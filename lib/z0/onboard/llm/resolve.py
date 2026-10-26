"""§7 resolver: bounded sends outside PLAN; immutable JSON-subset answers.yaml.

The persisted object is returned byte-for-byte semantically on replay: source is
NOT rewritten to 'replay' (that would change the plan hash). Invalid, edited or
foreign-host replay input refuses before provider discovery, never silently calls.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import signal
import socket
import threading
import time
from typing import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import kernel as k
from ..redact import Redactor, from_env, secret_names
from . import providers
from .privacy import UnsafePrompt, probe_evidence, prompt_for
from .questions import Question


class ReplayError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


@dataclass
class Context:
    snap: dict = field(default_factory=dict)
    env: dict = field(default_factory=lambda: dict(os.environ), repr=False)
    host_id: str = ""
    home: str = ""
    username: str = ""
    hostnames: tuple = ()
    canaries: tuple = field(default=(), repr=False)
    redactor: Redactor | None = field(default=None, repr=False)
    providers: list | None = None
    clock: Callable[[], float] = time.monotonic

    def privacy(self):
        redactor = self.redactor or from_env(self.snap, self.env, self.home)
        # All environment values we touched stay in memory and are scrubbed, not
        # only known key names. Identity gets the dedicated home/user/host forms.
        identity = {self.home, self.username, *self.hostnames}
        for value in self.env.values():
            if isinstance(value, str) and value not in identity:
                redactor.register(value)
        for name in secret_names(self.snap):
            redactor.register(self.env.get(name), minimum=1)
        return redactor


def default_context():
    from .. import regsnap
    from ..detect import Ctx, osinfo
    env = dict(os.environ)
    snap = regsnap.load()
    detection = Ctx(registry=snap)
    os_name, _ = osinfo._os_arch(detection)
    host_id = osinfo.host_id(osinfo._machine_id(detection, os_name), detection.hostname or "")
    return Context(snap=snap, env=env, host_id=host_id, home=str(Path.home()),
                   username=env.get("USER", ""), hostnames=(socket.gethostname(), env.get("HOSTNAME", "")))


def remote_granted(provider_id, mode, grants):
    source = {"flag": k.Source.FLAG, "tty": k.Source.TTY}.get(grants.get("source"), k.Source.LLM)
    named = provider_id in (grants.get("llm_providers") or [])
    return k.decide_consent(k.Mode.AUTO if mode == "auto" else k.Mode.GUIDED,
                            k.ConsentClass.C1, named, source).kind is k.Kind.ALLOW


@contextlib.contextmanager
def deadline(seconds):
    """Bound wall time too, not just socket inactivity (e.g. a trickle response).

    No threads/process pools. On platforms without a usable timer fail closed;
    all supported onboarding hosts have POSIX interval timers.
    """
    if not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread():
        raise TimeoutError("deadline_unavailable")
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    if old_timer[0]:
        raise TimeoutError("deadline_busy")
    def expired(signum, frame):
        raise TimeoutError("provider_timeout")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def response(raw):
    """Exact validation of providers.ANSWER_SCHEMA, without a schema dependency."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    if not isinstance(raw, str) or len(raw.encode()) > providers.MAX_BYTES:
        raise ValueError("response_schema")
    data = json.loads(raw, object_pairs_hook=unique)
    if type(data) is not dict or set(data) not in ({"answer"}, {"need_probe"}):
        raise ValueError("response_schema")
    if type(next(iter(data.values()))) is not str:
        raise ValueError("response_schema")
    return data


