"""APPLY (design §6.3): run a plan that is already written, identified by its hash.

1. Take the lock (§1.4), then check the plan hash (the run dir is named after it).
2. Freshness: re-detect, compare the volatile facts (freshness.py) and re-plan on
   drift with the same grants; the kernel (decide_replan) says continue-and-show-diff
   or stop-and-confirm-again. `--yes` cannot widen a grant.
3. For each step, in plan order: only `todo` steps run, and only after the kernel says
   ALLOW again for the step's consent class (a C2 step is never run automatically, an
   ungranted C1 step never runs; `ask` steps never execute). Then the probe is re-run
   (skip if satisfied), the action runs with the prepared env, every effect is
   journaled, and a failure blocks only the steps that depend on it.
4. Failure triage without an LLM takes the safe default (`mark_unavailable`, no retry);
   a failed install is always reported as a failure (exit 1).
5. `workspace.yaml` gets host_id, components.<id>.{path, branch, ref} and
   onboard.<id>.release; `$Z0_HOME/onboard/current` points at this run. Both journaled.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import freshness, journal as journal_mod, kernel as k, lock as lock_mod
from .actions import ACTIONS, LATER, ActionCtx, ActionError
from .actions.base import subprocess_runner
from .plan import EFFECTFUL, plan_hash
from .redact import from_env
from .util import parse_requirement

PLAN_FILES = ("plan.replan.json", "plan.json")


class ApplyError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Deps:
    """Everything APPLY/VERIFY/ROLLBACK touch outside pure data; tests replace it."""
    z0_home: str
    home: str
    repo_root: str
    snap: dict
    base_env: dict = field(default_factory=lambda: dict(os.environ))
    runner: Callable = subprocess_runner
    urls: dict = field(default_factory=dict)
    fetch: Optional[Callable] = None
    detect: Optional[Callable] = None            # () -> host.json (freshness re-detect)
    replan: Optional[Callable] = None            # (host, request) -> plan
    confirm: Optional[Callable] = None           # (lines) -> bool; None: no TTY
    out: Callable = print


@dataclass
class ApplyResult:
    code: int
    plan: dict
    host: dict
    results: dict
    ctx: Optional[ActionCtx] = None


def runs_dir(z0_home) -> Path:
    return Path(z0_home) / "onboard" / "runs"


def run_dir_for(z0_home, run_id: Optional[str]) -> Path:
    """`runs/<run-id>`, or the run `onboard/current` points at."""
    if run_id:
        if "/" in run_id or run_id in (".", ".."):
            raise ApplyError(2, f"not a run id: {run_id}")
        path = runs_dir(z0_home) / run_id
    else:
        current = Path(z0_home) / "onboard" / "current"
        if not current.is_symlink():
            raise ApplyError(2, "no applied run yet (no $Z0_HOME/onboard/current)")
        path = (current.parent / os.readlink(current)).resolve()
    if not (path / "plan.json").is_file():
        raise ApplyError(2, f"no such run: {run_id or path.name}")
    return path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def effective_plan(run: Path) -> dict:
    for name in PLAN_FILES:
        if (run / name).is_file():
            return load_json(run / name)
    raise ApplyError(2, f"no plan in {run.name}")


def check_hash(run: Path, plan_obj: dict) -> None:
    """The plan is identified by its hash: content, recorded hash and run id agree."""
    if plan_hash(plan_obj) != plan_obj.get("plan_hash"):
        raise ApplyError(4, f"{run.name}/plan.json does not match its plan_hash (edited?); refused")
    if not run.name.endswith("-" + plan_obj["plan_hash"][:8]):
        raise ApplyError(4, f"run {run.name} does not name plan {plan_obj['plan_hash'][:8]}; refused")


def write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())


def request_from_plan(plan_obj: dict, snap: dict) -> dict:
    """The plan inputs a freshness re-plan reuses, read back from plan.json itself:
    mode, profile, grants, pin policy, LLM mode, and the --with/--without ids that turn
    the profile (plus the auto supplementals) into the plan's target set."""
    from . import regsnap

    profile = plan_obj.get("profile") or None
    base = regsnap.resolve_profile(snap, profile) if profile in regsnap.profiles(snap) else []
    for cid in regsnap.profile_policy(snap).get("auto_supplementals") or []:
        if cid not in base:
            base.append(cid)
    targets = list(plan_obj.get("targets") or [])
    return {"mode": plan_obj.get("mode", "auto"), "profile": profile,
            "with_ids": [c for c in targets if c not in base],
            "without_ids": [c for c in base if c not in targets],
            "grants": plan_obj.get("grants"), "pin_policy": plan_obj.get("pin_policy", "pinned"),
            "llm": plan_obj.get("llm", "local"),
            **({"answers": {"llm": {r["question_id"]: r for r in plan_obj["llm_decisions"]}}}
               if plan_obj.get("llm_decisions") else {})}


