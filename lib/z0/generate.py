"""Generate docs, the almanac and the typed graph from registry manifests.

Everything under `generated/` and `docs/reference/ownership.md` is derived. If a
generated page is wrong, fix the registry — never the page.

Nothing here performs network access: the almanac must be reproducible offline so
`scripts/docs-check` can fail CI on drift. Live upstream heads belong to
`z0 registry doctor`, which writes only to a gitignored path.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import cognition, registry

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "generated"
DOCS_GEN = ROOT / "docs" / "reference"

ENTITY_STYLE = {
    "owned_component": ("([\"{}\"])", "owned component"),
    "upstream_system": ("([\"{}\"])", "upstream system"),
    "catalog_source": ("[(\"{}\")]", "delegated source"),
    "contract": ("{{\"{}\"}}", "contract"),
}


def _node(ident: str) -> str:
    return ident.replace("-", "_").replace(".", "__")


# ---------------------------------------------------------------- almanac ----
def almanac() -> dict:
    """The whole reconciled almanac as one machine-readable document."""
    comps, ups, srcs, ifaces = (
        registry.components(), registry.upstreams(),
        registry.sources(), registry.interfaces(),
    )
    return {
        "schema": "z0.almanac.v1",
        "canonical_repo": "kvnloo/z0",
        "generated_from": [
            "registry/components.yaml", "registry/upstreams.yaml",
            "registry/sources.yaml", "registry/interfaces.yaml",
            "registry/profiles.yaml",
        ],
        "notes": [
            "tested_ref is the ref this repo VALIDATED for install.",
            "upstream_head is a LIVE fact and is deliberately not stored here; "
            "run `z0 registry doctor` to discover it.",
            "architecture_status is semantic and is independent of tested_ref.",
            "Delegated sources record the relationship and cache policy only. "
            "The facts live at the authority.",
        ],
        "entity_classes": {
            "owned_component": sorted(comps),
            "upstream_system": sorted(ups),
            "catalog_source": sorted(srcs),
        },
        "components": comps,
        "upstreams": ups,
        "sources": srcs,
        "interfaces": ifaces,
        "profiles": registry.profiles(),
        "relationships": [
            {"from": s, "type": t, "to": d} for s, t, d in registry.relationship_edges()
        ],
    }


def agent_registry_yaml() -> str:
    """Agent-facing flat registry (the PR #2 idea), derived from the almanac."""
    data = {
        "version": 2,
        "ecosystem": "zer0",
        "canonical_repo": "kvnloo/z0",
        "generated_from": ["registry/*.yaml"],
        "components": {
            cid: {
                "repo": m.get("repo"),
                "plane": m.get("plane"),
                "architecture_status": m.get("architecture_status"),
                "implementation_status": m.get("implementation_status"),
                "owner": m.get("owner"),
                "owns": m.get("owns", []),
                "not_here": m.get("not_here", []),
            }
            for cid, m in sorted(registry.components().items())
        },
        "upstreams": {
            uid: {
                "repo": m.get("repo"),
                "kind": m.get("kind"),
                "is_fork": m.get("is_fork"),
                "relationship": m.get("relationship"),
            }
            for uid, m in sorted(registry.upstreams().items())
        },
        "sources": {
            sid: {
                "kind": m.get("kind"),
                "authority": m.get("authority"),
                "discovers": m.get("discovers", []),
                "cache_policy": m.get("cache_policy"),
            }
            for sid, m in sorted(registry.sources().items())
        },
    }
    header = (
        "# GENERATED — do not edit. Derived from registry/*.yaml by "
        "`./scripts/docs-generate`.\n"
    )
    return header + yaml.safe_dump(data, sort_keys=False, default_flow_style=False, width=100)


# ------------------------------------------------------------------ graph ----
def graph_mermaid() -> str:
    lines = ["graph TD"]
    comps, ups, srcs, ifaces = (
        registry.components(), registry.upstreams(),
        registry.sources(), registry.interfaces(),
    )
    for cid, meta in comps.items():
        lines.append(f'  {_node(cid)}(["{meta.get("name", cid)}"])')
    for uid, meta in ups.items():
        lines.append(f'  {_node(uid)}(["{meta.get("name", uid)}<br/><i>upstream</i>"])')
    for sid, meta in srcs.items():
        lines.append(f'  {_node(sid)}[("{meta.get("name", sid)}<br/><i>source</i>")]')

    used_contracts = set()
    edges: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for src, rel, dst in registry.relationship_edges():
        if dst in ifaces:
            used_contracts.add(dst)
            dst_node = _node(dst)
            link = f"  {_node(src)} -- {rel} --> {dst_node}"
        else:
            if src not in comps and src not in ups and src not in srcs:
                continue
            if dst not in comps and dst not in ups and dst not in srcs:
                continue
            link = f"  {_node(src)} -- {rel} --> {_node(dst)}"
        if link in seen:
            continue
        seen.add(link)
        edges.append(link)

    for name in sorted(used_contracts):
        lines.append(f'  {_node(name)}{{"{name}"}}')
    lines.extend(edges)

    lines += [
        "  classDef owned fill:#e8f5e9,stroke:#2e7d32;",
        "  classDef upstream fill:#e3f2fd,stroke:#1565c0;",
        "  classDef source fill:#fff3e0,stroke:#ef6c00;",
        "  classDef contract fill:#f3e5f5,stroke:#6a1b9a;",
    ]
    if comps:
        lines.append("  class " + ",".join(_node(c) for c in comps) + " owned;")
    if ups:
        lines.append("  class " + ",".join(_node(u) for u in ups) + " upstream;")
    if srcs:
        lines.append("  class " + ",".join(_node(s) for s in srcs) + " source;")
    if used_contracts:
        lines.append("  class " + ",".join(_node(c) for c in sorted(used_contracts))
                     + " contract;")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------- markdown ----
def _status_cell(meta: dict) -> str:
    return f"{meta.get('architecture_status', '')} / {meta.get('implementation_status', '')}"


def component_table() -> str:
    lines = [
        "# Owned components",
        "",
        "Architecture status is where the *design* lives; implementation status is",
        "whether it *runs*. `tested_ref` is the last validated install ref — a stale",
        "`tested_ref` does not make the design stale.",
        "",
        "| ID | Name | Plane | Arch / Impl | Repo | tested_ref |",
        "|----|------|-------|-------------|------|------------|",
    ]
    for cid, meta in sorted(registry.components().items()):
        ref = meta.get("install", {}).get("tested_ref") or "—"
        lines.append(
            f"| `{cid}` | {meta.get('name', cid)} | {meta.get('plane', '')} "
            f"| {_status_cell(meta)} | `{meta.get('repo', '')}` | `{ref}` |"
        )
    lines += ["", "_Generated from `registry/components.yaml`. Do not edit by hand._", ""]
    return "\n".join(lines)


def upstream_table() -> str:
    lines = [
        "# Upstream systems",
        "",
        "Not installable, not in any profile. A repository we contribute to is not",
        "automatically supported infrastructure.",
        "",
        "| ID | Name | Kind | Fork | Relationship | Upstream |",
        "|----|------|------|------|--------------|----------|",
    ]
    for uid, meta in sorted(registry.upstreams().items()):
        lines.append(
            f"| `{uid}` | {meta.get('name', uid)} | {meta.get('kind', '')} "
            f"| {'yes' if meta.get('is_fork') else 'no'} | {meta.get('relationship', '')} "
            f"| `{meta.get('upstream_repo', '')}` |"
        )
    lines += ["", "_Generated from `registry/upstreams.yaml`. Do not edit by hand._", ""]
    return "\n".join(lines)


def sources_md() -> str:
    lines = [
        "# Delegated catalog sources",
        "",
        "Where a fact Zer0 appears to need already has a stronger owner, z0 records",
        "the relationship, the discovery mechanism and the cache policy — never the",
        "facts. A cached snapshot is never fresher than its source.",
        "",
    ]
    for sid, meta in sorted(registry.sources().items()):
        lines.append(f"## `{sid}` — {meta.get('name', sid)}")
        lines.append(f"- **Kind:** {meta.get('kind', '')}")
        auth = meta.get("authority") or {}
        lines.append(f"- **Authority:** {auth.get('surface') or auth.get('repo') or '—'}")
        lines.append(f"- **Cache policy:** `{meta.get('cache_policy', '')}`"
                     + (f" (ttl {meta.get('cache_ttl')})" if meta.get("cache_ttl") else ""))
        lines.append(f"- **Discovers:** {', '.join(meta.get('discovers', []))}")
        lines.append(f"- **Owns:** {', '.join(meta.get('owns', []))}")
        lines.append(f"- **Does not own:** {', '.join(meta.get('does_not_own', []))}")
        lines.append(f"- **Consumed by:** {', '.join(meta.get('consumed_by', [])) or '—'}")
        if meta.get("note"):
            lines.append(f"- **Note:** {' '.join(str(meta['note']).split())}")
        lines.append("")
    lines.append("_Generated from `registry/sources.yaml`. Do not edit by hand._")
    lines.append("")
    return "\n".join(lines)


def ownership_table() -> str:
    lines = [
        "# Ownership map",
        "",
        "Generated from each component's `owns` / `not_here` in",
        "`registry/components.yaml`. If this page is wrong, fix the registry.",
        "",
        "| Component | Owns | Explicitly does not own |",
        "|-----------|------|--------------------------|",
    ]
    for cid, meta in sorted(registry.components().items()):
        owns = ", ".join(meta.get("owns", [])) or "—"
        not_here = ", ".join(meta.get("not_here", [])) or "—"
        lines.append(f"| `{cid}` | {owns} | {not_here} |")

    lines += [
        "",
        "## Promotion is three acts, not one",
        "",
        "The word \"promotion\" was overloaded across three systems. Split:",
        "",
        "| Act | Owner | Meaning |",
        "|-----|-------|---------|",
        "| Qualify | `evolution-lab` | the candidate clears frozen experimental gates |",
        "| Publish | `z0evals` | the reproducible study is frozen and published |",
        "| Activate | `z0intelligence` | the qualified policy enters shadow → canary → active |",
        "",
        "Evolution Lab may not activate; z0evals may not train or activate;",
        "z0intelligence may not declare a candidate qualified.",
        "",
        "## Rule",
        "",
        "Every cross-repo fact has one authoritative owner. Other repos may consume,",
        "reference or observe it, but must not silently redefine it. Where an",
        "upstream already owns the fact, z0 delegates — see `sources.md`.",
        "",
        "_Generated from `registry/*.yaml`. Do not edit by hand._",
        "",
    ]
    return "\n".join(lines)


def interfaces_md() -> str:
    classes = {"contract": [], "adapter": []}
    for name, meta in sorted(registry.interfaces().items()):
        classes.setdefault(meta.get("class", "contract"), []).append((name, meta))
    lines = [
        "# Interfaces",
        "",
        "Generic ecosystem contracts are separated from implementation-specific",
        "adapters. An adapter names the harness it belongs to and must never be",
        "presented as a shared contract.",
        "",
        "## Generic ecosystem contracts",
        "",
        "| Contract | Owner | Summary |",
        "|----------|-------|---------|",
    ]
    for name, meta in classes.get("contract", []):
        lines.append(f"| `{name}` | `{meta.get('owner', '')}` | {' '.join(str(meta.get('summary', '')).split())} |")
    lines += [
        "",
        "## Implementation-specific adapters",
        "",
        "| Adapter | Harness | Owner | Summary |",
        "|---------|---------|-------|---------|",
    ]
    for name, meta in classes.get("adapter", []):
        lines.append(
            f"| `{name}` | `{meta.get('harness', '')}` | `{meta.get('owner', '')}` "
            f"| {' '.join(str(meta.get('summary', '')).split())} |"
        )
    lines += ["", "_Generated from `registry/interfaces.yaml`._", ""]
    return "\n".join(lines)


def install_matrix() -> str:
    profs = registry.profiles()
    comp_ids = sorted(registry.components().keys())
    lines = [
        "# Install matrix",
        "",
        "Harnesses are chosen separately from capabilities and are never installed as",
        "components.",
        "",
        "| Profile | Capabilities | Harnesses (default first) |",
        "|---------|--------------|---------------------------|",
    ]
    def _chain(name: str) -> list[str]:
        """Profile inheritance order, nearest first."""
        out, seen = [], set()
        cur = name
        while cur and cur in profs and cur not in seen:
            seen.add(cur)
            out.append(cur)
            cur = profs[cur].get("extends")
        return out

    for pname in profs:
        chain = _chain(pname)
        harnesses: list[str] = []
        default = None
        for step in chain:
            for h in profs[step].get("harnesses") or []:
                if h not in harnesses:
                    harnesses.append(h)
            default = default or profs[step].get("default_harness")
        if default and default in harnesses:
            harnesses.insert(0, harnesses.pop(harnesses.index(default)))
        lines.append(
            f"| `{pname}` | {', '.join(profs[pname].get('capabilities', [])) or '—'} "
            f"| {', '.join('`' + h + '`' for h in harnesses) or '—'} |"
        )
    lines += [
        "",
        "## Owned components per profile",
        "",
        "| Component | " + " | ".join(profs.keys()) + " |",
        "|-----------|" + "|".join(["---"] * len(profs)) + "|",
    ]
    for cid in comp_ids:
        row = [f"`{cid}`"]
        for pname in profs:
            row.append("yes" if cid in set(registry.resolve_profile(pname)) else "")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "_Generated from `registry/profiles.yaml`._", ""]
    return "\n".join(lines)


