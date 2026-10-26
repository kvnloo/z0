"""APPLY actions, one module per closed step kind (design §2.5).

Each module exports `execute(ctx, step) -> Outcome` and raises ActionError on failure.
`ask` steps never execute. `service_unit`, `harness_plugin` and `delegate` arrive with
work packages Z3/Z4 (their consent bundles are never granted silently in the meantime:
a step of those kinds fails cleanly and blocks only its dependents).
"""
from __future__ import annotations

from . import (adopt_or_clone, build_tree, check, ensure_toolchain, pip_install, run, stage_release,
               swap_current, venv, write_file)
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
}
LATER = {"service_unit": "Z3/Z4", "harness_plugin": "Z3", "delegate": "Z3"}

__all__ = ["ACTIONS", "LATER", "ActionCtx", "ActionError", "Outcome"]
