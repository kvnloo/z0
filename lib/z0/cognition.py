"""Local cognition portfolio — reference, never duplication.

Ownership split this module exists to enforce:

``z0``
    The **stage map** and the **owner** of each stage
    (:mod:`z0.registry.cognition_flow`, data in ``registry/cognition.yaml``).

``z0intelligence``
    The **model list**: identity, roles, licences, gated access, benchmarks,
    local measurements, promotion state and the serving map. Canonical source is
    ``manifests/local_cognition.v1.json``, loadable through
    ``z0int cognition manifest --json``; the role view is
    ``z0int cognition roles --json``.

``kerdoios``
    Placement of an already-selected capability on a concrete machine. Never
    semantic suitability.

``frontier-kb``
    External evidence and hypotheses. Not runtime state.

This module therefore renders the stage/owner dataflow from z0's own registry
and **reads** the model rows from z0intelligence at render time. It never
embeds a model id, licence or benchmark number in this repository.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import registry

CANONICAL_REPO = "kvnloo/z0intelligence"
CANONICAL_MANIFEST = "manifests/local_cognition.v1.json"
MANIFEST_CLI = "z0int cognition manifest --json"
ROLES_CLI = "z0int cognition roles --json"

GENERATED = registry.ROOT / "generated"

# Roles are owned by z0intelligence; listed here only so a rendered table can be
# labelled. Selection and defaults stay in the manifest.
ROLE_LABELS = {
    "tiny_action_specialist": "tiny action specialist",
    "bounded_scorer": "bounded scorer",
    "general_function_caller": "general function caller",
    "semantic_orchestrator": "semantic orchestrator",
    "general_local_fallback": "general local fallback",
    "remote_specialist_fallback": "remote specialist fallback",
}


# --- z0-owned stage map -------------------------------------------------


def stages() -> list[dict[str, Any]]:
    return list(registry.cognition_flow().get("stages") or [])


def flow_edges() -> list[list[str]]:
    return [list(edge) for edge in (registry.cognition_flow().get("flow") or [])]


def canonical() -> dict[str, Any]:
    return dict(registry.cognition_flow().get("canonical") or {})


# --- z0intelligence-owned manifest, read at render time -----------------


def manifest_candidates() -> list[Path]:
    """Explicit, documented resolution order. No filesystem crawling."""
    paths: list[Path] = []
    explicit = os.environ.get("Z0INT_COGNITION_MANIFEST")
    if explicit:
        paths.append(Path(explicit).expanduser())
    root = os.environ.get("Z0INTELLIGENCE_ROOT")
    if root:
        paths.append(Path(root).expanduser() / CANONICAL_MANIFEST)
    # z0 already knows where it cloned z0intelligence via ~/.z0/workspace.yaml.
    try:
        paths.append(registry.repo_dir("z0intelligence") / CANONICAL_MANIFEST)
    except Exception:  # noqa: BLE001 - a missing workspace file is not fatal
        pass
    # ...and if it does not, look for a checkout by the names the registry says
    # this component has. DECLARED candidates stay first: discovery is a
    # fallback, never an override.
    #
    # Without this the default `~/.z0/repos/z0intelligence` -- derived from the
    # REPO basename -- can never find the checkout on a machine where the
    # directory kept the old name. It is `~/tmp/openjev` here, and `openjev` is
    # declared in registry/upstreams.yaml as `superseded_by: z0intelligence`, so
    # the alias is registry data rather than a guess.
    for root in _sibling_roots():
        for name in _manifest_alias_names():
            for candidate in (root / name, *sorted(root.glob(f"*/{name}"))):
                paths.append(candidate / CANONICAL_MANIFEST)
    return paths


def _manifest_alias_names() -> list[str]:
    """Directory names `CANONICAL_REPO`'s component is known by, per the registry."""
    component_id = CANONICAL_REPO.split("/")[-1]
    names = {component_id}
    try:
        for rid, meta in registry.reference_only().items():
            if (meta or {}).get("superseded_by") == component_id:
                names.add(rid)
    except Exception:  # noqa: BLE001 - registry unavailable is not fatal here
        pass
    return sorted(names)


def checkout_dirs() -> list[Path]:
    """Directories that LOOK like a z0intelligence checkout: known name + `.git`.

    Distinguishes the two reasons the manifest can be unreachable, which need
    opposite answers:

      * the checkout is here and the manifest is missing  -> a fault, fail
      * the checkout is not here at all                   -> a coverage limit,
                                                             say so loudly and
                                                             do not fail a build
                                                             that cannot have it

    Same rule `scripts/reality-sweep` uses for a root that exists here versus one
    this machine does not have.
    """
    out: list[Path] = []
    for root in _sibling_roots():
        if not root.is_dir():
            continue
        for name in _manifest_alias_names():
            for candidate in (root / name, *sorted(root.glob(f"*/{name}"))):
                if (candidate / ".git").exists() and candidate not in out:
                    out.append(candidate)
    return out


def _sibling_roots() -> list[Path]:
    """Where sibling checkouts live, mirroring scripts/reality-sweep.

    `Z0_SWEEP_ROOTS` overrides the same way it does there, so one variable
    configures both tools on a machine whose layout differs.
    """
    override = [p for p in os.environ.get("Z0_SWEEP_ROOTS", "").split(os.pathsep) if p]
    if override:
        return [Path(p).expanduser() for p in override]
    home = Path.home()
    return [home / name for name in ("tmp", "zer0", "src", "repos")]


def manifest_path() -> Path | None:
    for candidate in manifest_candidates():
        if candidate.is_file():
            return candidate
    return None


