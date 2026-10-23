"""python -m z0 entrypoint."""

from __future__ import annotations

import argparse
import sys

from . import bindings, commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="z0", description="Zer0 map, installer, and registry CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Clone and set up a profile")
    p_init.add_argument("--profile", "-p", help="Profile name (core, personal, desktop, …)")
    p_init.add_argument("--dry-run", action="store_true", help="Print plan without cloning")

    p_add = sub.add_parser("add", help="Add a single component")
    p_add.add_argument("component", help="Component id")

    p_doctor = sub.add_parser("doctor", help="Inspect installed components or native binding drift")
    p_doctor.add_argument("--bindings", action="store_true", help="Read-only native binding observation")
    p_doctor.add_argument("--json", action="store_true", help="Emit one machine-readable binding observation")
    p_doctor.add_argument("--receipt", help="New JSON observation receipt path (never overwritten)")

    p_apply = sub.add_parser("apply", help="Reconcile owned native config fragments (dry-run by default)")
    mode = p_apply.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print masked diffs without config writes")
    mode.add_argument("--apply", action="store_true", help="Write owned keys after timestamped backups")
    p_apply.add_argument("--yes", action="store_true", help="Authorize --apply config writes")
    for native in (p_doctor, p_apply):
        native.add_argument("--host", help="Local host name (remote access is not supported)")
        native.add_argument("--harness", choices=bindings.HARNESSES, help="Limit to one native harness")
        native.add_argument("--harness-profile", help="Limit --harness hermes to one native profile")
        intent = native.add_mutually_exclusive_group()
        intent.add_argument("--profile", help="Desired z0 component profile")
        intent.add_argument("--components", help="Desired comma-separated component ids (empty means none)")
        intent.add_argument("--host-profile", help="Host intent YAML or .files fleet.toml input")
    sub.add_parser("status", help="Development state table")

    p_graph = sub.add_parser("graph", help="Dependency graph")
    p_graph.add_argument("--mermaid", action="store_true")
    p_graph.add_argument("--json", action="store_true")

    p_docs = sub.add_parser("docs", help="Documentation tools")
    p_docs_sub = p_docs.add_subparsers(dest="docs_cmd")
    p_docs_sub.add_parser("generate", help="Regenerate docs from registry")

    args = parser.parse_args(argv)
    if args.cmd == "init":
        return commands.cmd_init(profile=args.profile, dry_run=args.dry_run)
    if args.cmd == "add":
        return commands.cmd_add(args.component)
    if args.cmd in {"doctor", "apply"}:
        native = {key: getattr(args, key) for key in (
            "host", "harness", "harness_profile", "profile", "components", "host_profile")}
        if args.cmd == "apply":
            return bindings.cmd_apply(dry_run=args.dry_run, apply=args.apply, yes=args.yes, **native)
        if args.bindings:
            return bindings.cmd_doctor(receipt=args.receipt, json_output=args.json, **native)
        if any(value is not None for value in native.values()) or args.receipt or args.json:
            parser.error("native config options require doctor --bindings")
        return commands.cmd_doctor()
    if args.cmd == "status":
        return commands.cmd_status()
    if args.cmd == "graph":
        fmt = "mermaid" if args.mermaid else "json" if args.json else "text"
        return commands.cmd_graph(fmt)
    if args.cmd == "docs" and args.docs_cmd == "generate":
        return commands.cmd_docs_generate()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
