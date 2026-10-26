"""`./z0 onboard ...` (design §1.2): detect, plan, (confirm), apply, verify, rollback.

Dry-run purity (law P0): `detect` writes nothing; `plan` writes only the origin
mirrors under $Z0_HOME/cache/git/ (§6.2) and its run dir under $Z0_HOME/onboard/runs/;
with `--stdout` (or `--host`) it writes nothing at all.

Consent (§3, owner decision D-1): C0 always applies. C1 runs only for granted bundles:
`--yes` grants all, `--accept B,..` a subset, and on a TTY `--auto` shows ONE
enumerated go/no-go confirmation. Without a TTY and without a grant, C1 stays an ask,
C0 still applies, and the run exits 3. C2 is never automatic. The kernel decides every
step, at plan time and again right before it runs.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Optional

BUNDLES = ("toolchains", "harness", "services", "models")
LATER = {"accept": "Z6", "status": "Z6", "pair": "Z4"}


def _ids(text: Optional[str]) -> list:
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def _common(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--auto", dest="mode", action="store_const", const="auto",
                      help="no choice questions; hardware-default profile")
    mode.add_argument("--guided", dest="mode", action="store_const", const="guided",
                      help="ask every choice (needs a TTY)")
    parser.add_argument("--yes", action="store_true", help="grant every C1 bundle")
    parser.add_argument("--accept", metavar="BUNDLES", help=f"grant a subset of {','.join(BUNDLES)}")
    parser.add_argument("--profile", help="install profile (default: decided from hardware)")
    parser.add_argument("--with", dest="with_ids", metavar="IDS", help="extra components")
    parser.add_argument("--without", dest="without_ids", metavar="IDS", help="drop components")
    parser.add_argument("--pin-policy", choices=("pinned", "tip"), default="pinned")
    parser.add_argument("--llm", choices=("none", "local", "auto"), default="local")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="z0 onboard", description="Onboard this host (design §1)")
    _common(parser)
    parser.add_argument("--plan-only", action="store_true", help="stop after the plan")
    sub = parser.add_subparsers(dest="cmd")
    p_plan = sub.add_parser("plan", help="dry run: detect, then plan")
    _common(p_plan)
    p_plan.add_argument("--stdout", action="store_true", help="print plan.json; write nothing")
    p_plan.add_argument("--check-deterministic", action="store_true",
                        help="plan twice from one detection and compare plan hashes")
    p_plan.add_argument("--host", metavar="HOST_JSON", help="plan from a recorded host.json")
    sub.add_parser("detect", help="print host.json (read-only; writes nothing)")
    p_apply = sub.add_parser("apply", help="apply a written plan, checked by its hash")
    p_apply.add_argument("run_id", help="a run under $Z0_HOME/onboard/runs/")
    p_apply.add_argument("--yes", action="store_true",
                         help="accepted for symmetry; it never widens the plan's grants")
    p_verify = sub.add_parser("verify", help="acceptance checks; writes receipt.json and report.md")
    p_verify.add_argument("run_id", nargs="?", help="default: the current run")
    p_back = sub.add_parser("rollback", help="undo a run from its journal (owned artifacts only)")
    p_back.add_argument("run_id", nargs="?", help="default: the current run")
    p_back.add_argument("--purge-bootstrap", action="store_true",
                        help="also remove stage 0's $Z0_HOME/{bootstrap,venv}")
    p_back.add_argument("--purge", action="store_true", help="also remove the cache/git mirrors")
    for name in LATER:
        later = sub.add_parser(name, help=f"arrives in work package {LATER[name]}")
        later.add_argument("rest", nargs="*")
    return parser


def _grants(args) -> dict:
    if args.yes:
        return {"bundles": list(BUNDLES), "source": "flag"}
    accepted = _ids(args.accept)
    unknown = [b for b in accepted if b not in BUNDLES]
    if unknown:
        raise SystemExit(f"z0 onboard: unknown bundle(s): {', '.join(unknown)}")
    return {"bundles": accepted, "source": "flag" if accepted else "none"}


def _tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def run_detect(fetch: bool = False):
    """Detect this host. `fetch`: first bring every registry pin into its origin
    mirror (§6.2), so pin evidence does not depend on having a checkout. Skipped when
    the host is declared offline (Z0_DETECT_OFFLINE=1)."""
    from . import regsnap
    from .detect import Ctx, detect

    from . import mirror

    snap = regsnap.load()
    outcomes = {}
    online = fetch and os.environ.get("Z0_DETECT_OFFLINE") != "1"
    if online:
        outcomes = mirror.ensure(snap, str(_z0_home()))
    # §2.6: repo-local setup steps at each pin, from the mirror only. Without the fetch
    # (--stdout, detect) only what the mirror already holds is read: nothing is written.
    snap["repo_setups"] = mirror.read_setups(snap, str(_z0_home()), lazy=online)
    host = detect(Ctx(registry=snap, **sandbox_from_env(os.environ)))
    if outcomes:
        mirror.merge(host, outcomes, snap)
    return host, snap


def sandbox_from_env(env) -> dict:
    """Container and test hooks: point detect at a fake sysroot and system bin dirs,
    or declare the host offline, without touching the real host's probes."""
    kwargs: dict = {}
    if env.get("Z0_DETECT_SYSROOT"):
        kwargs["sysroot"] = env["Z0_DETECT_SYSROOT"]
    if env.get("Z0_DETECT_SYSTEM_DIRS"):
        kwargs["system_dirs"] = [d for d in env["Z0_DETECT_SYSTEM_DIRS"].split(os.pathsep) if d]
    if env.get("Z0_DETECT_OFFLINE") == "1":
        kwargs["http_head"] = lambda url, timeout: False
    return kwargs