def component_page(cid: str, meta: dict) -> str:
    """One page per owned component, generated from registry metadata.

    Hand-written per-component pages duplicate registry facts and go stale
    (the previous oh-my-pi page still advertised an unmerged fork pin as a
    "stable ref"). Registry facts are generated; only implementation docs live
    in the owning repo.
    """
    install = meta.get("install", {})
    rel = meta.get("relationships") or []
    lines = [
        "---",
        f"id: components.{cid}",
        f"title: {meta.get('name', cid)}",
        f"scope: [{cid}]",
        "status: generated",
        "---",
        "",
        f"# {meta.get('name', cid)}",
        "",
        f"**Repo:** `{meta.get('repo', '')}`  ",
        f"**Plane:** {meta.get('plane', '')}  ",
        f"**Architecture status:** `{meta.get('architecture_status', '')}`  ",
        f"**Implementation status:** `{meta.get('implementation_status', '')}`  ",
        f"**tested_ref:** `{install.get('tested_ref') or '—'}`"
        + (f" on `{install.get('branch')}`" if install.get("branch") else ""),
        "",
        " ".join(str(meta.get("summary", "")).split()),
        "",
        "## Owns",
        "",
    ]
    lines += [f"- {o}" for o in meta.get("owns", [])] or ["- —"]
    lines += ["", "## Explicitly does not own", ""]
    lines += [f"- {o}" for o in meta.get("not_here", [])] or ["- —"]
    if rel:
        lines += ["", "## Relationships", "", "| Type | Target |", "|------|--------|"]
        lines += [f"| `{r.get('type')}` | `{r.get('to')}` |" for r in rel]
    if install.get("clone"):
        lines += ["", "## Install", "", "```bash", f"git clone {install['clone']}"]
        if install.get("branch"):
            lines.append(f"git checkout {install['branch']}")
        if install.get("command"):
            lines.append(install["command"])
        lines += ["```"]
    if meta.get("verify", {}).get("command"):
        lines += ["", "## Verify", "", "```bash", meta["verify"]["command"], "```"]
    docs = meta.get("docs") or {}
    if docs:
        lines += ["", "## Implementation docs (live in the owning repo)", ""]
        lines += [f"- `{k}`: `{v}`" for k, v in docs.items()]
    lines += ["", "_Generated from `registry/components.yaml`. Do not edit by hand._", ""]
    return "\n".join(lines)


