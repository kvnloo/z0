"""Registry snapshot for the onboarder: parsed YAML plus the sha256 of each file read.

The only module of the onboarder that imports PyYAML; detect/* and plan.py take the
parsed snapshot as data, so they stay stdlib-only and pure.
"""
from __future__ import annotations

from pathlib import Path

from .util import sha256_bytes

ROOT = Path(__file__).resolve().parents[3]
FILES = ("components", "profiles", "harnesses", "toolchains", "onboarding")


def load(root: Path = ROOT) -> dict:
    import yaml  # z0 venv (stage 0) or a python that already has PyYAML

    snap: dict = {"files": {}}
    for name in FILES:
        path = root / "registry" / f"{name}.yaml"
        raw = path.read_bytes()
        snap["files"][f"registry/{name}.yaml"] = sha256_bytes(raw)
        snap[name] = yaml.safe_load(raw.decode("utf-8")) or {}
    return snap


def components(snap: dict) -> dict:
    return snap.get("components", {}).get("components", {}) or {}


def profiles(snap: dict) -> dict:
    return snap.get("profiles", {}).get("profiles", {}) or {}


def profile_policy(snap: dict) -> dict:
    return snap.get("profiles", {}).get("onboard", {}) or {}


def harnesses(snap: dict) -> dict:
    return snap.get("harnesses", {}).get("harnesses", {}) or {}


def toolchains(snap: dict) -> dict:
    return snap.get("toolchains", {}) or {}


def onboarding(snap: dict) -> dict:
    return snap.get("onboarding", {}) or {}


def resolve_profile(snap: dict, name: str) -> list:
    """Same expansion as registry.resolve_profile, over the snapshot (pure)."""
    profs = profiles(snap)
    if name not in profs:
        raise KeyError(f"unknown profile: {name}")
    seen: list = []
    stack = [name]
    while stack:
        current = stack.pop()
        spec = profs[current]
        if "extends" in spec:
            stack.append(spec["extends"])
        for cid in spec.get("components", []) or []:
            if cid not in seen:
                seen.append(cid)
    return seen