def _choose_profile(args, snap) -> Optional[str]:
    if args.profile or args.mode != "guided":
        return args.profile
    if not _tty():
        print("z0 onboard: --guided needs a TTY (or pass --profile)", file=sys.stderr)
        raise SystemExit(2)
    from . import regsnap
    names = list(regsnap.profiles(snap))
    answer = input(f"profile [{'/'.join(names)}] (enter = hardware default): ").strip()
    if answer and answer not in names:
        print(f"z0 onboard: unknown profile {answer}", file=sys.stderr)
        raise SystemExit(2)
    return answer or None


def _make_plan(host, snap, args, profile):
    from .plan import plan
    return plan(host, snap, mode=args.mode, profile=profile, with_ids=_ids(args.with_ids),
                without_ids=_ids(args.without_ids), grants=_grants(args),
                pin_policy=args.pin_policy, llm=args.llm)


def _z0_home() -> Path:
    return Path(os.environ.get("Z0_HOME") or Path.home() / ".z0")


def _write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())


def write_run_dir(host: dict, plan_obj: dict) -> Path:
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = _z0_home() / "onboard" / "runs" / f"{stamp}-{plan_obj['plan_hash'][:8]}"
    old = os.umask(0o077)
    try:
        run.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(run, 0o700)
        _write_private(run / "host.json", json.dumps(host, indent=2, sort_keys=True) + "\n")
        _write_private(run / "plan.json", json.dumps(plan_obj, indent=2, sort_keys=True) + "\n")
        _write_private(run / "plan.diff.txt", diff_text(plan_obj))
    finally:
        os.umask(old)
    return run


def diff_text(plan_obj: dict) -> str:
    receipt = _z0_home() / "onboard" / "current" / "receipt.json"
    lines = [f"plan {plan_obj['plan_hash']}"]
    if not receipt.is_file():
        lines.append("no previous receipt: every step below is new")
    for entry in plan_obj["steps"]:
        status = entry["state"]["status"]
        if status != "already_satisfied":
            lines.append(f"{status:18} {entry['step']['id']}")
    return "\n".join(lines) + "\n"


