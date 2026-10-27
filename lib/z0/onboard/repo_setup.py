"""Repo-local `zer0.repo.yaml setup:` steps (design §2.6). Pure: data in, data out.

z0 reads the block only from the pinned SHA in its origin mirror, never from a working
tree (mirror.read_setups does that and vets each step with the registry step rules).
Here the vetted block meets the registry:

- The registry owns host-level and cross-repo steps. On a duplicate step id the
  registry wins; when the repo's step differs from the registry's, that is a conflict
  the plan reports (it never runs the repo's version).
- A repo step under a new id that repeats a registry step's argv would run the same
  thing twice: a conflict too, and it is not added.
- A new repo step is added to its component, except an effectful step without a path
  in `creates` or `probe.exists`: the plan could not tell that it already ran (law I1),
  so it is left out with a warning.

detect (workspace.owned) and plan both call `merge`, so they see the same steps.
"""
from __future__ import annotations

from typing import Optional

# What a step does. `needs` only orders steps (a repo chains its tiers; z0 orders by
# its own needs), so a different `needs` alone is not a conflict.
COMPARED = ("kind", "consent", "where", "target_where", "argv", "env", "when", "creates", "probe",
            "network", "timeout_s", "service", "harness", "toolchain")
KINDS_EFFECTFUL = ("ensure_toolchain", "adopt_or_clone", "build_tree", "stage_release",
                   "swap_current", "venv", "pip_install", "run", "write_file", "service_unit",
                   "harness_plugin", "delegate")
KINDS = KINDS_EFFECTFUL + ("check", "ask")


def source_key(entry: dict) -> str:
    """The plan's provenance key for a block: `<owner/repo>@<sha>:zer0.repo.yaml`."""
    return f"{entry.get('repo', '')}@{entry.get('ref', '')}:zer0.repo.yaml"


def usable(entry: Optional[dict], pin: str) -> bool:
    """Only a block read at this component's pin counts."""
    return bool(entry) and bool(pin) and entry.get("ref") == pin and isinstance(entry.get("setup"), dict)


def _body(step: dict) -> dict:
    return {key: step[key] for key in COMPARED if key in step}


def merge(cid: str, registry_steps: list, entry: dict) -> tuple:
    """(added steps, conflicts, warnings) for one component's vetted setup block."""
    registry = {s.get("id"): s for s in registry_steps}
    by_argv = {tuple(s["argv"]): s["id"] for s in registry_steps if s.get("argv")}
    source = source_key(entry)
    added, conflicts, warnings = [], [], []
    for raw in (entry.get("setup") or {}).get("steps") or []:
        step = {key: value for key, value in raw.items() if key != "component"}
        sid = str(step.get("id", ""))
        if sid in registry:
            mine, theirs = _body(registry[sid]), _body(step)
            fields = sorted(key for key in set(mine) | set(theirs) if mine.get(key) != theirs.get(key))
            if fields:
                conflicts.append({"component": cid, "id": sid, "fields": fields, "source": source,
                                  "resolution": "registry"})
            continue
        twin = by_argv.get(tuple(step.get("argv") or ()))
        if twin:
            conflicts.append({"component": cid, "id": sid, "fields": ["id"], "source": source,
                              "resolution": "registry", "registry_id": twin})
            continue
        if sid in {s["id"] for s in added}:
            warnings.append(f"{cid}: zer0.repo.yaml setup step {sid} is listed twice; the first wins")
            continue
        if not sid.startswith(f"{cid}.") or step.get("kind") not in KINDS:
            warnings.append(f"{cid}: zer0.repo.yaml setup step {sid or '?'} is not a {cid}.* step "
                            "of a closed kind; ignored")
            continue
        probe = step.get("probe") or {}
        if step["kind"] in KINDS_EFFECTFUL and not step.get("creates") and not probe.get("exists"):
            warnings.append(f"{cid}: zer0.repo.yaml setup step {sid} declares no creates or "
                            "probe.exists path, so z0 cannot tell that it already ran (I1); ignored")
            continue
        added.append(step)
    return added, conflicts, warnings


def vet(snap: dict, cid: str, setup: dict) -> tuple:
    """(setup with only the steps that pass the registry step rules, errors).

    Impure only through regcheck's import (it reads the step schema); callers are
    mirror.read_setups and scripts, never plan."""
    from .regcheck import check_step
    from . import regsnap

    never = {hid for hid, row in regsnap.harnesses(snap).items()
             if (row.get("policy") or {}).get("configure") == "never"}
    templates = regsnap.onboarding(snap).get("templates") or {}
    kept, errors = [], []
    for raw in (setup or {}).get("steps") or []:
        if not isinstance(raw, dict):
            errors.append(f"{cid}: setup step is not a mapping")
            continue
        body = {key: value for key, value in raw.items() if key != "component"}
        problems = check_step(cid, body, never, templates, snap, repo=True)
        if raw.get("component", cid) != cid:
            problems.append(f"component {cid} step {raw.get('id', '?')}: component must be {cid}")
        if problems:
            errors.extend(problems)
            continue
        kept.append(raw)
    out = dict(setup or {})
    out["steps"] = kept
    return out, errors
