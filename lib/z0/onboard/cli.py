"""`./z0 onboard ...` (design §1.2). Work package Z1 ships `detect` and `plan`.

Dry-run purity (law P0): `detect` writes nothing; `plan` writes only the origin
mirrors under $Z0_HOME/cache/git/ (§6.2) and its run dir under $Z0_HOME/onboard/runs/;
with `--stdout` (or `--host`) it writes nothing at all.
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
LATER = {"apply": "Z2", "verify": "Z2", "rollback": "Z2", "accept": "Z2", "status": "Z2",
         "pair": "Z4"}


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
    run = write_run_dir(host, plan_obj)
    sys.stdout.write(summary_text(plan_obj, run))
    if bare and not args.plan_only:
        print("apply arrives in work package Z2; this run stopped after the plan.")
    return exit_code(plan_obj)


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "detect":
        host, _ = run_detect()
        sys.stdout.write(json.dumps(host, indent=2, sort_keys=True) + "\n")
        return 0
    if args.cmd == "plan":
        return cmd_plan(args)
    if args.cmd in LATER:
        print(f"z0 onboard {args.cmd}: arrives in work package {LATER[args.cmd]}", file=sys.stderr)
        return 2
    return cmd_plan(args, bare=True)
