"""Load Zer0 registry YAML and resolve install profiles."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registry"

COMPONENT_KINDS = frozenset({
    "runtime", "measurement", "desktop", "intelligence", "compute", "research",
    "contract", "observability", "memory-source", "service", "worker-coordinator", "sensor",
})


def aodl_harness_ids(path: str | Path | None = None) -> set[str]:
    """Read ids from AODL, never from a second catalog maintained in z0.

    Z0_AODL_CATALOG selects a local checkout for offline checks. Otherwise read
    the upstream authority declared in registry/harnesses.yaml; failure is fatal.
    """
    path = path or os.environ.get("Z0_AODL_CATALOG")
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        source = harness_catalog()
        url = (
            f"https://raw.githubusercontent.com/{source['authority']}/"
            f"{source.get('ref', 'main')}/{source['path']}"
        )
        with urlopen(url, timeout=15) as response:
            data = json.load(response)
    ids = data.get("supported")
    if not isinstance(ids, list) or not ids or any(
        not isinstance(hid, str) or not hid.strip() for hid in ids
    ):
        raise ValueError("AODL catalog must contain a nonempty supported id list")
    if len(ids) != len(set(ids)):
        raise ValueError("AODL catalog contains duplicate supported ids")
    return set(ids)


def _string_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{where} must be a list of nonempty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{where} contains duplicates")
    return value


def _validate_mcp(value: Any, where: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be a mapping")
    unknown = value.keys() - {"command", "args", "env", "url", "headers"}
    if unknown:
        raise ValueError(f"{where} has unknown fields: {sorted(unknown)}")
    if ("command" in value) == ("url" in value):
        raise ValueError(f"{where} requires exactly one of command or url")
    target = "command" if "command" in value else "url"
    if not isinstance(value[target], str) or not value[target].strip():
        raise ValueError(f"{where}.{target} must be a nonempty string")
    if "args" in value:
        if target != "command":
            raise ValueError(f"{where}.args requires command")
        if not isinstance(value["args"], list) or any(
            not isinstance(arg, str) for arg in value["args"]
        ):
            raise ValueError(f"{where}.args must be a list of strings")
    for field in ("env", "headers"):
        if field not in value:
            continue
        if (field == "env") != (target == "command"):
            raise ValueError(f"{where}.{field} is not valid for {target}")
        entries = value[field]
        if not isinstance(entries, dict) or any(
            not isinstance(key, str) or not key.strip() or not isinstance(item, str)
            for key, item in entries.items()
        ):
            raise ValueError(f"{where}.{field} must map nonempty strings to strings")


def validate_components(
    comps: dict[str, dict[str, Any]] | None = None,
    *,
    harness_ids: set[str] | None = None,
) -> None:
    """Validate component metadata and declarative bindings, not live enablement."""
    comps = components() if comps is None else comps
    if not isinstance(comps, dict):
        raise ValueError("components must be a mapping")
    vocabulary = maturity()
    for cid, meta in comps.items():
        where = f"component {cid}"
        if not isinstance(meta, dict):
            raise ValueError(f"{where} must be a mapping")
        for field, allowed in (
            ("kind", COMPONENT_KINDS), ("status", vocabulary["status"]),
            ("execution", vocabulary["execution"]),
        ):
            if field == "execution" and field not in meta:
                continue
            value = meta.get(field)
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(f"{where} has unknown {field} {value!r}")
        if "service" in meta:
            service = meta["service"]
            if not isinstance(service, dict) or set(service) != {"unit"} or not isinstance(service["unit"], str):
                raise ValueError(f"{where}.service requires a unit name")
            if not re.fullmatch(r"[A-Za-z0-9_@.:-]+\.(service|socket|timer|target)", service["unit"]):
                raise ValueError(f"{where}.service.unit must be a systemd unit name")
        if "observed" in meta:
            observed = meta["observed"]
            if not isinstance(observed, dict):
                raise ValueError(f"{where}.observed must be a mapping")
            for field in ("at", "host", "summary"):
                if not isinstance(observed.get(field), str) or not observed[field].strip():
                    raise ValueError(f"{where}.observed.{field} must be a nonempty string")
            sources = _string_list(observed.get("evidence"), f"{where}.observed.evidence")
            if not sources:
                raise ValueError(f"{where}.observed requires evidence")
        if "evidence_source_for" in meta:
            _string_list(meta["evidence_source_for"], f"{where}.evidence_source_for")
        if "bindings" not in meta:
            continue
        bindings = meta["bindings"]
        if not isinstance(bindings, dict):
            raise ValueError(f"{where}.bindings must be a mapping")
        ids = _string_list(bindings.get("harnesses", []), f"{where}.bindings.harnesses")
        if harness_ids is None:
            harness_ids = aodl_harness_ids()
        unknown = set(ids) - harness_ids
        if unknown:
            raise ValueError(f"{where} references unknown AODL harness ids: {sorted(unknown)}")
        if "mcp" in bindings:
            _validate_mcp(bindings["mcp"], f"{where}.bindings.mcp")
        for hid, override in bindings.items():
            if hid in {"mcp", "harnesses"}:
                continue
            if hid not in ids:
                raise ValueError(f"{where}.bindings.{hid} is not in bindings.harnesses")
            if not isinstance(override, dict):
                raise ValueError(f"{where}.bindings.{hid} must be a mapping")
            if "memory_provider" in override and override["memory_provider"] is not None and (
                not isinstance(override["memory_provider"], str)
                or not override["memory_provider"].strip()
            ):
                raise ValueError(f"{where}.bindings.{hid}.memory_provider must be a string or null")
            if "mcp" in override:
                _validate_mcp(override["mcp"], f"{where}.bindings.{hid}.mcp")


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


def suite() -> dict[str, dict[str, Any]]:
    return _load("suite.yaml").get("repositories", {})


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
