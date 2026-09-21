"""Load Zer0 registry YAML and resolve install profiles."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registry"


def _load(name: str) -> dict[str, Any]:
    path = REGISTRY / name
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def components() -> dict[str, dict[str, Any]]:
    return _load("components.yaml").get("components", {})


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


def resolve_profile(name: str) -> list[str]:
    """Expand profile + extends chain into ordered component ids."""
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