def upstream_page(uid: str, meta: dict) -> str:
    lines = [
        "---",
        f"id: upstreams.{uid}",
        f"title: {meta.get('name', uid)}",
        f"scope: [{uid}]",
        "status: generated",
        "---",
        "",
        f"# {meta.get('name', uid)}",
        "",
        "**This is an upstream system, not a Zer0 component.** It is not installable",
        "and appears in no profile.",
        "",
        f"**Repo:** `{meta.get('repo', '')}`  ",
        f"**Upstream:** `{meta.get('upstream_repo', '—')}`  ",
        f"**Kind:** {meta.get('kind', '')}  ",
        f"**Fork:** {'yes' if meta.get('is_fork') else 'no'}  ",
        f"**Relationship:** `{meta.get('relationship', '')}`",
        "",
        " ".join(str(meta.get("summary", "")).split()),
        "",
        "## Owns",
        "",
    ]
    lines += [f"- {o}" for o in meta.get("owns", [])] or ["- —"]
    lines += ["", "## Explicitly does not own", ""]
    lines += [f"- {o}" for o in meta.get("not_here", [])] or ["- —"]
    if meta.get("note"):
        lines += ["", "## Note", "", " ".join(str(meta["note"]).split())]
    lines += [
        "",
        "> The upstream head is a **live** fact. Run `./z0 registry doctor` to see it;",
        "> it is deliberately not stored in the repository.",
        "",
        "_Generated from `registry/upstreams.yaml`. Do not edit by hand._",
        "",
    ]
    return "\n".join(lines)


