"""Shared helpers for the Z1 onboard tests (stdlib unittest only).

PyYAML is needed to read the registry. Without it the registry-backed tests skip,
unless Z0_REQUIRE_YAML=1 (CI), which turns that skip into a failure.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

FIXTURES = ROOT / "tests/onboard/fixtures/hosts"
EXPECTED = ROOT / "tests/onboard/expected"

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_YAML = False

try:
    import jsonschema
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - optional
    jsonschema = None


def require_yaml(test_case):
    """Decorator: skip without PyYAML, or fail when CI requires it."""
    if HAVE_YAML:
        return test_case
    if os.environ.get("Z0_REQUIRE_YAML") == "1":
        def fail(self):
            self.fail("PyYAML is required here (Z0_REQUIRE_YAML=1)")
        return type(test_case.__name__, (unittest.TestCase,), {"test_pyyaml_present": fail})
    return unittest.skip("PyYAML not installed")(test_case)


_SNAP = None


def snapshot() -> dict:
    global _SNAP
    if _SNAP is None:
        from z0.onboard import regsnap
        _SNAP = regsnap.load(ROOT)
    return json.loads(json.dumps(_SNAP))  # a private copy per caller


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def fixture_names() -> list:
    return sorted(p.stem for p in FIXTURES.glob("*.json"))


ALL_BUNDLES = {"bundles": ["toolchains", "harness", "services", "models"], "source": "flag"}

# (expected file stem, fixture, plan kwargs)
GOLDEN_CASES = [
    ("groot-nvidia-32g.auto", "groot-nvidia-32g", {}),
    ("groot-nvidia-32g.auto-yes", "groot-nvidia-32g", {"grants": ALL_BUNDLES}),
    ("mbp-cpu-15g.auto", "mbp-cpu-15g", {}),
    ("mbp-cpu-15g.guided-personal", "mbp-cpu-15g", {"mode": "guided", "profile": "personal"}),
    ("apple-m-32g.auto", "apple-m-32g", {}),
    ("tiny-4g-vps.auto", "tiny-4g-vps", {}),
    ("offline.auto", "offline", {}),
    ("host-mismatch.auto", "host-mismatch", {}),
]


def render(plan_obj: dict) -> str:
    return json.dumps(plan_obj, indent=2, sort_keys=True) + "\n"


def validator(name: str):
    if jsonschema is None:
        return None
    names = ("host-profile", "onboard-step", "onboard-plan", "onboard-receipt", "onboarding")
    load = lambda n: json.loads((ROOT / f"schemas/{n}.schema.json").read_text())  # noqa: E731
    registry = Registry().with_resources([(load(n)["$id"], Resource.from_contents(load(n)))
                                          for n in names])
    return jsonschema.Draft202012Validator(load(name), registry=registry)


def simulate_apply(host: dict, plan_obj: dict) -> dict:
    """The host as it would be after APPLY ran every `todo` step (law I1's left side).

    Effects are modelled from what each step declares: created/probed paths become
    `workspace.owned`, toolchains become present at their pin, and an adopted clone
    is recorded. No step's real action runs.
    """
    after = json.loads(json.dumps(host))
    owned = set(after.setdefault("workspace", {}).setdefault("owned", []))
    for entry in plan_obj["steps"]:
        if entry["state"]["status"] != "todo":
            continue
        step = entry["step"]
        owned.update(step.get("creates") or [])
        if (step.get("probe") or {}).get("exists"):
            owned.add(step["probe"]["exists"])
        if step["kind"] == "ensure_toolchain":
            tool = step["id"].split(".", 1)[1]
            if tool in ("python-window", "python3"):
                after["python_window"] = "present"
            else:
                after.setdefault("toolchains", {})[tool] = {
                    "state": "present", "version": step["toolchain"]["version"],
                    "sh_resolves": True, "source": "z0_toolchain",
                    "path": f"/opt/z0-test/{tool}"}
    after["workspace"]["owned"] = sorted(owned)
    return after
