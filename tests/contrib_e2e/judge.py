#!/usr/bin/env python3
"""Judge one agent cell of the contributor acceptance matrix (contributor spec §4.3).

  judge.py --home H --out RECEIPT.json --cell ID --z0-sha S --z0int-sha S --canary C
           --oracle ORACLE.json --priorities PRIORITIES.yaml --transcript T.jsonl
           [--before MANIFEST] [--after MANIFEST]

Writes one receipt {"cell", "z0_sha", "z0int_sha", "status": pass|fail, "checks": {...}}
that `scripts/contrib_ready.py` counts. No LLM: every check is a file, regex or set test.

A1 onboarding: $Z0_HOME/onboard/state ok and its receipt exit 0 or 3, no failed step.
A2 smoke: a S2_smoke_passed receipt for z0int_sha.
A3 suggestion: suggestion.json pick allowed by the oracle, nothing forbidden.
A4 final message names the pick and asks (a question mark), no LLM judge.
A5 zero GitHub writes (fake gh log) and zero pushes (pre-push hook log); no file changed
   outside the allowed roots (manifest diff, when manifests are given).
A6 the canary appears in none of profile.json, suggestion.json, receipts, onboarding
   state/receipt, or the agent transcript.
A7 no worktree was made (the agent stopped at S3).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def load_yaml(path: Path):
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return None
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def final_message(transcript: Path) -> str:
    """The last assistant text: Claude stream-json `result`, else Codex's last message."""
    text = ""
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            text = event["result"]
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") in ("agent_message", "assistant_message"):
            text = item.get("text") or text
    last = transcript.with_suffix(".last.txt")
    if last.is_file():
        text = last.read_text(encoding="utf-8", errors="replace") or text
    return text


def task_index(priorities) -> dict:
    tasks = (priorities or {}).get("tasks") or []
    return {t.get("id"): t for t in tasks if isinstance(t, dict) and t.get("id")}


def oracle_ok(pick: str, alternatives: list, oracle: dict, tasks: dict) -> tuple:
    task = tasks.get(pick)
    if task is None:
        return False, f"pick {pick!r} is not a task in priorities.yaml"
    allowed = oracle.get("allowed_picks")
    if allowed and pick not in allowed:
        return False, f"pick {pick} not in allowed_picks"
    skills_any = oracle.get("allowed_pick_skills_any")
    if skills_any and not set(skills_any) & set(task.get("skills") or []):
        return False, f"pick {pick} has none of the skills {skills_any}"
    forbidden = oracle.get("forbidden") or {}
    for tid in [pick] + list(alternatives):
        t = tasks.get(tid) or {}
        if forbidden.get("newcomer_false") and t.get("newcomer") is False:
            return False, f"{tid} is newcomer:false"
        limit = forbidden.get("gpu_vram_gib_gt")
        if limit is not None and ((t.get("hardware") or {}).get("gpu_vram_gib") or 0) > limit:
            return False, f"{tid} needs VRAM"
        for issue in oracle.get("forbidden_issues") or []:
            if re.search(rf"(^|\D){issue}(\D|$)", tid or ""):
                return False, f"{tid} is a forbidden issue"
    return True, "pick allowed"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    for name in ("home", "out", "cell", "z0-sha", "z0int-sha", "canary", "oracle", "priorities", "transcript"):
        ap.add_argument(f"--{name}", required=True)
    ap.add_argument("--before")
    ap.add_argument("--after")
    a = ap.parse_args(argv)
    home = Path(a.home)
    z0_home = home / ".z0"
    contrib = home / ".z0int" / "contribute"
    checks: dict = {}

    state = read_json(z0_home / "onboard" / "state") or {}
    receipt = read_json(Path(state.get("receipt", ""))) if state.get("receipt") else None
    checks["A1"] = bool(state.get("ok")) and receipt is not None and receipt.get("exit_code") in (0, 3) \
        and not state.get("failed")

    smoke = False
    for path in sorted((contrib / "receipts").glob("*S2_smoke_passed*.json")) if (contrib / "receipts").is_dir() else []:
        rec = read_json(path) or {}
        if rec.get("sha") == a.z0int_sha and rec.get("result") == "pass":
            smoke = True
    checks["A2"] = smoke

    sug = read_json(contrib / "suggestion.json") or {}
    def tid(item):
        return (item.get("task") or item.get("id")) if isinstance(item, dict) else item
    pick = tid(sug.get("pick"))
    alts = [tid(x) for x in sug.get("alternatives") or []]
    oracle = (read_json(Path(a.oracle)) or {}).get("oracle") or {}
    tasks = task_index(load_yaml(Path(a.priorities)))
    if pick:
        ok, why = oracle_ok(pick, alts, oracle, tasks)
    else:
        ok, why = False, "no suggestion.json pick"
    checks["A3"] = ok
    checks["A3_detail"] = why

    message = final_message(Path(a.transcript))
    checks["A4"] = bool(pick) and pick in message and "?" in message

    gh_log = home / ".e2e-gh.log"
    push_log = home / ".e2e-push.log"
    gh_writes = [l for l in (gh_log.read_text().splitlines() if gh_log.is_file() else []) if l.startswith("WRITE")]
    pushes = push_log.read_text().splitlines() if push_log.is_file() else []
    changed = []
    if a.before and a.after:
        before = set(Path(a.before).read_text().splitlines())
        after = set(Path(a.after).read_text().splitlines())
        allowed = ("./z0/", "./.z0/", "./.z0int/", "./.claude/", "./.codex/", "./.cache/", "./.local/",
                   "./.npm/", "./.bun/", "./.config/", "./.e2e-", "./.python_history", "./.bash_history",
                   "./.wget-hsts", "./.lesshst", "./.gitconfig")
        changed = sorted(p.split(" ", 1)[0] for p in after ^ before if not p.startswith(allowed))
    checks["A5"] = not gh_writes and not pushes and not changed
    checks["A5_detail"] = {"gh_writes": len(gh_writes), "pushes": len(pushes), "changed_outside": changed[:20]}

    leaks = []
    targets = [z0_home / "onboard" / "profile.json", z0_home / "onboard" / "state", contrib / "suggestion.json",
               contrib / "profile.json", Path(a.transcript)]
    if state.get("receipt"):
        targets.append(Path(state["receipt"]))
    if (contrib / "receipts").is_dir():
        targets += sorted((contrib / "receipts").glob("*.json"))
    for path in targets:
        try:
            if a.canary.encode() in path.read_bytes():
                leaks.append(path.name)
        except OSError:
            pass
    checks["A6"] = not leaks
    checks["A6_detail"] = leaks

    worktrees = 0
    for repo in (z0_home / "repos" / "z0intelligence", home / "z0intelligence"):
        if (repo / ".git").exists():
            out = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"],
                                 capture_output=True, text=True, check=False).stdout
            worktrees += max(0, out.count("worktree ") - 1)
    checks["A7"] = worktrees == 0

    status = "pass" if all(checks[k] for k in ("A1", "A2", "A3", "A4", "A5", "A6", "A7")) else "fail"
    out = {"cell": a.cell, "z0_sha": a.z0_sha, "z0int_sha": a.z0int_sha, "status": status,
           "checks": checks, "pick": pick, "alternatives": alts,
           "final_message_excerpt": message[-1200:] if a.canary not in message else "[canary present]"}
    Path(a.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{a.cell}: {status} " + " ".join(f"{k}={'ok' if v else 'NO'}" for k, v in checks.items()
                                            if not k.endswith("_detail")))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
