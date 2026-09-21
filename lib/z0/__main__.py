"""python -m z0 entrypoint."""

from __future__ import annotations

import argparse
import sys

from . import commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="z0", description="Zer0 map, installer, and registry CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Clone and set up a profile")
    p_init.add_argument("--profile", "-p", help="Profile name (core, personal, desktop, …)")
    p_init.add_argument("--dry-run", action="store_true", help="Print plan without cloning")

    p_add = sub.add_parser("add", help="Add a single component")
    p_add.add_argument("component", help="Component id")

    sub.add_parser("doctor", help="Verify installed components and interface owners")
    sub.add_parser("status", help="Development state table")

    p_graph = sub.add_parser("graph", help="Dependency graph")
    p_graph.add_argument("--mermaid", action="store_true")
    p_graph.add_argument("--json", action="store_true")

    p_docs = sub.add_parser("docs", help="Documentation tools")
    p_docs_sub = p_docs.add_subparsers(dest="docs_cmd")
    p_docs_sub.add_parser("generate", help="Regenerate docs from registry")

    p_reg = sub.add_parser(
        "registry",
        help="Federated almanac tools — validate, and discover live upstream heads",
    )
    p_reg_sub = p_reg.add_subparsers(dest="registry_cmd")
    p_reg_doctor = p_reg_sub.add_parser(
        "doctor",
        help="Validate the registry and report LIVE upstream heads (never committed)",
    )
    p_reg_doctor.add_argument("--write", action="store_true",
                              help="Cache discovered heads under .z0-cache/ (gitignored)")
    p_reg_doctor.add_argument("--json", action="store_true")

    p_cog = sub.add_parser(
        "cognition",
        help="Local cognition portfolio — stage map, owners, and the z0intelligence manifest",
    )
    p_cog_sub = p_cog.add_subparsers(dest="cognition_cmd")
    p_cog_portfolio = p_cog_sub.add_parser(
        "portfolio", help="Dataflow plus the live model rows read from z0intelligence"
    )
    p_cog_portfolio.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "init":
        return commands.cmd_init(profile=args.profile, dry_run=args.dry_run)
    if args.cmd == "add":
        return commands.cmd_add(args.component)
    if args.cmd == "doctor":
        return commands.cmd_doctor()
    if args.cmd == "status":
        return commands.cmd_status()
    if args.cmd == "graph":
        fmt = "mermaid" if args.mermaid else "json" if args.json else "text"
        return commands.cmd_graph(fmt)
    if args.cmd == "docs" and args.docs_cmd == "generate":
        return commands.cmd_docs_generate()
    if args.cmd == "registry" and args.registry_cmd == "doctor":
        return commands.cmd_registry_doctor(write_cache=args.write, as_json=args.json)
    if args.cmd == "cognition" and args.cognition_cmd == "portfolio":
        return commands.cmd_cognition_portfolio(as_json=args.json)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
