"""Seven closed questions (§7). Verifiers inspect detected facts, never the host.

Answers are hints, not new facts, grants, steps, paths, or executable commands.
The conservative default need not be a candidate (e.g. the generic package hint).
"""
from __future__ import annotations

import copy
import posixpath
from dataclasses import dataclass
from typing import Callable

from .. import kernel as k

KINDS = ("harness_classify", "config_dir_pick", "fork_match", "port_owner",
         "gpu_vendor_resolve", "pkg_hint", "failure_triage")
# Explicit projections: never send an entire host, environment, file or error log.
FACT_KEYS = {
    "harness_classify": ("name", "dir", "symlink_target", "shebang", "policies"),
    "config_dir_pick": ("dirs",),
    "fork_match": ("pin_present",),
    "port_owner": ("executable", "release_root"),
    "gpu_vendor_resolve": ("driver_classes",),
    "pkg_hint": ("tool", "family", "packages"),
    "failure_triage": ("step_id", "exit_code", "remediations", "conditions_hold"),
}
DEFAULTS = {"harness_classify": "unsupported", "config_dir_pick": "all",
            "fork_match": "no", "port_owner": "conflict", "gpu_vendor_resolve": "cpu",
            "pkg_hint": "generic hint", "failure_triage": "mark_unavailable"}


def provider_allowed(name: str) -> bool:
    return k.decide_provider(k.provider_from_id(name)).kind is not k.Kind.REFUSE


def verify_harness(facts: dict, answer: str) -> bool:
    policy = facts.get("policies", {}).get(answer, {})
    return (answer == "unsupported" or
            (bool(policy) and policy.get("exec_probe") == "allowed"
             and policy.get("configure") != "never"
             and k.provider_from_id(answer) not in k.FORBIDDEN_PROVIDERS))


def verify_config(facts: dict, answer: str) -> bool:
    # detect/harnesses records only dirs whose projects/ child exists.
    return answer == "all" or answer in facts.get("dirs", [])


def verify_fork(facts: dict, answer: str) -> bool:
    return answer == "no" or (answer == "yes" and facts.get("pin_present") is True)


def verify_port(facts: dict, answer: str) -> bool:
    root, exe = facts.get("release_root", ""), facts.get("executable", "")
    return answer == "conflict" or (answer == "adopt" and bool(root) and bool(exe)
                                   and posixpath.normpath(exe).startswith(
                                       posixpath.normpath(root).rstrip("/") + "/"))


def verify_gpu(facts: dict, answer: str) -> bool:
    return answer == "cpu" or (answer in ("nvidia", "amd", "apple", "intel_mac")
                               and answer in facts.get("driver_classes", []))


def verify_pkg(facts: dict, answer: str) -> bool:
    return answer in facts.get("packages", [])  # print-only; never executed


def verify_failure(facts: dict, answer: str) -> bool:
    return answer == "mark_unavailable" or (answer in facts.get("remediations", [])
                                           and facts.get("conditions_hold", {}).get(answer) is True)


VERIFIERS = dict(zip(KINDS, (verify_harness, verify_config, verify_fork, verify_port,
                             verify_gpu, verify_pkg, verify_failure)))


@dataclass(frozen=True)
class Question:
    id: str
    kind: str
    facts: dict
    candidates: tuple
    safe_default: str
    verifier: Callable[[dict, str], bool]

    def payload(self) -> dict:
        return {"id": self.id, "kind": self.kind, "facts": self.facts,
                "candidates": list(self.candidates), "safe_default": self.safe_default}

    def accepts(self, answer: str) -> bool:
        return (type(answer) is str and answer in self.candidates
                and self.verifier(self.facts, answer))


def question(raw: dict, snap: dict) -> Question:
    """Close an unknown against registry candidates and immutable detected evidence."""
    kind = raw["kind"]
    if kind not in KINDS or not isinstance(raw.get("id"), str):
        raise ValueError("unknown question kind or invalid id")
    source = raw.get("facts") or {}
    facts = {}
    strings = {"name", "dir", "symlink_target", "shebang", "executable", "release_root",
               "tool", "family", "step_id"}
    sequences = {"dirs", "driver_classes", "remediations"}
    for key in FACT_KEYS[kind]:
        value = source.get(key)
        if key in strings and type(value) is str:
            facts[key] = value
        elif key in sequences and isinstance(value, list) and all(type(v) is str for v in value):
            facts[key] = list(value)
        elif key == "pin_present" and type(value) is bool:
            facts[key] = value
        elif key == "exit_code" and type(value) is int:
            facts[key] = value
    if kind == "failure_triage":
        holds = source.get("conditions_hold") or {}
        facts["conditions_hold"] = {name: holds.get(name) is True
                                    for name in facts.get("remediations", [])}
    rows = (snap.get("harnesses") or {}).get("harnesses") or {}
    supplied = [c for c in raw.get("candidates", []) if type(c) is str]
    if kind == "harness_classify":
        facts["policies"] = {hid: copy.deepcopy(row.get("policy") or {}) for hid, row in rows.items()}
        legal = set(rows) | {"unsupported"}
    elif kind == "config_dir_pick":
        legal = set(facts.get("dirs", [])) | {"all"}
    elif kind == "fork_match":
        legal = {"yes", "no"}
    elif kind == "port_owner":
        legal = {"adopt", "conflict"}
    elif kind == "gpu_vendor_resolve":
        legal = {"cpu", "nvidia", "amd", "apple", "intel_mac"}
    elif kind == "pkg_hint":
        tools = (snap.get("toolchains") or {}).get("tools") or {}
        packages = list((tools.get(facts.get("tool"), {}).get("system_pkg") or {}).values())
        facts["packages"] = sorted(set(packages))
        legal = set(packages)
    else:
        # Remediation conditions are evaluated by the collector, not by the model.
        legal = set(facts.get("remediations", [])) | {"mark_unavailable"}
    # Probe results are typed detection metadata only, never user file contents.
    recorded = raw.get("facts", {}).get("probe_results", {})
    facts["probe_results"] = {
        pid: {key: row[key] for key in ("exists", "mode") if key in row
              and (type(row[key]) is bool if key == "exists" else type(row[key]) is int)}
        for pid, row in recorded.items() if isinstance(row, dict)
    } if isinstance(recorded, dict) else {}
    candidates = tuple(dict.fromkeys(c for c in supplied if c in legal))
    return Question(raw["id"], kind, facts, candidates, DEFAULTS[kind], VERIFIERS[kind])


def collect(host: dict, snap: dict) -> list:
    out = []
    for raw in host.get("unknowns") or []:
        if raw.get("kind") in KINDS:
            out.append(question(raw, snap))
    if len({q.id for q in out}) != len(out):
        raise ValueError("duplicate question id")
    return sorted(out, key=lambda q: q.id)
