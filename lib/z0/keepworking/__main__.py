"""python3 -m z0.keepworking check [--ledger PATH] | hook"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import hook, ledger


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="z0-keepworking")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="show which asks forbid stopping")
    c.add_argument("--ledger", type=Path, default=ledger.DEFAULT_LEDGER)
    sub.add_parser("hook", help="run as a Claude Code Stop hook (stdin JSON)")
    args = ap.parse_args(argv)
    if args.cmd == "hook":
        return hook.main()
    loaded = ledger.load(args.ledger)
    print(f"ledger: {loaded.state.name} {loaded.error}".rstrip())
    for e in loaded.entries:
        mark = "ok  " if e.ok else "OPEN"
        print(f"{mark} {e.id:32} {e.status.name.lower():8} {e.why}")
    print(f"stop permitted: {loaded.state.name == 'OK' and loaded.all_ok}")
    return 0 if loaded.state.name == "OK" and loaded.all_ok else 3


if __name__ == "__main__":
    sys.exit(main())
