"""z0 CLI commands — init, doctor, graph, status."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import cognition, generate, registry


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)


def _git_head(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    try:
        r = _run(["git", "rev-parse", "HEAD"], cwd=path)
        return r.stdout.strip()[:12]
    except subprocess.CalledProcessError:
        return None


def _git_branch(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    try:
        r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
        return r.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def cmd_init(profile: str | None = None, dry_run: bool = False) -> int:
    if profile is None:
        print("What are you trying to build?\n")
        names = list(registry.profiles().keys())
        for i, name in enumerate(names, 1):
            summary = registry.profiles()[name].get("summary", "")
            print(f"  [{i}] {name:10} — {summary}")
        choice = input("\nProfile [core]: ").strip() or "core"
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            profile = names[int(choice) - 1]
        else:
            profile = choice
    try:
        component_ids = registry.resolve_profile(profile)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ws = registry.load_workspace()
    ws["profile"] = profile
    root = Path(ws.get("root", registry.z0_home() / "repos")).expanduser()
    if not dry_run:
        root.mkdir(parents=True, exist_ok=True)
    ws.setdefault("components", {})

    print(f"\nProfile: {profile}")
    print(f"Root:    {root}\n")
    comps = registry.components()
    for cid in component_ids:
        meta = comps.get(cid)
        if not meta:
            print(f"  skip unknown component: {cid}")
            continue
        install = meta.get("install", {})
        dest = registry.repo_dir(cid, ws)
        clone_url = install.get("clone", "")
        branch = install.get("branch")
        ref = install.get("ref")
        print(f"  {cid}")
        print(f"    clone: {clone_url}")
        if branch:
            print(f"    branch: {branch}")
        if ref:
            print(f"    ref: {ref[:12]}")
        print(f"    path: {dest}")
        if dry_run:
            continue
        if dest.is_dir() and (dest / ".git").is_dir():
            print("    status: already cloned")
        elif clone_url:
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                _run(["git", "clone", "--filter=blob:none", clone_url, str(dest)])
                if branch:
                    _run(["git", "checkout", branch], cwd=dest)
                if ref:
                    _run(["git", "checkout", "--detach", ref], cwd=dest)
                print("    status: cloned")
            except subprocess.CalledProcessError as exc:
                print(f"    error: clone failed: {exc.stderr.strip()}", file=sys.stderr)
        cmd = install.get("command")
        if cmd and dest.is_dir():
            print(f"    setup: {cmd}")
            try:
                subprocess.run(cmd, shell=True, cwd=dest, check=True)
            except subprocess.CalledProcessError:
                print("    warning: setup command failed", file=sys.stderr)
        ws["components"][cid] = {
            "path": str(dest),
            "branch": branch,
            "ref": ref,
        }
    if not dry_run:
        registry.save_workspace(ws)
    print("\nDone. Run `z0 doctor` to verify.")
    return 0


def cmd_add(component_id: str) -> int:
    comps = registry.components()
    if component_id not in comps:
        print(f"error: unknown component `{component_id}`", file=sys.stderr)
        return 1
    return _add_one(component_id)


def _add_one(component_id: str) -> int:
    meta = registry.components()[component_id]
    ws = registry.load_workspace()
    ws.setdefault("components", {})
    dest = registry.repo_dir(component_id, ws)
    install = meta.get("install", {})
    clone_url = install.get("clone", "")
    if not dest.is_dir() and clone_url:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--filter=blob:none", clone_url, str(dest)])
        if install.get("branch"):
            _run(["git", "checkout", install["branch"]], cwd=dest)
        if install.get("ref"):
            _run(["git", "checkout", "--detach", install["ref"]], cwd=dest)
    ws["components"][component_id] = {
        "path": str(dest),
        "branch": install.get("branch"),
        "ref": install.get("ref"),
    }
    registry.save_workspace(ws)
    print(f"added {component_id} at {dest}")
    return 0


def cmd_doctor() -> int:
    ws = registry.load_workspace()
    comps = registry.components()
    print("Zer0 System\n")
    warnings: list[str] = []
    for cid, meta in sorted(comps.items()):
        dest = registry.repo_dir(cid, ws)
        install = meta.get("install", {})
        pinned = (install.get("ref") or "")[:12]
        if dest.is_dir() and (dest / ".git").exists():
            head = _git_head(dest) or "?"
            branch = _git_branch(dest) or "?"
            mark = "✓"
            if pinned and head and not head.startswith(pinned[:7]):
                warnings.append(f"{cid}: local {head} != registry pin {pinned}")
        else:
            head = branch = "-"
            mark = "○"
        print(f"{mark} {meta.get('name', cid)}")
        print(f"    {branch} @ {head}  (registry: {pinned or '-'})")
    print("\nInterfaces")
    print("─" * 40)
    for iface, imeta in sorted(registry.interfaces().items()):
        owner = imeta.get("owner", "")
        owner_path = registry.repo_dir(owner, ws)
        ok = owner_path.is_dir()
        print(f"{'✓' if ok else '○'} {iface} → {owner}")
    if warnings:
        print("\nWarnings")
        print("─" * 40)
        for w in warnings:
            print(f"! {w}")
    return 0


def cmd_status() -> int:
    ws = registry.load_workspace()
    comps = registry.components()
    print(f"{'Component':<16} {'Installed':<10} {'Branch':<28} {'HEAD':<12} {'State'}")
    print("─" * 90)
    for cid, meta in sorted(comps.items()):
        dest = registry.repo_dir(cid, ws)
        installed = "yes" if dest.is_dir() and (dest / ".git").exists() else "no"
        branch = (_git_branch(dest) or "-")[:28] if installed == "yes" else "-"
        head = (_git_head(dest) or "-")[:12] if installed == "yes" else "-"
        state = f"{meta.get('status', '')}/{meta.get('execution', '')}"
        print(f"{cid:<16} {installed:<10} {branch:<28} {head:<12} {state}")
    return 0


def cmd_graph(fmt: str = "text") -> int:
    if fmt == "mermaid":
        print(generate.graph_mermaid(), end="")
        return 0
    if fmt == "json":
        nodes = [
            {"id": cid, "name": m.get("name", cid), "kind": m.get("kind")}
            for cid, m in registry.components().items()
        ]
        edges = [
            {"from": s, "to": d, "kind": k}
            for s, d, k in generate._edges()
        ]
        print(json.dumps({"nodes": nodes, "edges": edges}, indent=2))
        return 0
    comps = registry.components()
    children: dict[str, list[str]] = {cid: list(meta.get("depends_on", [])) for cid, meta in comps.items()}
    roots = [cid for cid, deps in children.items() if not deps]
    for root in sorted(roots):
        _print_tree(root, comps, set(), 0)
    return 0


def _print_tree(cid: str, comps: dict[str, Any], seen: set[str], depth: int) -> None:
    if cid in seen:
        return
    seen.add(cid)
    prefix = "  " * depth + ("└── " if depth else "")
    label = comps.get(cid, {}).get("name", cid)
    print(f"{prefix}{label}" if depth else label)
    for other_id, meta in comps.items():
        if cid in meta.get("depends_on", []):
            _print_tree(other_id, comps, seen, depth + 1)
    for peer in comps.get(cid, {}).get("integrates_with", []):
        if peer not in seen and peer in comps:
            print(f"{'  ' * (depth + 1)}↔ {comps[peer].get('name', peer)}")


def cmd_docs_generate() -> int:
    written = generate.write_all()
    for path in written:
        print(f"wrote {path.relative_to(generate.ROOT)}")
    return 0


def cmd_cognition_portfolio(as_json: bool = False) -> int:
    """Read the z0intelligence manifest live. z0 never stores the model list."""
    manifest = cognition.load_manifest()
    if as_json:
        print(json.dumps(cognition.render_json(manifest), indent=2, default=str))
        return 0
    if manifest is None:
        print(
            "note: z0intelligence manifest not resolved on this machine — reference view only.\n"
            "      set Z0INT_COGNITION_MANIFEST or Z0INTELLIGENCE_ROOT, clone z0intelligence via "
            "`./z0 add z0intelligence`, or put `z0int` on PATH.",
            file=sys.stderr,
        )
    print(cognition.render_markdown(manifest, manifest_source=cognition.CANONICAL_REPO), end="")
    return 0