def component_pages() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for cid, meta in registry.components().items():
        out[DOCS_GEN.parent / "components" / f"{cid}.md"] = component_page(cid, meta)
    for uid, meta in registry.upstreams().items():
        out[DOCS_GEN.parent / "components" / f"{uid}.md"] = upstream_page(uid, meta)
    return out


def docs_index_jsonl() -> str:
    entries = []
    known = sorted(registry.known_ids())
    for path in sorted((ROOT / "docs").rglob("*.md")):
        rel = path.relative_to(ROOT / "docs")
        text = path.read_text(encoding="utf-8")
        # Generated component pages mirror the registry and are regenerated on
        # every run; indexing them would make the index depend on the previous
        # run's output and break docs-check determinism.
        if text.startswith("---") and "status: generated" in text.split("---", 2)[1]:
            continue
        title = rel.stem.replace("-", " ").title()
        comps = [cid for cid in known if cid in text.lower()]
        entries.append({
            "id": str(rel).replace("/", ".").replace(".md", ""),
            "path": f"docs/{rel}",
            "title": title,
            "entities": comps,
        })
    return "\n".join(json.dumps(e) for e in entries) + ("\n" if entries else "")


def cognition_portfolio() -> str:
    """Reference view of the local cognition portfolio.

    Rendered WITHOUT a manifest on purpose: the model list is owned by
    z0intelligence and must never be committed into z0. Use
    `./z0 cognition portfolio` to read the live manifest.
    """
    return cognition.render_markdown(
        None,
        manifest_source="referenced only — z0 never stores the model list (unresolved at generation time)",
    )


def write_all() -> list[Path]:
    GENERATED.mkdir(parents=True, exist_ok=True)
    DOCS_GEN.mkdir(parents=True, exist_ok=True)
    outputs = {
        GENERATED / "almanac.json": json.dumps(almanac(), indent=2, sort_keys=False) + "\n",
        GENERATED / "graph.mmd": graph_mermaid(),
        GENERATED / "components.md": component_table(),
        GENERATED / "upstreams.md": upstream_table(),
        GENERATED / "sources.md": sources_md(),
        GENERATED / "interfaces.md": interfaces_md(),
        GENERATED / "install-matrix.md": install_matrix(),
        GENERATED / "cognition-portfolio.md": cognition_portfolio(),
        GENERATED / "cognition-flow.mmd": cognition.flow_mermaid(),
        DOCS_GEN / "ownership.md": ownership_table(),
        GENERATED / "docs-index.jsonl": docs_index_jsonl(),
        ROOT / "zer0.registry.yaml": agent_registry_yaml(),
    }
    outputs.update(component_pages())
    written: list[Path] = []
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
