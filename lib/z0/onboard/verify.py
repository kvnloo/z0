"""VERIFY (design §6.4): acceptance checks, then `receipt.json` and `report.md`.

Runs every runnable `check` step of the applied plan (reusing a result APPLY got in
this same process), folds them into each component's acceptance tiers, adds the
component checks (checks/), and scans what the run wrote for any secret value the
process holds (the canary scan, law X1). `z0 doctor`'s exit code is never a gate.

Exit code: 0 when every required check passed, 1 otherwise (and 1 when APPLY failed a
step), 4 when the plan was refused as a whole (host mismatch, no profile).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import journal as journal_mod, report as report_mod
from .actions.base import ActionCtx
from .apply import Deps, effective_plan, make_ctx, run_step, write_private
from .checks import CHECKS
from .plan import exit_code as plan_exit_code

LAWS = {"H1": "bend+test", "S1": "bend+test", "S2": "bend+test", "S3": "bend+test",
        "C1": "bend+test", "C2": "bend+test", "L-LLM": "bend", "P1": "bend+test",
        "P0": "test", "O1": "test", "I1": "test", "R1": "test", "X1": "test", "H2": "test",
        "T1": "test", "M1": "bend+test"}


@dataclass
class VerifyView:
    plan: dict
    results: dict
    ctx: ActionCtx
    snap: dict
    effects: list
    plan_states: dict = field(default_factory=dict)
    acceptance: dict = field(default_factory=dict)

    def __post_init__(self):
        self.steps = {e["step"]["id"]: e["step"] for e in self.plan["steps"]}
        self.plan_states = {e["step"]["id"]: e["state"] for e in self.plan["steps"]}

    def check_status(self, sid: str) -> str:
        """passed | failed | unavailable | skipped, for one step."""
        result = self.results.get(sid) or {}
        status = result.get("status") or self.plan_states.get(sid, {}).get("status", "skipped")
        if status in ("passed", "already_satisfied"):
            return "passed"
        if status == "failed":
            return "failed"
        if status == "blocked":
            # Blocked by a failure in this run is a failure; blocked in the plan is not.
            return "failed" if self.plan_states.get(sid, {}).get("status") == "todo" else "unavailable"
        if status in ("unavailable", "refused"):
            return "unavailable"
        return "skipped"


def tier_status(statuses: list) -> str:
    if not statuses:
        return "skipped"
    for value in ("failed", "unavailable", "skipped"):
        if value in statuses:
            return value
    return "passed"


def acceptance(view: VerifyView) -> dict:
    comps = (view.snap.get("components") or {}).get("components") or {}
    out: dict = {}
    for cid in view.plan.get("targets") or []:
        tiers = (((comps.get(cid) or {}).get("onboard") or {}).get("acceptance") or {}).get("tiers") or []
        for tier in tiers:
            checks = [sid for sid in tier.get("checks") or [] if sid in view.steps]
            out.setdefault(cid, {})[tier["name"]] = tier_status([view.check_status(s) for s in checks])
    return out


def run_checks(ctx: ActionCtx, plan_obj: dict, results: dict, prior: dict, deps: Deps) -> dict:
    """Run each todo `check` not already run in this process; blocked when a step it
    needs failed or was blocked."""
    bad = {sid for sid, r in results.items() if r.get("status") in ("failed", "blocked", "refused")}
    out = dict(results)
    for entry in plan_obj["steps"]:
        step, state = entry["step"], entry["state"]
        sid = step["id"]
        if step["kind"] != "check" or state["status"] != "todo":
            continue
        if sid in prior:
            out[sid] = prior[sid]
        else:
            blocker = next((n for n in step.get("needs") or [] if n in bad), None)
            if blocker is not None:
                out[sid] = {"status": "blocked", "reason": f"dependency {blocker} failed"}
            else:
                deps.out(f"  check            {sid} ...")
                out[sid] = run_step(ctx, step)
            ctx.journal.write("verify", step=sid, status=out[sid]["status"],
                              reason=out[sid].get("reason", ""))
        if out[sid]["status"] in ("failed", "blocked"):
            bad.add(sid)
    return out


def secrets_scan(ctx: ActionCtx, run: Path, effects: list) -> dict:
    """X1: no secret value the process holds appears in anything this run wrote."""
    scanned, found = [], False
    files = [p for p in run.rglob("*") if p.is_file() and not p.is_symlink()]
    for effect in effects:
        if effect["effect"].get("kind") in ("file", "replace"):
            files.append(Path(ctx.expand(effect["effect"]["path"])))
    workspace = Path(ctx.z0_home) / "workspace.yaml"
    if workspace.is_file():
        files.append(workspace)
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        scanned.append(ctx.form(str(path)))
        if ctx.redactor.found_in(data):
            found = True
    return {"canary_found": found, "scanned": sorted(set(scanned))[:200]}


def receipt_steps(plan_obj: dict, results: dict, effects: list) -> list:
    by_step: dict = {}
    for effect in effects:
        item = {"path": effect["effect"]["path"]}
        if effect["effect"].get("sha256"):
            item["sha256"] = effect["effect"]["sha256"]
        if effect["effect"].get("target"):
            item["target"] = effect["effect"]["target"]
        by_step.setdefault(effect.get("step"), []).append(item)
    out = []
    for entry in plan_obj["steps"]:
        sid = entry["step"]["id"]
        result = results.get(sid) or {"status": entry["state"]["status"],
                                      "reason": entry["state"].get("reason", "")}
        status = result["status"]
        if status == "todo":
            status = "skipped"
        item = {"id": sid, "status": status}
        if result.get("reason"):
            item["reason"] = str(result["reason"])
        if result.get("remediation"):
            item["remediation"] = result["remediation"]
        if by_step.get(sid):
            item["effects"] = by_step[sid]
        out.append(item)
    return out


def installed(ctx: ActionCtx, plan_obj: dict, results: dict) -> list:
    out = []
    ok = ("passed", "already_satisfied")
    for cid, summary in (plan_obj.get("components") or {}).items():
        source = next((e["step"] for e in plan_obj["steps"] if e["step"].get("component") == cid
                       and e["step"]["kind"] == "adopt_or_clone"), None)
        if source is None or results.get(source["id"], {}).get("status") not in ok:
            continue
        pin = str((ctx.component(cid).get("install") or {}).get("ref") or "")
        item = {"component": cid, "sha": pin, "adopted": bool(summary.get("adopted"))}
        release = next((e["step"] for e in plan_obj["steps"] if e["step"].get("component") == cid
                        and e["step"]["kind"] == "stage_release"
                        and results.get(e["step"]["id"], {}).get("status") in ok), None)
        if release and release.get("creates"):
            item["release"] = release["creates"][0]
        if pin:
            out.append(item)
    return out


def harness_table(host: dict) -> dict:
    out = {}
    for hid, entry in sorted((host.get("harnesses") or {}).items()):
        state = entry.get("state", "absent")
        if state not in ("installed", "config_only", "absent"):
            state = "absent"
        integration = "policy_excluded" if entry.get("policy_excluded") or hid in ("grok", "cursor-agent") \
            else "none"
        out[hid] = {"state": state, "integration": integration}
    return out


def verify_run(run: Path, deps: Deps, *, prior: Optional[dict] = None, host: Optional[dict] = None,
               apply_code: Optional[int] = None, consent_code: int = 0) -> tuple:
    """Returns (exit code, receipt)."""
    plan_obj = effective_plan(run)
    host = host or json.loads((run / "host.json").read_text(encoding="utf-8"))
    journal = journal_mod.Journal(run / "journal.jsonl", run.name)
    entries = journal.entries()
    applied = {sid: {"status": e["status"], "reason": e.get("reason", ""),
                     **({"remediation": e["remediation"]} if e.get("remediation") else {})}
               for sid, e in journal_mod.step_results(entries).items()}
    if prior:
        applied.update(prior)
    ctx = make_ctx(run, plan_obj, host, deps, journal)
    journal.write("verify_start", plan_hash=plan_obj["plan_hash"])
    results = run_checks(ctx, plan_obj, applied, prior or {}, deps)
    effects = journal_mod.effects(journal.entries())
    view = VerifyView(plan_obj, results, ctx, deps.snap, effects)
    view.acceptance = acceptance(view)
    extra = []
    for cid, evaluate in CHECKS.items():
        if cid == "z0" or cid in (plan_obj.get("targets") or []):
            extra.extend(evaluate(view))
    accept = {cid: dict(tiers) for cid, tiers in view.acceptance.items()}
    for item in extra:
        accept.setdefault(item["component"], {})[item["name"]] = item["status"]
    scan = secrets_scan(ctx, run, effects)
    failed_steps = [sid for sid, r in results.items() if r.get("status") == "failed"]
    failed_checks = [f"{i['component']}.{i['name']}" for i in extra
                     if i["status"] == "failed" and i.get("required", True)]
    refused = plan_exit_code(plan_obj)
    if refused:
        code = refused
    elif failed_steps or failed_checks or scan["canary_found"] or apply_code == 1:
        code = 1
    else:
        code = consent_code
    receipt = {
        "version": 1, "run_id": run.name, "plan_hash": plan_obj["plan_hash"],
        "host_id": plan_obj["host_id"], "started_at": _first_ts(entries), "finished_at": journal_mod.utc_now(),
        "exit_code": code,
        "installed": installed(ctx, plan_obj, results),
        "steps": receipt_steps(plan_obj, results, effects),
        "acceptance": accept,
        "asks": [{key: ask[key] for key in ("id", "reason", "command", "consent") if key in ask}
                 for ask in plan_obj.get("asks") or []],
        "harnesses": harness_table(host),
        "llm_decisions": plan_obj.get("llm_decisions", []),
        "laws": LAWS,
        "secrets_scan": scan,
    }
    warnings = list(plan_obj.get("warnings") or []) + ctx.warnings
    for item in extra:
        warnings.extend(item.get("warnings") or [])
    write_private(run / "receipt.json", json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    text = report_mod.render(plan_obj, receipt, extra, warnings)
    write_private(run / "report.md", ctx.redactor(text))
    journal.write("verify_done", exit_code=code, failed=failed_steps + failed_checks)
    return code, receipt


def _first_ts(entries: list) -> str:
    return next((e["ts"] for e in entries if e.get("ts")), journal_mod.utc_now())


__all__ = ["verify_run", "VerifyView", "acceptance", "tier_status"]
