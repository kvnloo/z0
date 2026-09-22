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


class DuplicateKeyError(ValueError):
    """A registry file declared the same key twice."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys.

    `yaml.safe_load` silently keeps the LAST duplicate key. That turned a
    malformed edit of components.yaml -- one that inserted a second `owns:` block
    because it did not recognise the inline `owns: [a, b]` form -- into a file
    that parsed cleanly while quietly discarding the new entries. A registry that
    can silently drop facts is worse than one that fails to load.
    """


def _no_duplicate_keys(loader: "_StrictLoader", node: yaml.Node, deep: bool = False) -> Any:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise DuplicateKeyError(
                f"duplicate key {key!r} at line {key_node.start_mark.line + 1}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


def _load(name: str) -> dict[str, Any]:
    path = REGISTRY / name
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        try:
            return yaml.load(fh, Loader=_StrictLoader) or {}
        except DuplicateKeyError as exc:
            raise DuplicateKeyError(f"{name}: {exc}") from exc


def components() -> dict[str, dict[str, Any]]:
    """Owned Zer0 components. Only these are installable."""
    return _load("components.yaml").get("components", {})


def upstreams() -> dict[str, dict[str, Any]]:
    return _load("upstreams.yaml").get("upstreams", {})


def sources() -> dict[str, dict[str, Any]]:
    return _load("sources.yaml").get("sources", {})


def reference_only() -> dict[str, dict[str, Any]]:
    """Owned repos that are NOT part of the network: product lines and aliases."""
    return _load("upstreams.yaml").get("reference_only", {})


def profiles() -> dict[str, dict[str, Any]]:
    return _load("profiles.yaml").get("profiles", {})


def interfaces() -> dict[str, dict[str, Any]]:
    return _load("interfaces.yaml").get("interfaces", {})


def maturity() -> dict[str, dict[str, str]]:
    return _load("maturity.yaml")


# The one canonical evidence vocabulary. Repos reference this list; they must
# not redeclare their own. An ordered tuple, because the order is the strength
# ordering: a claim may not borrow the consequences of a later class.
REQUIRED_EVIDENCE_CLASSES: tuple[str, ...] = (
    "SMOKE",
    "EXPLORATORY_BETA",
    "SHADOW",
    "PAIRED_REPLAY",
    "CONFIRM",
    "OOD",
    "PROMOTION",
)


def evidence_classes() -> dict[str, dict[str, Any]]:
    """The canonical evidence taxonomy, or {} when undeclared."""
    return _load("maturity.yaml").get("evidence", {}) or {}


class UnknownEvidenceClass(ValueError):
    """A claim named an evidence class the canonical taxonomy does not define."""


def normalize_evidence_class(value: Any) -> str:
    """Return the canonical name for an evidence class, whatever its case.

    The registry keys are uppercase; artifacts serialize the same names
    lowercased (`"evidence_class": "exploratory_beta"`). Both spell the one
    vocabulary, so consumers normalize before matching instead of comparing
    strings.

    Matching exactly is not a style question: kerdoios compared uppercase
    literals while every artifact in the ecosystem was lowercase, so it rejected
    all of them as unknown. Case-insensitive acceptance does not widen the set --
    an unrecognised name is still an error, and still loud.
    """
    text = str(value or "").strip()
    if not text:
        raise UnknownEvidenceClass(
            "empty evidence_class; the canonical taxonomy is defined in "
            "registry/maturity.yaml (evidence:)"
        )
    upper = text.upper()
    if upper not in evidence_classes():
        raise UnknownEvidenceClass(
            f"unknown evidence_class {value!r}; the canonical taxonomy is "
            f"{', '.join(evidence_classes())} (registry/maturity.yaml)"
        )
    return upper


# --- semantic ontology accessors (from the pre-federation generation) -------
# These were written on origin/main against the older `components.yaml` schema.
# They are additive: federation answers "who owns what and what is observed",
# the ontology answers "what harnesses/mechanisms/representations exist". Both
# are kept, because neither subsumes the other.


def harnesses() -> dict[str, dict[str, Any]]:
    return _load("harnesses.yaml").get("harnesses", {})


def harness_catalog() -> dict[str, Any]:
    return _load("harnesses.yaml").get("catalog", {})


def mechanisms() -> dict[str, dict[str, Any]]:
    return _load("mechanisms.yaml").get("mechanisms", {})


def lifecycles() -> dict[str, dict[str, Any]]:
    return _load("lifecycles.yaml").get("lifecycles", {})


def representations() -> dict[str, dict[str, Any]]:
    return _load("representations.yaml").get("representations", {})


def evidence_dependencies() -> dict[str, dict[str, Any]]:
    return _load("evidence_dependencies.yaml").get("evidence_dependencies", {})


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
    out.update({rid: "reference_only" for rid in reference_only()})
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
    for rid, meta in reference_only().items():
        rel = meta.get("relationship")
        if rel:
            edges.append(("z0", rel, rid))
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

    for rid, meta in reference_only().items():
        for field in ("name", "repo", "class", "kind", "relationship"):
            if not meta.get(field):
                problems.append(f"reference_only {rid}: missing {field}")
        if meta.get("class") != "reference_only":
            problems.append(f"reference_only {rid}: class must be reference_only")
        if meta.get("relationship") not in VALID_RELATIONS:
            problems.append(f"reference_only {rid}: unknown relationship "
                            f"{meta.get('relationship')!r}")

    for name, spec in profiles().items():
        for cid in spec.get("components", []):
            if cid not in comps:
                problems.append(f"profile {name}: {cid} is not an owned component")
        for cid in (spec.get("harnesses") or []):
            if cid not in comps and cid not in ups:
                problems.append(f"profile {name}: harness {cid} is unknown")

    # Semantic-ontology references resolve against the FULL entity universe,
    # not against owned components alone. The pre-federation check asserted
    # `component in comps`, which the federation legitimately breaks: oh-my-pi
    # and agenttrace moved to upstreams while mechanisms still name them. The
    # reference is true; only its class changed. Rows now carry `class:` so the
    # distinction is explicit rather than implied.
    entity_ids = set(comps) | set(ups) | set(srcs) | set(reference_only())
    interface_ids = set(interfaces())
    harness_ids = set(harnesses())

    def _check_refs(where: str, rows: Any, *, key: str = "entity") -> None:
        for row in rows or []:
            if not isinstance(row, dict):
                problems.append(f"{where}: reference is not a mapping")
                continue
            target = row.get(key) or row.get("component") or row.get("harness")
            if not target:
                problems.append(f"{where}: reference names nothing")
                continue
            declared = row.get("class")
            if declared and declared not in ("component", "upstream", "source", "reference_only"):
                problems.append(f"{where}: unknown class {declared!r}")
            if target not in entity_ids and target not in interface_ids and target not in harness_ids:
                problems.append(
                    f"{where}: reference {target!r} is not a known entity, harness or interface"
                )

    for mid, meta in mechanisms().items():
        _check_refs(f"mechanism {mid}.implemented_by", meta.get("implemented_by"))
        _check_refs(f"mechanism {mid}.implementations", meta.get("implementations"))
    for hid, meta in harnesses().items():
        _check_refs(f"harness {hid}", [meta] if meta.get("entity") or meta.get("component") else [])
    for rid, meta in representations().items():
        _check_refs(f"representation {rid}", meta.get("carried_by"))
    for lid, meta in lifecycles().items():
        _check_refs(f"lifecycle {lid}", meta.get("applies_to"))

    # A file in `schemas/` that nothing reads is worse than no file: it sits
    # where an authoritative schema belongs and describes a shape nobody
    # enforces. `schemas/component.schema.json` did exactly that -- it required
    # the PRE-federation component shape (id, kind, status) long after the
    # registry moved to (plane, architecture_status, owns, not_here,
    # relationships), had no reader, and contradicted every entry in
    # components.yaml. z0 now validates in Python, so `schemas/` is empty; this
    # keeps it that way unless a schema comes with a reader.
    schema_dir = ROOT / "schemas"
    if schema_dir.is_dir():
        haystack: list[str] = []
        for rel in ("lib", "scripts", "docs", "registry", "audit", "tests"):
            base = ROOT / rel
            if not base.is_dir():
                continue
            for candidate in base.rglob("*"):
                if not candidate.is_file() or "__pycache__" in candidate.parts:
                    continue
                if candidate.suffix not in (".py", ".sh", ".md", ".yml", ".yaml", ".json"):
                    continue
                try:
                    haystack.append(candidate.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
        blob = "\n".join(haystack)
        for schema_file in sorted(schema_dir.rglob("*")):
            if schema_file.is_file() and schema_file.name not in blob:
                problems.append(
                    f"schemas/{schema_file.name}: nothing references it. A schema "
                    "nothing enforces is read as authoritative while describing "
                    "no enforced shape -- delete it, or add a reader."
                )

    # The evidence taxonomy is the one vocabulary the whole stack classifies
    # claims against, so an incomplete or under-specified taxonomy is a
    # structural problem, not a documentation gap. `PAIRED_REPLAY` in
    # particular existed nowhere before this check.
    ev = evidence_classes()
    missing = [c for c in REQUIRED_EVIDENCE_CLASSES if c not in ev]
    if missing:
        problems.append(f"maturity.yaml: evidence taxonomy is missing {missing}")
    for cid in REQUIRED_EVIDENCE_CLASSES:
        spec = ev.get(cid)
        if not spec:
            continue
        if not spec.get("means"):
            problems.append(f"evidence class {cid}: missing 'means'")
        if "may_influence" not in spec:
            problems.append(f"evidence class {cid}: missing 'may_influence'")

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