def summary_text(plan_obj: dict, run: Optional[Path]) -> str:
    counts: dict = {}
    for entry in plan_obj["steps"]:
        counts[entry["state"]["status"]] = counts.get(entry["state"]["status"], 0) + 1
    out = [f"plan {plan_obj['plan_hash'][:12]}  mode={plan_obj['mode']}  "
           f"profile={plan_obj['profile'] or '-'}  targets={','.join(plan_obj['targets'])}",
           "steps: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
    if plan_obj["asks"]:
        out.append("What you need to do:")
        for ask in plan_obj["asks"]:
            out.append(f"  [{ask.get('consent', '')}] {ask['id']}: {ask['reason']}\n"
                       f"        {ask['command']}")
    if plan_obj.get("unavailable"):
        out.append("Unavailable:")
        for entry in plan_obj["unavailable"]:
            out.append(f"  {entry['id']}: {entry['status']} ({entry['detail']})")
    if plan_obj.get("conflicts"):
        out.append("Repo setup conflicts (zer0.repo.yaml vs the registry; the registry wins):")
        for conflict in plan_obj["conflicts"]:
            what = (f"same argv as registry step {conflict['registry_id']}"
                    if conflict.get("registry_id") else "differs in " + ", ".join(conflict["fields"]))
            out.append(f"  {conflict['id']}: {what} ({conflict['source']})")
    for warning in plan_obj["warnings"]:
        out.append(f"warning: {warning}")
    if run is not None:
        out.append(f"run dir: {run}")
    return "\n".join(out) + "\n"


def cmd_plan(args, bare: bool = False) -> int:
    from .plan import PlanError, exit_code

    if args.mode is None:
        args.mode = "auto"  # no TTY: same as --auto (§1.1)
        if bare and _tty():
            answer = input("auto or guided? [auto]: ").strip().lower()
            args.mode = "guided" if answer in ("g", "guided") else "auto"
    if getattr(args, "host", None):
        from . import mirror, regsnap
        snap = regsnap.load()
        snap["repo_setups"] = mirror.read_setups(snap, str(_z0_home()), lazy=False)
        host = json.loads(Path(args.host).read_text(encoding="utf-8"))
        # H1: a host.json recorded elsewhere is never planned as this host.
        from .detect import Ctx, osinfo
        current = osinfo.detect(Ctx(registry=snap, **sandbox_from_env(os.environ)))["host_id"]
        if host.get("host_id") != current:
            host.setdefault("workspace", {})["host_match"] = "other"
    else:
        host, snap = run_detect(fetch=not getattr(args, "stdout", False))
    profile = _choose_profile(args, snap)
    try:
        plan_obj = _make_plan(host, snap, args, profile)
        if getattr(args, "check_deterministic", False):
            again = _make_plan(json.loads(json.dumps(host)), snap, args, profile)
            same = again["plan_hash"] == plan_obj["plan_hash"]
            print(f"{'deterministic' if same else 'NOT deterministic'} {plan_obj['plan_hash']}")
            return 0 if same else 1
    except PlanError as exc:
        print(f"z0 onboard: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "stdout", False):
        sys.stdout.write(json.dumps(plan_obj, indent=2, sort_keys=True) + "\n")
        return exit_code(plan_obj)
    if bare and not args.plan_only and exit_code(plan_obj) == 0:
        return onboard(args, host, snap, profile, plan_obj)
    run = write_run_dir(host, plan_obj)
    sys.stdout.write(summary_text(plan_obj, run))
    return exit_code(plan_obj)


# --- apply / verify / rollback (work package Z2) -----------------------------------

def replan_from(snap: dict) -> "callable":
    from .plan import plan

    def replan(host: dict, request: dict) -> dict:
        return plan(host, snap, mode=request.get("mode", "auto"), profile=request.get("profile"),
                    with_ids=request.get("with_ids") or [], without_ids=request.get("without_ids") or [],
                    grants=request.get("grants"), pin_policy=request.get("pin_policy", "pinned"),
                    llm=request.get("llm", "local"))
    return replan


def _confirm(lines: list) -> bool:
    for line in lines:
        print(line)
    try:
        answer = input("Proceed? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def make_deps(snap: dict, *, detect: bool):
    from . import regsnap
    from .apply import Deps

    def redetect():
        host, _ = run_detect(fetch=False)
        return host

    return Deps(z0_home=str(_z0_home()), home=os.environ.get("HOME") or str(Path.home()),
                repo_root=str(regsnap.ROOT), snap=snap, detect=redetect if detect else None,
                replan=replan_from(snap), confirm=_confirm if _tty() else None)


def _outside_z0(step: dict) -> list:
    paths = list(step.get("creates") or []) + ([step["probe"]["exists"]]
                                               if (step.get("probe") or {}).get("exists") else [])
    return [p for p in paths if not p.startswith("$Z0_HOME")]


def confirmation_lines(base: dict, candidate: dict) -> tuple:
    """(lines, needed bundles, newly granted C1 steps) for the ONE go/no-go (D-1)."""
    from .plan import _c1_reason

    before = {e["step"]["id"]: e["state"] for e in base["steps"]}
    todo = [e["step"] for e in candidate["steps"] if e["state"]["status"] == "todo"]
    new_c1 = [s for s in todo if s["consent"]["class"] == "C1"
              and before.get(s["id"], {}).get("status") != "todo"]
    outside = [s for s in todo if s["consent"]["class"] == "C0" and _outside_z0(s)]
    bundles = sorted({s["consent"].get("bundle", "") for s in new_c1})
    lines = [f"Apply {len(todo)} steps; {len(new_c1) + len(outside)} write outside ~/.z0:"]
    for bundle in bundles:
        lines.append(f"  [{bundle}]")
        lines += [f"    {s['id']}: {_c1_reason(s)}" for s in new_c1 if s["consent"].get("bundle") == bundle]
    if outside:
        lines.append("  [repo-local, C0]")
        lines += [f"    {s['id']}: {', '.join(_outside_z0(s))}" for s in outside]
    return lines, bundles, new_c1


def _consent(args, host, snap, profile, plan_obj) -> tuple:
    """Returns (plan to apply, consent exit code, abort code or None)."""
    if args.yes or plan_obj["grants"]["source"] != "none":
        return plan_obj, 0, None
    from .plan import plan

    candidate = plan(host, snap, mode=args.mode, profile=profile, with_ids=_ids(args.with_ids),
                     without_ids=_ids(args.without_ids),
                     grants={"bundles": list(BUNDLES), "source": "tty"},
                     pin_policy=args.pin_policy, llm=args.llm)
    lines, bundles, new_c1 = confirmation_lines(plan_obj, candidate)
    if len(lines) == 1:
        return plan_obj, 0, None
    if not _tty():
        if new_c1:
            print(f"z0 onboard: {len(new_c1)} C1 step(s) need consent and there is no TTY; "
                  "they stay asks (re-run with --yes, or --accept "
                  f"{','.join(bundles)}). C0 steps still apply.", file=sys.stderr)
        return plan_obj, 3 if new_c1 else 0, None
    granted = list(bundles)
    if args.mode == "guided":
        granted = [b for b in bundles if _confirm([f"Grant the {b} bundle?"] +
                                                  [l for l in lines if l.startswith("    ")])]
    elif not _confirm(lines):
        print("z0 onboard: nothing applied (declined). `--accept BUNDLES` grants a subset.")
        return plan_obj, 3, 3
    if not granted:
        return plan_obj, 3 if new_c1 else 0, None
    granted_plan = plan(host, snap, mode=args.mode, profile=profile, with_ids=_ids(args.with_ids),
                        without_ids=_ids(args.without_ids),
                        grants={"bundles": granted, "source": "tty"},
                        pin_policy=args.pin_policy, llm=args.llm)
    left = [e for e in granted_plan["steps"] if e["state"].get("reason") == "c1_ungranted"]
    return granted_plan, 3 if left else 0, None


def onboard(args, host, snap, profile, plan_obj) -> int:
    """The bare `./z0 onboard`: (confirm), write the run, apply, verify (§1.1)."""
    from .apply import ApplyError, apply_run
    from .lock import LockHeld
    from .verify import verify_run

    plan_obj, consent_code, abort = _consent(args, host, snap, profile, plan_obj)
    run = write_run_dir(host, plan_obj)
    sys.stdout.write(summary_text(plan_obj, run))
    if abort is not None:
        return abort
    from .lock import hold

    deps = make_deps(snap, detect=False)
    try:
        result = apply_run(run, deps, yes=args.yes)
        with hold(deps.z0_home):
            code, receipt = verify_run(run, deps, prior=result.results, host=result.host,
                                       apply_code=result.code, consent_code=consent_code)
    except LockHeld as exc:
        print(f"z0 onboard: {exc}", file=sys.stderr)
        return 1
    except ApplyError as exc:
        print(f"z0 onboard: {exc}", file=sys.stderr)
        return exc.code
    _handoff(run, receipt, snap, result.host)
    print(receipt_summary(run, receipt))
    return code


def _handoff(run: Path, receipt: dict, snap: dict, host: Optional[dict]) -> None:
    """CW7: the state and profile files `z0int contribute` reads (handoff.py)."""
    from . import handoff
    from .redact import from_env

    home = os.environ.get("HOME") or str(Path.home())
    redactor = from_env(snap, dict(os.environ), home)
    try:
        handoff.write_state(str(_z0_home()), run, receipt, str(_repo_root()), redactor)
    except (OSError, ValueError) as exc:
        print(f"z0 onboard: onboard/state not written ({exc})", file=sys.stderr)
    handoff.write_profile(str(_z0_home()), host, snap, redactor)


def _repo_root() -> Path:
    from . import regsnap
    return Path(regsnap.ROOT)


def receipt_summary(run: Path, receipt: dict) -> str:
    counts: dict = {}
    for step in receipt["steps"]:
        counts[step["status"]] = counts.get(step["status"], 0) + 1
    lines = ["steps: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
    for cid, tiers in sorted(receipt["acceptance"].items()):
        lines.append(f"  {cid}: " + ", ".join(f"{n} {s}" for n, s in tiers.items()))
    for step in receipt["steps"]:
        if step["status"] == "failed":
            lines.append(f"FAILED {step['id']}: {step.get('reason', '')}")
    lines.append(f"exit {receipt['exit_code']}; report: {run / 'report.md'}")
    return "\n".join(lines)


def _snap() -> dict:
    from . import mirror, regsnap
    snap = regsnap.load()
    snap["repo_setups"] = mirror.read_setups(snap, str(_z0_home()), lazy=False)
    return snap


def cmd_apply(args) -> int:
    from .apply import ApplyError, apply_run, run_dir_for
    from .lock import LockHeld

    try:
        run = run_dir_for(_z0_home(), args.run_id)
        snap = _snap()
        result = apply_run(run, make_deps(snap, detect=True), yes=args.yes)
    except LockHeld as exc:
        print(f"z0 onboard apply: {exc}", file=sys.stderr)
        return 1
    except ApplyError as exc:
        print(f"z0 onboard apply: {exc}", file=sys.stderr)
        return exc.code
    failed = [sid for sid, r in result.results.items() if r["status"] == "failed"]
    print(f"applied {run.name}: {len(failed)} failed step(s). Next: ./z0 onboard verify {run.name}")
    return result.code


def cmd_verify(args) -> int:
    from .apply import ApplyError, run_dir_for
    from .lock import LockHeld, hold
    from .verify import verify_run

    try:
        run = run_dir_for(_z0_home(), args.run_id)
        snap = _snap()
        with hold(_z0_home()):
            code, receipt = verify_run(run, make_deps(snap, detect=False))
    except LockHeld as exc:
        print(f"z0 onboard verify: {exc}", file=sys.stderr)
        return 1
    except ApplyError as exc:
        print(f"z0 onboard verify: {exc}", file=sys.stderr)
        return exc.code
    _handoff(run, receipt, snap, None)
    print(receipt_summary(run, receipt))
    return code


def cmd_rollback(args) -> int:
    from .apply import ApplyError, run_dir_for
    from .lock import LockHeld
    from .rollback import purge, rollback_run

    try:
        run = run_dir_for(_z0_home(), args.run_id)
        counts = rollback_run(run, str(_z0_home()), os.environ.get("HOME") or str(Path.home()))
    except LockHeld as exc:
        print(f"z0 onboard rollback: {exc}", file=sys.stderr)
        return 1
    except ApplyError as exc:
        print(f"z0 onboard rollback: {exc}", file=sys.stderr)
        return exc.code
    print(f"rolled back {run.name}: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to undo"))
    from . import handoff
    handoff.mark_rolled_back(str(_z0_home()), run.name)
    if args.purge:
        print("purged: " + (", ".join(purge(str(_z0_home()), "cache")) or "nothing"))
    if args.purge_bootstrap:
        print("purged: " + (", ".join(purge(str(_z0_home()), "bootstrap")) or "nothing"))
    return 1 if counts.get("error") else 0


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "detect":
        host, _ = run_detect()
        sys.stdout.write(json.dumps(host, indent=2, sort_keys=True) + "\n")
        return 0
    if args.cmd == "plan":
        return cmd_plan(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "rollback":
        return cmd_rollback(args)
    if args.cmd in LATER:
        print(f"z0 onboard {args.cmd}: arrives in work package {LATER[args.cmd]}", file=sys.stderr)
        return 2
    return cmd_plan(args, bare=True)
