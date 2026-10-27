"""APPLY actions, one module per closed step kind (design §2.5).

Each module exports `execute(ctx, step) -> Outcome` and raises ActionError on failure.
`ask` steps never execute. `service_unit` and `harness_plugin` are work packages Z3/Z4;
`delegate` waits for the z0intelligence onboard contract (WP-I1): a step of that kind
fails cleanly and blocks only its dependents.
"""
from __future__ import annotations

from . import (adopt_or_clone, build_tree, check, ensure_toolchain, harness_plugin, pip_install,
               renderers, run, service_unit, stage_release, swap_current, venv, write_file)
from .base import ActionCtx, ActionError, Outcome

ACTIONS = {
    "ensure_toolchain": ensure_toolchain.execute,
    "adopt_or_clone": adopt_or_clone.execute,
    "build_tree": build_tree.execute,
    "stage_release": stage_release.execute,
    "swap_current": swap_current.execute,
    "venv": venv.execute,
    "pip_install": pip_install.execute,
    "run": run.execute,
    "write_file": write_file.execute,
    "check": check.execute,
    "service_unit": service_unit.execute,
    "harness_plugin": harness_plugin.execute,
}
LATER = {"delegate": "the z0intelligence onboard contract (WP-I1)"}
write_file.RENDERERS.update(renderers.RENDERERS)

__all__ = ["ACTIONS", "LATER", "ActionCtx", "ActionError", "Outcome"]
