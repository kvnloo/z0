#!/usr/bin/env python3
"""Claude Code Stop hook: block the stop while the keepworking law forbids it.

stdin: the Stop hook input (session_id, transcript_path, cwd, stop_hook_active,
background_tasks, session_crons, ...). stdout: {"decision":"block","reason":...}
when the kernel blocks; nothing when it allows. A crash in this file never blocks.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from z0.keepworking import kernel as k  # noqa: E402
    from z0.keepworking import ledger as lg  # noqa: E402
else:
    from . import kernel as k
    from . import ledger as lg

MAX_LISTED = 8
# Hard cap on how many times one session can be sent back to work. G1 already ends
# the loop when a continued turn runs no tool; the cap also ends it when every
# continued turn keeps running tools without closing asks.
DEFAULT_MAX_CONTINUATIONS = 8
INTERACTIVE_ENTRYPOINTS = ("", "cli")


def state_dir(ledger_path: Path) -> Path:
    return Path(os.environ.get("Z0_KEEPWORKING_STATE") or ledger_path.parent / "state" / "keepworking")


def tool_uses(transcript_path) -> int:
    """Count tool calls in the transcript; -1 when it cannot be read."""
    try:
        with open(os.path.expanduser(str(transcript_path)), "rb") as fh:
            return sum(line.count(b'"type":"tool_use"') + line.count(b'"type": "tool_use"')
                       for line in fh)
    except (OSError, TypeError):
        return -1


def is_bound(event: dict, loaded: lg.Loaded, env) -> bool:
    """Scope policy, checked before the kernel. Unbound sessions may always stop.

    - Z0_KEEPWORKING=off: escape hatch, never bound.
    - no ledger: there is no registered approved work, so nothing to keep working on.
    - ledger "enforce": "off": escape hatch the owner can flip mid-session.
    - Z0_KEEPWORKING=on: force-bind (tests, an owner-launched headless run).
    - headless/SDK sessions (claude -p, Agent SDK, ACP bridges) and child sessions
      are workers, not the owner's session: unbound unless the ledger opts them in.
    - the session cwd must be under one of scope_cwd_prefixes (default ~/workspace).
    """
    flag = env.get("Z0_KEEPWORKING", "").lower()
    if flag in ("off", "0"):
        return False
    if loaded.state is k.Ledger.MISSING:
        return False
    cfg = loaded.config
    if loaded.state is k.Ledger.OK and str(cfg.get("enforce", "on")).lower() == "off":
        return False
    if flag in ("on", "1"):
        return True
    if env.get("CLAUDE_CODE_CHILD_SESSION") == "1" and not cfg.get("include_child_sessions"):
        return False
    if (env.get("CLAUDE_CODE_ENTRYPOINT", "") not in INTERACTIVE_ENTRYPOINTS
            and not cfg.get("include_print_sessions")):
        return False
    prefixes = cfg.get("scope_cwd_prefixes") or [str(Path.home() / "workspace")]
    cwd = os.path.realpath(str(event.get("cwd") or os.getcwd()))
    return any(cwd == os.path.realpath(os.path.expanduser(p))
               or cwd.startswith(os.path.realpath(os.path.expanduser(p)) + os.sep)
               for p in prefixes)


def max_continuations(loaded: lg.Loaded, env) -> int:
    raw = env.get("Z0_KEEPWORKING_MAX") or loaded.config.get("max_continuations")
    try:
        return max(0, int(raw)) if raw is not None else DEFAULT_MAX_CONTINUATIONS
    except (TypeError, ValueError):
        return DEFAULT_MAX_CONTINUATIONS


def reason_text(verdict: k.Verdict, loaded: lg.Loaded, ledger_path: Path) -> str:
    if verdict.reason is k.Reason.LEDGER_BROKEN:
        return (f"keepworking law: the ask ledger is unusable ({loaded.error}). "
                f"Fix {ledger_path} (JSON object with an 'asks' list) before stopping.")
    rows = loaded.open_entries
    lines = [f"keepworking law: {len(rows)} of {len(loaded.entries)} owner asks are not done "
             "or validly blocked. Keep working. Next actions:"]
    for e in rows[:MAX_LISTED]:
        lines.append(f"- [{e.id}] {e.why}. next: {e.next or 'decide the next concrete step and do it'}")
    if len(rows) > MAX_LISTED:
        lines.append(f"- ... and {len(rows) - MAX_LISTED} more (python3 -m z0.keepworking check)")
    lines.append(f"Record progress in {ledger_path}: 'done' needs evidence kind deployed_sha, "
                 "device_receipt (existing file) or pr (GitHub PR URL); 'blocked' needs "
                 "blocked_by kind sudo/login/merge_review/physical/owner_decision/payment with a "
                 "detail and a 'checked' date. Never mark an ask done or blocked to escape this hook.")
    return "\n".join(lines)


def decide(event: dict, env=os.environ, today: dt.date | None = None):
    ledger_path = Path(env.get("Z0_ASKS_LEDGER") or lg.DEFAULT_LEDGER)
    loaded = lg.load(ledger_path, today)
    bound = is_bound(event, loaded, env)
    waiting = bool(event.get("background_tasks")) or bool(event.get("session_crons"))
    active = bool(event.get("stop_hook_active"))
    session = str(event.get("session_id") or "unknown").replace("/", "_")
    sdir = state_dir(ledger_path)
    marker = sdir / f"{session}.json"
    uses = tool_uses(event.get("transcript_path"))
    try:
        state = json.loads(marker.read_text())
        last, blocks = state.get("tool_uses", -1), int(state.get("blocks", 0))
        if state.get("prompt_id") != event.get("prompt_id"):
            blocks = 0  # the cap counts continuations per user prompt
    except (OSError, ValueError, AttributeError, TypeError):
        last, blocks = -1, 0
    progress = uses >= 0 and uses > last
    verdict = k.decide_stop(bound, waiting, loaded.state, loaded.all_ok, active, progress)
    cap = max_continuations(loaded, env)
    capped = verdict.blocks and blocks >= cap
    if capped:  # cap reached: release the session; the ledger still lists the open asks
        verdict = k.allow(k.Reason.NO_PROGRESS)
    record = {"at": dt.datetime.now().isoformat(timespec="seconds"), "session": session,
              "bound": bound, "waiting": waiting, "ledger": loaded.state.name,
              "all_ok": loaded.all_ok, "active": active, "progress": progress,
              "blocks": blocks, "cap": cap, "capped": capped,
              "verdict": verdict.kind.name, "reason": verdict.reason.name,
              "open": [e.id for e in loaded.open_entries]}
    try:
        sdir.mkdir(parents=True, exist_ok=True)
        if verdict.blocks:
            marker.write_text(json.dumps({"tool_uses": uses, "blocks": blocks + 1,
                                          "prompt_id": event.get("prompt_id")}))
        with open(sdir / "decisions.jsonl", "a") as log:
            log.write(json.dumps(record) + "\n")
    except OSError:
        pass
    out = None
    if verdict.blocks:
        out = {"decision": "block", "reason": reason_text(verdict, loaded, ledger_path)
               + f"\n(continuation {blocks + 1} of at most {cap} for this prompt; the owner's "
               "escape: set \"enforce\": \"off\" in the ledger or Z0_KEEPWORKING=off)"}
    return verdict, out


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        _, out = decide(event)
    except Exception as exc:  # a broken hook must never trap the session
        print(f"z0-keepworking hook error (stop allowed): {exc}", file=sys.stderr)
        return 1
    if out is not None:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