def _todo_c1(plan_obj: dict, before: Optional[dict] = None) -> list:
    seen = {e["step"]["id"] for e in (before or {}).get("steps", []) if e["state"]["status"] == "todo"}
    return [e["step"] for e in plan_obj["steps"] if e["state"]["status"] == "todo"
            and e["step"]["consent"]["class"] != "C0" and e["step"]["id"] not in seen]


def freshen(run: Path, plan_obj: dict, deps: Deps, yes: bool, journal) -> tuple:
    """§6.3 step 2. Returns (plan to apply, current host)."""
    recorded = load_json(run / "host.json")
    if deps.detect is None:
        return plan_obj, recorded
    host = deps.detect()
    verdict = k.decide_host(k.host_match(plan_obj.get("host_id"), host.get("host_id")))
    if verdict.kind is not k.Kind.ALLOW:
        raise ApplyError(4, "this plan was made on another host (H1); refused")
    changed = freshness.drift(recorded, host)
    if not changed:
        return plan_obj, host
    request = request_from_plan(plan_obj, deps.snap)
    if deps.replan is None:
        raise ApplyError(1, f"host changed since the plan ({', '.join(changed)}) and no re-plan is available")
    new_plan = deps.replan(host, request)
    decision = freshness.decide(recorded, host, plan_obj, new_plan, yes)
    deps.out(f"host changed since the plan ({', '.join(changed)}); re-planned "
             f"{plan_obj['plan_hash'][:12]} -> {new_plan['plan_hash'][:12]}")
    for line in freshness.diff_lines(plan_obj, new_plan):
        deps.out(f"  {line}")
    if decision is k.Replan.RECONFIRM:
        lines = [f"{s['id']} ({s['consent']['class']}"
                 f"{', ' + s['consent']['bundle'] if s['consent'].get('bundle') else ''})"
                 for s in _todo_c1(new_plan, plan_obj)]
        if deps.confirm is None or not deps.confirm(
                ["The re-plan adds steps you have not confirmed:"] + [f"  {l}" for l in lines]):
            journal.write("replan", plan_hash=new_plan["plan_hash"], decision="reconfirm_declined")
            raise ApplyError(3, "the re-plan would widen what you confirmed; nothing applied. "
                                "Re-run ./z0 onboard to confirm the new plan.")
    if new_plan.get("llm_decisions"):
        from .plan import collect_questions
        from .llm.resolve import frozen_envelope
        answers = {"llm": {r["question_id"]: r for r in new_plan["llm_decisions"]}}
        envelope = frozen_envelope(collect_questions(host, deps.snap), new_plan["mode"],
                                   new_plan["grants"], new_plan["llm"], new_plan["host_id"], answers)
        write_private(run / "answers.replan.yaml", json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    write_private(run / "plan.replan.json", json.dumps(new_plan, indent=2, sort_keys=True) + "\n")
    journal.write("replan", plan_hash=new_plan["plan_hash"], decision=decision.name.lower(),
                  drift=changed)
    return new_plan, host


def _tool_users(snap: dict) -> dict:
    """toolchain step id -> components that require that tool (blocking on failure)."""
    from .plan import _canonical_tool  # same canonical names the plan used
    specs = (snap.get("toolchains") or {}).get("tools") or {}
    users: dict = {}
    for cid, comp in ((snap.get("components") or {}).get("components") or {}).items():
        for req in ((comp.get("onboard") or {}).get("requires") or {}).get("tools") or []:
            tool, _ = parse_requirement(str(req))
            users.setdefault(f"toolchain.{_canonical_tool(tool, specs)}", set()).add(cid)
    return users


def consent_verdict(plan_obj: dict, step: dict) -> k.Verdict:
    """The kernel, asked again right before a step runs (C1/C2/L-LLM)."""
    mode = k.Mode.AUTO if plan_obj.get("mode", "auto") == "auto" else k.Mode.GUIDED
    cls = k.ConsentClass[step["consent"]["class"]]
    grants = plan_obj.get("grants") or {}
    source = {"tty": k.Source.TTY, "llm": k.Source.LLM}.get(grants.get("source"), k.Source.FLAG)
    granted = (cls is k.ConsentClass.C1 and step["consent"].get("bundle") in (grants.get("bundles") or [])
               and ("steps" not in grants or step["id"] in grants["steps"]))
    return k.decide_consent(mode, cls, granted, source)


def satisfied_now(ctx: ActionCtx, step: dict) -> bool:
    """Re-run the step's probe (§6.3 step 3) before acting."""
    if step["kind"] in ("check", "ask"):
        return False
    probe = (step.get("probe") or {}).get("exists")
    paths = [probe] if probe else list(step.get("creates") or [])
    return bool(paths) and all(os.path.lexists(ctx.expand(p)) for p in paths)


def make_ctx(run: Path, plan_obj: dict, host: dict, deps: Deps, journal) -> ActionCtx:
    return ActionCtx(z0_home=deps.z0_home, home=deps.home, run_id=run.name, run_dir=run,
                     journal=journal, plan=plan_obj, snap=deps.snap, host=host,
                     repo_root=deps.repo_root, base_env=deps.base_env, runner=deps.runner,
                     urls=deps.urls, fetch=deps.fetch,
                     redactor=from_env(deps.snap, deps.base_env, deps.home))


def run_step(ctx: ActionCtx, step: dict) -> dict:
    """Execute one step; returns its result entry (never raises for a step failure)."""
    ctx.step_id = step["id"]
    action = ACTIONS.get(step["kind"])
    if action is None:
        later = LATER.get(step["kind"], "a later work package")
        return {"status": "failed", "reason": f"{step['kind']} steps arrive with {later}"}
    try:
        outcome = action(ctx, step)
    except ActionError as exc:
        return {"status": "failed", "reason": ctx.redactor(str(exc))}
    except OSError as exc:
        return {"status": "failed", "reason": ctx.redactor(f"{exc.__class__.__name__}: {exc.strerror}")}
    result = {"status": "passed" if outcome.ok else "failed", "reason": ctx.redactor(outcome.detail)}
    if outcome.output:
        result["output"] = ctx.redactor(outcome.output)
    return result


def execute_plan(ctx: ActionCtx, plan_obj: dict, deps: Deps) -> dict:
    """Run every todo step in order; failures block only their dependents."""
    journal = ctx.journal
    comps = (deps.snap.get("components") or {}).get("components") or {}
    users = _tool_users(deps.snap)
    results: dict = {}
    bad: set = set()           # failed or blocked step ids
    bad_components: set = set()
    for entry in plan_obj["steps"]:
        step, state = entry["step"], entry["state"]
        sid, cid = step["id"], step.get("component")
        if state["status"] != "todo":
            results[sid] = {"status": state["status"], "reason": state.get("reason", "")}
            continue
        blocker = next((n for n in step.get("needs") or [] if n in bad), None)
        source = step["kind"] == "adopt_or_clone"   # needs only git (plan.py, same rule)
        if blocker is None and cid:
            blocker = next((t for t, who in users.items() if t in bad and cid in who
                            and (not source or t == "toolchain.git")), None)
        if blocker is None and cid:
            blocker = next((d for d in (comps.get(cid) or {}).get("depends_on") or []
                            if d in bad_components), None)
        if blocker is not None:
            results[sid] = {"status": "blocked", "reason": f"dependency {blocker} failed"}
        elif step["kind"] == "ask":
            results[sid] = {"status": "ask", "reason": "manual step, never executed"}
        else:
            verdict = consent_verdict(plan_obj, step)
            if verdict.kind is not k.Kind.ALLOW:
                results[sid] = {"status": "refused",
                                "reason": f"kernel: {verdict.kind.name.lower()} "
                                          f"({verdict.reason.name.lower()})"}
            elif satisfied_now(ctx, step):
                results[sid] = {"status": "already_satisfied", "reason": "probe satisfied"}
            else:
                journal.write("step", step=sid, status="begin", kind=step["kind"])
                deps.out(f"  {step['kind']:16} {sid} ...")
                results[sid] = run_step(ctx, step)
                if results[sid]["status"] == "failed":
                    results[sid]["remediation"] = "mark_unavailable"
        status = results[sid]["status"]
        journal.write("step", step=sid, status=status, reason=results[sid].get("reason", ""),
                      **({"remediation": results[sid]["remediation"]} if "remediation" in results[sid] else {}))
        if status in ("failed", "blocked", "refused"):
            bad.add(sid)
            if cid and cid != "z0" and status == "failed":
                bad_components.add(cid)
            if status == "failed":
                deps.out(f"  FAILED {sid}: {results[sid]['reason']}")
    return results


def _dump_yaml(data: dict) -> str:
    import yaml
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def workspace_update(ctx: ActionCtx, plan_obj: dict, results: dict) -> None:
    """§6.3 step 6: additive keys; `registry.py` ignores the ones it does not know."""
    import yaml

    path = os.path.join(ctx.z0_home, "workspace.yaml")
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError:
        data = {}
    if not isinstance(data, dict):
        return
    before = _dump_yaml(data) if data else ""
    data.setdefault("version", 1)
    data.setdefault("root", _home_form(ctx, os.path.join(ctx.z0_home, "repos")))
    data["host_id"] = plan_obj["host_id"]
    comps = data.setdefault("components", {}) or {}
    data["components"] = comps
    onboard = data.setdefault("onboard", {}) or {}
    data["onboard"] = onboard
    ok = ("passed", "already_satisfied")
    for entry in plan_obj["steps"]:
        step = entry["step"]
        cid = step.get("component")
        if not cid or cid == "z0" or results.get(step["id"], {}).get("status") not in ok:
            continue
        comp = ctx.component(cid)
        if step["kind"] == "adopt_or_clone":
            tree = ctx.tree(cid)
            comps[cid] = {"path": _home_form(ctx, tree), "branch": (comp.get("install") or {}).get("branch"),
                          "ref": (comp.get("install") or {}).get("ref")}
        elif step["kind"] in ("stage_release", "swap_current") and step.get("creates"):
            onboard.setdefault(cid, {})["release" if step["kind"] == "stage_release" else "current"] = \
                _home_form(ctx, ctx.expand(step["creates"][0]))
    text = _dump_yaml(data)
    if text != before:
        ctx.step_id = "z0.workspace"
        ctx.write_file(path, text.encode("utf-8"), 0o600)


def _home_form(ctx: ActionCtx, path: str) -> str:
    """`~/...` (expanduser-able, as `z0 doctor` reads it), never an absolute home path."""
    path = os.path.abspath(path)
    if path == ctx.home or path.startswith(ctx.home + "/"):
        return "~" + path[len(ctx.home):]
    return path


def point_current(ctx: ActionCtx, run: Path) -> None:
    link = os.path.join(ctx.z0_home, "onboard", "current")
    target = os.path.join("runs", run.name)
    if os.path.islink(link) and os.readlink(link) == target:
        return
    ctx.step_id = "z0.current"
    ctx.symlink(link, target)


def apply_run(run: Path, deps: Deps, *, yes: bool = False) -> ApplyResult:
    plan_obj = load_json(run / "plan.json")
    check_hash(run, plan_obj)
    with lock_mod.hold(deps.z0_home):
        journal = journal_mod.Journal(run / "journal.jsonl", run.name)
        plan_obj, host = freshen(run, plan_obj, deps, yes, journal)
        journal.write("apply_start", plan_hash=plan_obj["plan_hash"])
        ctx = make_ctx(run, plan_obj, host, deps, journal)
        results = execute_plan(ctx, plan_obj, deps)
        workspace_update(ctx, plan_obj, results)
        point_current(ctx, run)
        failed = [sid for sid, r in results.items() if r["status"] == "failed"]
        journal.write("apply_done", failed=failed)
    code = 1 if failed else 0
    return ApplyResult(code, plan_obj, host, results, ctx)


def effectful_todo(plan_obj: dict) -> list:
    return [e["step"]["id"] for e in plan_obj["steps"]
            if e["state"]["status"] == "todo" and e["step"]["kind"] in EFFECTFUL]