def validate_record(q, record):
    required = {"question_id", "kind", "source", "prompt_sha256", "answer", "accepted", "reason"}
    if not isinstance(record, dict) or not required <= record.keys() \
            or record.keys() - required - {"provider", "model"}:
        return False
    if record["question_id"] != q.id or record["kind"] != q.kind:
        return False
    if record["source"] not in ("llm", "safe_default") or type(record["accepted"]) is not bool:
        return False
    if not isinstance(record["reason"], str):
        return False
    sha = record["prompt_sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        return False
    if "provider" in record:
        if (not isinstance(record.get("provider"), str) or not isinstance(record.get("model"), str)
                or k.decide_provider(k.provider_from_id(record["provider"])).kind is k.Kind.REFUSE):
            return False
    elif "model" in record:
        return False
    if record["source"] == "safe_default":
        return record["answer"] == q.safe_default and not record["accepted"]
    return (record["accepted"] and q.accepts(record["answer"])
            and isinstance(record.get("model"), str)
            and k.decide_provider(k.provider_from_id(record.get("provider", ""))).kind is not k.Kind.REFUSE)


def freeze(path, envelope):
    """Exclusive creation: concurrent resolvers cannot overwrite a frozen decision."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())


def frozen_envelope(questions, mode, grants, llm_flag, host_id, answers):
    fingerprint = digest({"questions": [q.payload() for q in questions], "host_id": host_id,
                          "mode": mode, "grants": grants, "llm": llm_flag})
    return {"version": 1, "host_id": host_id, "input_sha256": fingerprint,
            "answers_sha256": digest(answers), "answers": answers}


def resolve(questions, mode, grants, llm_flag, answers_path, *, context=None):
    """Return {'llm': {question id: frozen record}}; never return consent fields.

    `answers_path=None` is an in-memory resolution (caller must freeze before apply).
    `none` skips everything, including discovery, replay reads and context loading.
    """
    if llm_flag == "none":
        return {}
    if llm_flag not in ("local", "auto"):
        raise ValueError("invalid LLM flag")
    ctx = context or default_context()
    questions = list(questions)
    if any(not isinstance(q, Question) for q in questions) or len({q.id for q in questions}) != len(questions):
        raise ValueError("invalid questions")
    grants = grants or {}
    fingerprint = digest({"questions": [q.payload() for q in questions], "host_id": ctx.host_id,
                          "mode": mode, "grants": grants, "llm": llm_flag})
    answers = {}
    if answers_path is not None and Path(answers_path).exists():
        try:
            envelope = json.loads(Path(answers_path).read_text(encoding="utf-8"))
            answers = envelope["answers"]
            records = answers["llm"]
            valid = (envelope["version"] == 1 and envelope["input_sha256"] == fingerprint
                     and envelope["host_id"] == ctx.host_id and set(answers) == {"llm"}
                     and set(records) == {q.id for q in questions}
                     and envelope["answers_sha256"] == digest(answers)
                     and all(validate_record(q, records[q.id]) for q in questions)
                     and all(r.get("provider", "local") == "local" or
                             (llm_flag == "auto" and remote_granted(r["provider"], mode, grants))
                             for r in records.values()))
        except (OSError, ValueError, KeyError, TypeError):
            valid = False
        if not valid:
            raise ReplayError("frozen answers do not match this host, questions or grants")
        return answers
    policy = (ctx.snap.get("onboarding") or {}).get("llm") or {}
    budget = policy.get("budget") or {}
    max_calls = max(0, min(8, int(budget.get("max_calls", 8))))
    timeout = max(0, min(30, float(budget.get("call_timeout_s", 30))))
    total = max(0, min(180, float(budget.get("total_s", 180))))
    rounds = max(0, min(2, int(budget.get("probe_rounds", 2))))
    start, calls = ctx.clock(), 0
    redactor = ctx.privacy()
    selected = None
    selection_reason = "no_provider" if max_calls and timeout and total else "budget_exhausted"
    # Crucially: prepare/check ALL prompts before discovery or smoke sends.
    prompts = {}
    for q in questions:
        if redactor.found_in(q.id.encode()) or any(v and v in q.id for v in ctx.canaries):
            raise UnsafePrompt("unsafe question identifier")
        try:
            prompts[q.id] = prompt_for(q, redactor, ctx.username, ctx.hostnames, ctx.canaries)
        except UnsafePrompt:
            prompts[q.id] = None
    if any(prompts.values()) and max_calls and timeout and total:
        choices = ctx.providers if ctx.providers is not None else providers.configured(ctx.snap, ctx.env)
        for provider in choices:
            verdict = k.decide_provider(k.provider_from_id(provider.id))
            if verdict.kind is k.Kind.REFUSE:
                selection_reason = "forbidden_provider"
                continue
            if provider.id != "local" and (llm_flag != "auto" or not remote_granted(provider.id, mode, grants)):
                selection_reason = "remote_ungranted"
                continue
            remaining = total - (ctx.clock() - start)
            if remaining <= 0:
                selection_reason = "budget_exhausted"
                break
            try:
                with deadline(min(timeout, remaining)):
                    available = provider.available(timeout=min(2, timeout, remaining))
                if available:
                    selected = provider
                    break
            except Exception:
                selection_reason = "provider_unavailable"
    answers = {"llm": {}}
    for q in questions:
        prompt = prompts[q.id]
        record = {"question_id": q.id, "kind": q.kind, "source": "safe_default",
                  "prompt_sha256": hashlib.sha256((prompt or "").encode()).hexdigest(),
                  "answer": q.safe_default, "accepted": False,
                  "reason": "redaction_failed" if prompt is None else selection_reason}
        probes = {}
        for round_number in range(rounds + 1):
            if prompt is None or selected is None:
                break
            remaining = total - (ctx.clock() - start)
            if calls >= max_calls or remaining <= 0 or timeout <= 0:
                record["reason"] = "budget_exhausted"
                break
            record.update(provider=selected.id, model=redactor(selected.model),
                          prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
            calls += 1
            try:
                with deadline(min(timeout, remaining)):
                    raw = selected.send(prompt, min(timeout, remaining))
                if ctx.clock() - start > total:
                    record["reason"] = "budget_exhausted"
                    break
                data = response(raw)
                if "need_probe" in data:
                    evidence = probe_evidence(data["need_probe"], ctx.snap.get("onboarding", {}).get("probes", {}), q)
                    if round_number >= rounds or evidence is None:
                        record["reason"] = "probe_unavailable" if evidence is None else "probe_rounds"
                        break
                    probes[data["need_probe"]] = evidence
                    prompt = prompt_for(q, redactor, ctx.username, ctx.hostnames, ctx.canaries, probes)
                    continue
                answer = data["answer"]
                if answer not in q.candidates:
                    record["reason"] = "out_of_set"
                elif not q.accepts(answer):
                    record["reason"] = "verifier_failed"
                elif redactor.found_in(answer.encode()) or any(v and v in answer for v in ctx.canaries):
                    record["reason"] = "redaction_failed"
                else:
                    record.update(source="llm", answer=answer, accepted=True, reason="verified")
            except (TimeoutError,):
                record["reason"] = "timeout"
            except (ValueError, TypeError):
                record["reason"] = "response_schema"
            except Exception:
                record["reason"] = "provider_failed"  # never persist raw provider errors
            break
        if redactor.found_in(json.dumps(record).encode()) or any(v and v in json.dumps(record) for v in ctx.canaries):
            raise UnsafePrompt("unsafe answer metadata")
        answers["llm"][q.id] = record
    if answers_path is not None:
        freeze(answers_path, {"version": 1, "host_id": ctx.host_id, "input_sha256": fingerprint,
                              "answers_sha256": digest(answers), "answers": answers})
    return answers
