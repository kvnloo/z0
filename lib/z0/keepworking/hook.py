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
    if env.get("Z0_KEEPWORKING", "").lower() in ("off", "0"):
        return False
    cfg = loaded.config
    if loaded.state is k.Ledger.OK and str(cfg.get("enforce", "on")).lower() == "off":
        return False
    if env.get("CLAUDE_CODE_CHILD_SESSION") == "1" and not cfg.get("include_child_sessions"):
        return False
    prefixes = cfg.get("scope_cwd_prefixes") or [str(Path.home() / "workspace")]
    cwd = os.path.realpath(str(event.get("cwd") or os.getcwd()))
    return any(cwd == os.path.realpath(os.path.expanduser(p))
               or cwd.startswith(os.path.realpath(os.path.expanduser(p)) + os.sep)
               for p in prefixes)


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
        last = json.loads(marker.read_text()).get("tool_uses", -1)
    except (OSError, ValueError, AttributeError):
        last = -1
    progress = uses >= 0 and uses > last
    verdict = k.decide_stop(bound, waiting, loaded.state, loaded.all_ok, active, progress)
    record = {"at": dt.datetime.now().isoformat(timespec="seconds"), "session": session,
              "bound": bound, "waiting": waiting, "ledger": loaded.state.name,
              "all_ok": loaded.all_ok, "active": active, "progress": progress,
              "verdict": verdict.kind.name, "reason": verdict.reason.name,
              "open": [e.id for e in loaded.open_entries]}
    try:
        sdir.mkdir(parents=True, exist_ok=True)
        if verdict.blocks:
            marker.write_text(json.dumps({"tool_uses": uses}))
        with open(sdir / "decisions.jsonl", "a") as log:
            log.write(json.dumps(record) + "\n")
    except OSError:
        pass
    out = None
    if verdict.blocks:
        out = {"decision": "block", "reason": reason_text(verdict, loaded, ledger_path)}
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
