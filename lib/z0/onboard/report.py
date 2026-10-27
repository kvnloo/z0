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
    if receipt.get("degraded"):
        out += ["", f"Degraded: {', '.join(receipt['degraded'])} failed. The first-task path "
                    "(z0intelligence, z0evals) is intact: go on to a first task, and fix the "
                    "items below when you can."]
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
