"""Load Zer0 registry YAML and resolve install profiles.

The registry is FEDERATED (z0#1): owned components, upstream systems and
delegated catalog sources are distinct entity classes in distinct files, and an
entry is only installable if it is an owned component.

Upstream facts are never stored here. `upstream_head` and other live state are
discovered by `z0 registry doctor`, which writes only to a gitignored path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registry"

# Closed vocabulary for typed edges. An ambiguous `integrates_with` is refused:
# the graph is only useful if the direction means something.
VALID_RELATIONS = {
    "owns", "depends_on", "implements", "consumes_contract", "emits_contract",
    "discovers_from", "executes_via", "measured_by", "governed_by", "trains_for",
    "legacy_of", "reference_to", "provides_research_evidence", "governs",
    "evaluated_by",
    # Promotion split (see audit/RECONCILIATION.md §2):
    "qualifies", "publishes_evidence_to", "activates",
}

# Statuses a capability may carry. `unknown` means "not yet asserted" and is an
# honest value, not a failure.
ARCHITECTURE_STATUSES = {
    "merged", "open_pr", "branch_only", "local_only", "planned",
    "legacy", "superseded", "unknown",
}
IMPLEMENTATION_STATUSES = {
    "live", "canary", "experimental", "pre_activation", "idea", "unknown",
}


def _load(name: str) -> dict[str, Any]:
    path = REGISTRY / name
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def components() -> dict[str, dict[str, Any]]:
    """Owned Zer0 components. Only these are installable."""
    return _load("components.yaml").get("components", {})


def upstreams() -> dict[str, dict[str, Any]]:
    return _load("upstreams.yaml").get("upstreams", {})


def sources() -> dict[str, dict[str, Any]]:
    return _load("sources.yaml").get("sources", {})


def profiles() -> dict[str, dict[str, Any]]:
    return _load("profiles.yaml").get("profiles", {})


def interfaces() -> dict[str, dict[str, Any]]:
    return _load("interfaces.yaml").get("interfaces", {})


def maturity() -> dict[str, dict[str, str]]:
    return _load("maturity.yaml")


def cognition_flow() -> dict[str, Any]:
    """Stage map + owners for the local cognition dataflow.

    Model identity, roles, licences and measurements are NOT here; they are
    canonical in z0intelligence and read through :mod:`z0.cognition`.
    """
    return _load("cognition.yaml")


def entity_kinds() -> dict[str, str]:
    """id -> entity class, across all three classes."""
    out = {cid: "owned_component" for cid in components()}
    out.update({uid: "upstream_system" for uid in upstreams()})
    out.update({sid: "catalog_source" for sid in sources()})
    return out


def known_ids() -> set[str]:
    return set(entity_kinds())


def relationship_edges() -> list[tuple[str, str, str]]:
    """(source, relation, target) for every declared typed edge.

    Direction is the point. An upstream's `executes_via` means *Zer0 executes
    through it*, so the edge reads `z0 --executes_via--> <upstream>`. A source's
    consumers read `<consumer> --discovers_from--> <source>`.
    """
    edges: list[tuple[str, str, str]] = []
    for cid, meta in components().items():
        for rel in meta.get("relationships") or []:
            edges.append((cid, rel.get("type", ""), rel.get("to", "")))
    for uid, meta in upstreams().items():
        rel = meta.get("relationship")
        if rel:
            edges.append(("z0", rel, uid))
        for contract in meta.get("consumes_contracts") or []:
            edges.append((uid, "consumes_contract", contract))
        for contract in meta.get("emits_contracts") or []:
            edges.append((uid, "emits_contract", contract))
    for sid, meta in sources().items():
        for consumer in meta.get("consumed_by") or []:
            edges.append((consumer, "discovers_from", sid))
    return edges


def validate() -> list[str]:
    """Structural problems in the registry. Empty list means well-formed."""
    problems: list[str] = []
    comps, ups, srcs = components(), upstreams(), sources()

    ids = list(comps) + list(ups) + list(srcs)
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        problems.append(f"id declared in more than one entity class: {sorted(dupes)}")

    contract_owners = {c: m.get("owner") for c, m in interfaces().items()}

    for cid, meta in comps.items():
        for field in ("name", "repo", "plane", "architecture_status",
                      "implementation_status", "owner"):
            if not meta.get(field):
                problems.append(f"component {cid}: missing {field}")
        st = meta.get("architecture_status")
        if st and st not in ARCHITECTURE_STATUSES:
            problems.append(f"component {cid}: bad architecture_status {st!r}")
        ist = meta.get("implementation_status")
        if ist and ist not in IMPLEMENTATION_STATUSES:
            problems.append(f"component {cid}: bad implementation_status {ist!r}")
        for rel in meta.get("relationships") or []:
            rtype = rel.get("type")
            if rtype not in VALID_RELATIONS:
                problems.append(f"component {cid}: unknown relationship {rtype!r}")
            target = rel.get("to")
            # a target may be another entity OR a contract id
            if target not in ids and target not in contract_owners:
                problems.append(f"component {cid}: relationship target {target!r} is unknown")
        if not (meta.get("owns") or []):
            problems.append(f"component {cid}: owns nothing")

    for uid, meta in ups.items():
        for field in ("name", "repo", "kind", "relationship"):
            if not meta.get(field):
                problems.append(f"upstream {uid}: missing {field}")
        if meta.get("relationship") not in VALID_RELATIONS:
            problems.append(f"upstream {uid}: unknown relationship {meta.get('relationship')!r}")
        if meta.get("is_fork") is None:
            problems.append(f"upstream {uid}: is_fork must be stated")
        for pid in meta.get("profiles") or []:
            problems.append(f"upstream {uid}: upstreams are never installable (profile {pid})")

    for sid, meta in srcs.items():
        for field in ("name", "kind", "relationship", "cache_policy"):
            if not meta.get(field):
                problems.append(f"source {sid}: missing {field}")
        if meta.get("relationship") != "discovers_from":
            problems.append(f"source {sid}: delegated sources only discover_from")
        if not (meta.get("authority") or {}):
            problems.append(f"source {sid}: missing authority")
        if not (meta.get("discovers") or []):
            problems.append(f"source {sid}: discovers nothing")
        if not (meta.get("owns") or []):
            problems.append(f"source {sid}: missing owns")
        if not (meta.get("does_not_own") or []):
            problems.append(f"source {sid}: missing does_not_own")

    for name, spec in profiles().items():
        for cid in spec.get("components", []):
            if cid not in comps:
                problems.append(f"profile {name}: {cid} is not an owned component")
        for cid in (spec.get("harnesses") or []):
            if cid not in comps and cid not in ups:
                problems.append(f"profile {name}: harness {cid} is unknown")

    return problems


def resolve_profile(name: str) -> list[str]:
    """Expand profile + extends chain into ordered OWNED component ids."""
    profs = profiles()
    if name not in profs:
        raise KeyError(f"unknown profile: {name}")
    seen: list[str] = []
    stack = [name]
    while stack:
        current = stack.pop()
        spec = profs[current]
        if "extends" in spec:
            stack.append(spec["extends"])
        for cid in spec.get("components", []):
            if cid not in seen:
                seen.append(cid)
    return seen


def z0_home() -> Path:
    return Path(os.environ.get("Z0_HOME", Path.home() / ".z0"))


def workspace_path() -> Path:
    return z0_home() / "workspace.yaml"


def load_workspace() -> dict[str, Any]:
    path = workspace_path()
    if not path.is_file():
        return {"version": 1, "root": str(z0_home() / "repos"), "components": {}}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def save_workspace(data: dict[str, Any]) -> None:
    z0_home().mkdir(parents=True, exist_ok=True)
    path = workspace_path()
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)


def repo_dir(component_id: str, ws: dict[str, Any] | None = None) -> Path:
    ws = ws or load_workspace()
    comps = ws.get("components", {})
    if component_id in comps and comps[component_id].get("path"):
        return Path(comps[component_id]["path"]).expanduser()
    root = Path(ws.get("root", z0_home() / "repos")).expanduser()
    meta = components().get(component_id, {})
    repo = meta.get("repo", component_id).split("/", 1)[-1]
    return root / repo
