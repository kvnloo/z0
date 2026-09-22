"""Generate docs and graphs from registry manifests."""

from __future__ import annotations

import json
from pathlib import Path

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
        "| ID | Name | Kind | Status | Execution | Repo | Stable ref |",
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


def harnesses_md() -> str:
    lines = [
        "# Harness registry",
        "",
        "| ID | Name | Kind | Adoption | Repo | AODL id | Catalog gap |",
        "|----|------|------|----------|------|---------|-------------|",
    ]
    for hid, meta in sorted(registry.harnesses().items()):
        lines.append(
            f"| `{hid}` | {meta.get('name', hid)} | {meta.get('kind', '')} "
            f"| {meta.get('adoption', '')} | `{meta.get('repo', '')}` "
            f"| `{meta.get('aodl_id') or ''}` | {'yes' if meta.get('catalog_gap') else ''} |"
        )
    lines += ["", "_Generated from `registry/harnesses.yaml`._", ""]
    return "\n".join(lines)


def mechanisms_md() -> str:
    lines = ["# Mechanism registry", ""]
    for mid, meta in sorted(registry.mechanisms().items()):
        lines.append(f"## `{mid}` — {meta.get('name', mid)}")
        lines.append(f"- **Kind:** {meta.get('kind', '')}")
        lines.append(f"- **Stage:** {meta.get('stage', '')}")
        if meta.get("family"):
            lines.append(f"- **Family:** `{meta['family']}`")
        purpose = " ".join(str(meta.get("purpose", "")).split())
        lines.append(f"- **Purpose:** {purpose}")
        implementations = (meta.get("implemented_by") or []) + (meta.get("implementations") or [])
        if implementations:
            refs = []
            for row in implementations:
                refs.append(row.get("component") or row.get("harness") or row.get("repo") or "?")
            lines.append("- **Implemented by:** " + ", ".join(f"`{x}`" for x in refs))
        lines.append("")
    lines += ["_Generated from `registry/mechanisms.yaml`._", ""]
    return "\n".join(lines)


def lifecycles_md() -> str:
    lines = ["# Lifecycle registry", ""]
    for lid, meta in sorted(registry.lifecycles().items()):
        stages = " → ".join(f"`{s}`" for s in meta.get("stages", []))
        lines.append(f"## `{lid}` — {meta.get('name', lid)}")
        lines.append(f"- **Kind:** {meta.get('kind', '')}")
        lines.append(f"- **Stages:** {stages}")
        rule = " ".join(str(meta.get("rule", "")).split())
        lines.append(f"- **Rule:** {rule}")
        lines.append("")
    lines += ["_Generated from `registry/lifecycles.yaml`._", ""]
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
        "# Where does this belong?",
        "",
        "| I need to change… | Owner component |",
        "|-------------------|-----------------|",
        "| Coding agent runtime | `oh-my-pi` |",
        "| Voice / Stage / computer use | `oh-my-pi` |",
        "| Context spill / RLM | `oh-my-pi` |",
        "| OS prediction / prepare | `flow` |",
        "| Personal learned policy | `z0intelligence` |",
        "| Routine promotion | `z0intelligence` |",
        "| Token / cost measurement | `tokenomics` |",
        "| Compute / provider allocation | `kerdoios` |",
        "| Experiment search | `evolution-lab` |",
        "| Research knowledge | `frontier-kb` |",
        "| Typed intent / plan schema | `aodl` |",
        "| Historical agent TUI | `agenttrace` |",
        "| Visual private history | `memento` |",
        "",
        "## Do NOT put…",
        "",
        "| Anti-pattern | Correct owner |",
        "|--------------|---------------|",
        "| Routing policy in Tokenomics | `kerdoios` / `z0intelligence` |",
        "| Training logic in Flow | `evolution-lab` |",
        "| Provider execution in Kerdoios | OMP / provider adapters |",
        "| Runtime implementation in AODL | `oh-my-pi` |",
        "| Private user traces in frontier-kb | `memento` / `z0intelligence` |",
        "",
    ]
    return "\n".join(lines)


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
        GENERATED / "harnesses.md": harnesses_md(),
        GENERATED / "mechanisms.md": mechanisms_md(),
        GENERATED / "lifecycles.md": lifecycles_md(),
        GENERATED / "install-matrix.md": install_matrix(),
        DOCS_GEN / "ownership.md": ownership_table(),
        GENERATED / "docs-index.jsonl": docs_index_jsonl(),
    }
    written: list[Path] = []
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
