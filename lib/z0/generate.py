"""Generate docs and graphs from registry manifests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import registry

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "generated"
DOCS_GEN = ROOT / "docs" / "reference"


def _edges() -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    for cid, meta in registry.components().items():
        for dep in meta.get("depends_on", []):
            edges.append((dep, cid, "depends"))
        for peer in meta.get("integrates_with", []):
            if peer != cid:
                edges.append((cid, peer, "integrates"))
    return edges


def graph_mermaid() -> str:
    lines = ["graph TD"]
    for cid, meta in registry.components().items():
        label = meta.get("name", cid)
        lines.append(f'  {cid.replace("-", "_")}["{label}"]')
    seen: set[tuple[str, str]] = set()
    for src, dst, kind in _edges():
        a = src.replace("-", "_")
        b = dst.replace("-", "_")
        key = (a, b)
        if key in seen:
            continue
        seen.add(key)
        style = "-.->" if kind == "integrates" else "-->"
        lines.append(f"  {a} {style} {b}")
    return "\n".join(lines) + "\n"


def component_table() -> str:
    lines = [
        "# Component registry",
        "",
        "| ID | Name | Kind | Status | Execution | Repo | Tested ref |",
        "|----|------|------|--------|-----------|------|------------|",
    ]
    for cid, meta in sorted(registry.components().items()):
        install = meta.get("install", {})
        ref = (install.get("ref") or "")[:12]
        lines.append(
            f"| `{cid}` | {meta.get('name', cid)} | {meta.get('kind', '')} "
            f"| {meta.get('status', '')} | {meta.get('execution', '')} "
            f"| `{meta.get('repo', '')}` | `{ref}` |"
        )
    lines.append("")
    lines.append("_Generated from `registry/components.yaml`. Do not edit by hand._")
    lines.append("")
    return "\n".join(lines)


def interfaces_md() -> str:
    lines = ["# Interface registry", ""]
    for name, meta in sorted(registry.interfaces().items()):
        lines.append(f"## `{name}`")
        lines.append(f"- **Owner:** `{meta.get('owner', '')}`")
        lines.append(f"- **Summary:** {meta.get('summary', '')}")
        lines.append("")
    lines.append("_Generated from `registry/interfaces.yaml`._")
    lines.append("")
    return "\n".join(lines)


def install_matrix() -> str:
    profs = registry.profiles()
    comp_ids = sorted(registry.components().keys())
    lines = [
        "# Install matrix",
        "",
        "| Component | " + " | ".join(profs.keys()) + " |",
        "|-----------|" + "|".join(["---"] * len(profs)) + "|",
    ]
    for cid in comp_ids:
        row = [f"`{cid}`"]
        for pname, pspec in profs.items():
            resolved = set(registry.resolve_profile(pname))
            row.append("yes" if cid in resolved else "")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("_Generated from `registry/profiles.yaml`._")
    lines.append("")
    return "\n".join(lines)


def ownership_table() -> str:
    lines = [
        "# Ownership map",
        "",
        "This page is generated from each component's `boundaries` entry in `registry/components.yaml`. "
        "If this page is wrong, fix the registry rather than this file.",
        "",
        "| Component | Owns | Explicitly does not own |",
        "|-----------|------|--------------------------|",
    ]
    for cid, meta in sorted(registry.components().items()):
        bounds = meta.get("boundaries", {})
        owns = ", ".join(bounds.get("owns", [])) or "—"
        not_here = ", ".join(bounds.get("not_here", [])) or "—"
        lines.append(f"| `{cid}` | {owns} | {not_here} |")
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "Every cross-repo fact should have one authoritative owner. Other repos may consume, "
            "reference, or observe that fact, but should not silently redefine it.",
            "",
            "_Generated from `registry/components.yaml`. Do not edit by hand._",
            "",
        ]
    )
    return "\n".join(lines)


def agent_registry_yaml() -> str:
    comps = {}
    for cid, meta in sorted(registry.components().items()):
        comps[cid] = {
            "repo": meta.get("repo"),
            "kind": meta.get("kind"),
            "status": meta.get("status"),
            "execution": meta.get("execution"),
            "owner": meta.get("owner"),
            "boundaries": meta.get("boundaries", {}),
        }

    data = {
        "version": 1,
        "ecosystem": "zer0",
        "canonical_repo": "kvnloo/z0",
        "generated_from": [
            "registry/components.yaml",
            "registry/profiles.yaml",
            "registry/interfaces.yaml",
        ],
        "rules": [
            "Implementation docs live with implementations",
            "Architecture and onboarding live in z0",
            "Token/cost claims require Tokenomics evidence",
            "Verified-success claims require an independent verifier",
            "AODL owns portable contracts, not runtime execution",
            "z0 maps the system; it does not run the system",
        ],
        "profiles": {
            name: registry.resolve_profile(name)
            for name in registry.profiles()
        },
        "components": comps,
        "interfaces": sorted(registry.interfaces()),
    }
    return (
        "# GENERATED FILE — edit registry/*.yaml, then run ./z0 docs generate\n"
        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    )

def docs_index_jsonl() -> str:
    entries = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        rel = path.relative_to(ROOT / "docs")
        text = path.read_text(encoding="utf-8")
        title = rel.stem.replace("-", " ").title()
        comps: list[str] = []
        for cid in registry.components():
            if cid in text.lower() or cid.replace("-", "") in text.lower():
                comps.append(cid)
        entries.append(
            {
                "id": str(rel).replace("/", ".").replace(".md", ""),
                "path": f"docs/{rel}",
                "title": title,
                "components": comps,
            }
        )
    return "\n".join(json.dumps(e) for e in entries) + ("\n" if entries else "")


def write_all() -> list[Path]:
    GENERATED.mkdir(parents=True, exist_ok=True)
    DOCS_GEN.mkdir(parents=True, exist_ok=True)
    outputs = {
        GENERATED / "graph.mmd": graph_mermaid(),
        GENERATED / "components.md": component_table(),
        GENERATED / "interfaces.md": interfaces_md(),
        GENERATED / "install-matrix.md": install_matrix(),
        DOCS_GEN / "ownership.md": ownership_table(),
        GENERATED / "docs-index.jsonl": docs_index_jsonl(),
        ROOT / "zer0.registry.yaml": agent_registry_yaml(),
    }
    written: list[Path] = []
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
