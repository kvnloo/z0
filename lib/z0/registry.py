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


def resolve_profile(name: str) -> list[str]:
    """Expand profile inheritance parent-first into ordered component ids."""
    profs = profiles()
    if name not in profs:
        raise KeyError(f"unknown profile: {name}")

    resolved: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(profile: str) -> None:
        if profile not in profs:
            raise KeyError(f"unknown profile: {profile}")
        if profile in visiting:
            raise ValueError(f"profile inheritance cycle at {profile}")
        if profile in visited:
            return

        visiting.add(profile)
        spec = profs[profile]
        parent = spec.get("extends")
        if parent:
            visit(str(parent))
        for cid in spec.get("components", []):
            if cid not in resolved:
                resolved.append(cid)
        visiting.remove(profile)
        visited.add(profile)

    visit(name)
    return resolved


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