def manifest_from_cli() -> dict[str, Any] | None:
    """Fall back to the z0intelligence CLI when the manifest file is not local."""
    exe = shutil.which("z0int")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "cognition", "manifest", "--json"],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def load_manifest(path: Path | None = None, *, allow_cli: bool = True) -> dict[str, Any] | None:
    """Load the canonical z0intelligence manifest, or None when unreachable."""
    target = path or manifest_path()
    if target is not None and Path(target).is_file():
        return json.loads(Path(target).read_text(encoding="utf-8"))
    if allow_cli:
        return manifest_from_cli()
    return None


def model_rows(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Project manifest models into render rows. Order comes from the manifest."""
    if not manifest:
        return []
    rows: list[dict[str, Any]] = []
    defaults = {str(v): k for k, v in (manifest.get("role_defaults") or {}).items()}
    for model_id, model in (manifest.get("models") or {}).items():
        model = model or {}
        measurements = model.get("measurements") or []
        rows.append(
            {
                "model_id": str(model_id),
                "hf": model.get("hf"),
                "parameters": model.get("parameter_count"),
                "roles": list(model.get("role_tags") or []),
                "role_default_for": defaults.get(str(model_id)),
                "license": model.get("license"),
                "commercial_use": model.get("commercial_use"),
                "gated_access": bool(model.get("gated_access", False)),
                "measured_locally": bool(measurements),
                "promotion_state": model.get("promotion_state"),
            }
        )
    rows.sort(key=lambda r: r["model_id"])
    return rows


# --- rendering ----------------------------------------------------------


def flow_mermaid() -> str:
    lines = ["flowchart LR"]
    for stage in stages():
        node = str(stage["id"]).replace("-", "_")
        lines.append(f'  {node}["{stage.get("name", stage["id"])}"]')
    for src, dst, label in flow_edges():
        a = src.replace("-", "_")
        b = dst.replace("-", "_")
        lines.append(f"  {a} -->|{label}| {b}")
    return "\n".join(lines) + "\n"


def _stage_table() -> list[str]:
    lines = [
        "| Stage | Owner component | Owner | Plane | Responsibility |",
        "|-------|-----------------|-------|-------|----------------|",
    ]
    for stage in stages():
        owner = stage.get("owner", "")
        co = stage.get("co_owner")
        owner_cell = f"`{owner}`" + (f" + `{co}`" if co else "")
        lines.append(
            f"| `{stage['id']}` | {owner_cell} | {stage.get('owner_label', '')} "
            f"| {stage.get('plane', '')} | {stage.get('responsibility', '')} |"
        )
    return lines


def _reference_table(manifest_source: str) -> list[str]:
    return [
        "| What | Canonical source |",
        "|------|------------------|",
        f"| Model list, roles, licences, gated access | `{CANONICAL_REPO}` → `{CANONICAL_MANIFEST}` |",
        f"| Load the manifest | `{MANIFEST_CLI}` |",
        f"| Role view | `{ROLES_CLI}` |",
        "| Resource placement (already-selected capability) | `kvnloo/kerdoios` |",
        "| External evidence and hypotheses | `kvnloo/frontier-kb` |",
        f"| Resolution on this machine | {manifest_source} |",
    ]


def render_markdown(manifest: dict[str, Any] | None = None, *, manifest_source: str | None = None) -> str:
    """Reference view. When a manifest is supplied, append the live model rows.

    The committed ``generated/cognition-portfolio.md`` is always rendered
    **without** a manifest: z0 links the model list, it does not store it.
    ``z0 cognition portfolio`` and ``scripts/cognition-check`` pass a manifest
    to exercise the read path.
    """
    resolved = manifest is not None
    if manifest_source is None:
        manifest_source = (
            f"`{manifest_path()}`" if manifest_path() else "not resolved (reference only)"
        )
    lines = [
        "# Local cognition portfolio",
        "",
        "_Generated from `registry/cognition.yaml`. Do not edit by hand._",
        "",
        "z0 owns the **stage map** and the **owner** of each stage. It does not own model",
        "identity, roles, licences, benchmarks, measurements or promotion state — those are",
        "canonical in z0intelligence and referenced, never copied. Kerdoios owns placement of an",
        "already-selected capability; frontier-kb owns external evidence.",
        "",
        "## Dataflow",
        "",
        *_stage_table(),
        "",
        "```mermaid",
        flow_mermaid().rstrip(),
        "```",
        "",
        "## Model list (referenced from z0intelligence)",
        "",
        *_reference_table(manifest_source),
        "",
        "Render the live portfolio on this machine:",
        "",
        "```bash",
        "./z0 cognition portfolio          # human view",
        "./z0 cognition portfolio --json   # machine view",
        "```",
        "",
    ]
    if resolved:
        lines += [
            "## Resolved model rows (live read — not committed)",
            "",
            "This section appears only when a manifest is resolved. It is rendered from",
            f"`{CANONICAL_REPO}` and is deliberately absent from the committed file.",
            "",
            "| Model | Roles | Default for | Params | Licence | Commercial | Gated | Measured locally | State |",
            "|-------|-------|-------------|--------|---------|------------|-------|------------------|-------|",
        ]
        for row in model_rows(manifest):
            roles = ", ".join(row["roles"]) or "-"
            lines.append(
                f"| `{row['model_id']}` | {roles} | {row.get('role_default_for') or '-'} "
                f"| {row.get('parameters') or '-'} | {row.get('license') or '-'} "
                f"| {row.get('commercial_use')} | {row.get('gated_access')} "
                f"| {row.get('measured_locally')} | {row.get('promotion_state') or '-'} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_json(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": registry.cognition_flow().get("schema", "z0.cognition_flow.v1"),
        "canonical": canonical(),
        "stages": stages(),
        "flow": flow_edges(),
        "manifest_resolved": manifest is not None,
        "models": model_rows(manifest),
    }
