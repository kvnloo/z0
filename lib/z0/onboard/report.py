"""`report.md` for a zero-context reader (design §1.2), in this order:

1. What you need to do: the asks, by impact, each with a reason and a command.
2. What was installed, from which SHA.
3. What is unavailable, and why.
4. Harness table.
5. LLM decisions.
6. Upstream gaps and warnings found.

Names, hashes and statuses only: no secret value, no env value, no file contents.
"""
from __future__ import annotations


FIRST_TASK = ("z0intelligence", "z0evals")


def missing_first_task(receipt: dict) -> list:
    """First-task components that cannot run here: every one of their steps is refused
    (e.g. z0intelligence on Intel macOS) or unavailable (e.g. under 8 GiB RAM).

    Neither is a failure and neither changes the exit code, so say it in words."""
    # shortcut: step ids are `<component>.<step>`; read plan components if that ever changes.
    if receipt.get("exit_code") == 4:   # the whole plan was refused; that message governs
        return []
    missing = []
    for c in FIRST_TASK:
        states = [s["status"] for s in receipt["steps"] if s["id"].startswith(c + ".")]
        if states and all(st in ("refused", "unavailable") for st in states):
            missing.append(c)
    return missing


def first_task_note(receipt: dict) -> str:
    missing = missing_first_task(receipt)
    if "z0intelligence" not in missing:
        return ""
    note = ("z0intelligence is not installed on this host (refused or unavailable; report.md "
            "\"Unavailable\" says why. Not a failure: the exit code ignores it), so there is no "
            "first task here.")
    if "z0evals" not in missing:
        note += " z0evals still runs: `./z0 onboard verify` re-runs its checks."
    return note


def render(plan_obj: dict, receipt: dict, extra: list, warnings: list) -> str:
    out = [f"# z0 onboard report: run {receipt['run_id']}", "",
           f"Exit code {receipt['exit_code']}. Plan `{plan_obj['plan_hash'][:12]}`, mode {plan_obj['mode']}, "
           f"profile {plan_obj.get('profile') or '-'}, targets {', '.join(plan_obj.get('targets') or [])}.", ""]
    out += ["## What you need to do", ""]
    if receipt["asks"]:
        for ask in receipt["asks"]:
            out.append(f"- **{ask['id']}** [{ask.get('consent', '')}]: {ask['reason']}  ")
            out.append(f"  `{ask['command']}`")
    else:
        out.append("Nothing.")
    failed = [s for s in receipt["steps"] if s["status"] == "failed"]
    failed_checks = [i for i in extra if i["status"] == "failed"]
    missing = missing_first_task(receipt)
    if receipt.get("degraded"):
        if "z0intelligence" in missing:
            # No first task on this host: the note below says so; never also say "go on".
            out += ["", f"Degraded: {', '.join(receipt['degraded'])} failed. Fix the items "
                        "below when you can."]
        else:
            intact = ", ".join(c for c in FIRST_TASK if c not in missing)
            out += ["", f"Degraded: {', '.join(receipt['degraded'])} failed. The first-task path "
                        f"({intact}) is intact: go on to a first task, and fix the "
                        "items below when you can."]
    if first_task_note(receipt):
        out += ["", first_task_note(receipt)]
    if failed or failed_checks:
        out += ["", "Failed (fix, then re-run `./z0 onboard`):"]
        out += [f"- {s['id']}: {s.get('reason', '')}" for s in failed]
        out += [f"- {i['component']}.{i['name']}: {i['detail']}" for i in failed_checks]
    out += ["", "## Installed", ""]
    if receipt["installed"]:
        for item in receipt["installed"]:
            where = f", release {item['release']}" if item.get("release") else ""
            how = "adopted in place" if item.get("adopted") else "z0 clone"
            out.append(f"- {item['component']} @ `{item['sha'][:12]}` ({how}{where})")
    else:
        out.append("Nothing new.")
    out += ["", "## Acceptance", ""]
    for cid, tiers in sorted(receipt["acceptance"].items()):
        out.append(f"- {cid}: " + ", ".join(f"{name} {status}" for name, status in tiers.items()))
    out += ["", "## Unavailable", ""]
    if plan_obj.get("unavailable"):
        out += [f"- {u['id']}: {u['detail']}" for u in plan_obj["unavailable"]]
    else:
        out.append("Nothing.")
    out += ["", "## Harnesses", "", "| harness | state | integration |", "|---|---|---|"]
    for hid, row in receipt["harnesses"].items():
        out.append(f"| {hid} | {row['state']} | {row['integration']} |")
    out += ["", "## LLM decisions", ""]
    if not receipt["llm_decisions"]:
        out.append("None (LLM disabled or no unresolved questions).")
    for row in receipt["llm_decisions"]:
        via = f" via {row['provider']} ({row.get('model', '-')})" if row.get("provider") else ""
        out.append(f"- {row['question_id']} [{row['kind']}]: {row['answer']} "
                   f"({row['source']}{via}; {row.get('reason', '')}). "
                   f"Prompt `{row.get('prompt_sha256', '-')}`.")
    out += ["", "## Upstream gaps and warnings", ""]
    out += [f"- {w}" for w in sorted(set(warnings))] or ["None."]
    out += ["", f"Secrets scan: {'CANARY FOUND' if receipt['secrets_scan']['canary_found'] else 'clean'} "
                f"({len(receipt['secrets_scan'].get('scanned') or [])} file(s)).", ""]
    return "\n".join(out)
