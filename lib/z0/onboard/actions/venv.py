"""`venv` (§2.5): an owned virtualenv, one per component (never shared). Undo: remove
the owned venv.

The step's argv runs when it has one (z0evals: `python3 -m venv .venv` in its tree);
otherwise `python3 -m venv <target>`, with the python3 of the prepared PATH (T1). The
venv is never made with `--system-site-packages` and never touches system Python.
"""
from __future__ import annotations

import os

from .base import ActionCtx, ActionError, Outcome


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    target = ctx.venv_dir(step)
    if not target:
        raise ActionError("venv step names no target (`creates` or a `bin/python` probe)")
    cwd = ctx.workdir(step)
    argv = list(step.get("argv") or ["python3", "-m", "venv", target])
    if "--system-site-packages" in argv:
        raise ActionError("a shared-site venv is never made")
    with ctx.creating(target):
        result = ctx.exec(argv, cwd=cwd, env=ctx.env_for(step), timeout=step.get("timeout_s", 600))
        if not result.ok:
            raise ActionError(f"venv creation failed (rc {result.rc})")
        if not os.path.exists(os.path.join(target, "bin", "python")):
            raise ActionError(f"{ctx.form(target)}/bin/python is missing after venv creation")
    return Outcome(True, f"venv at {ctx.form(target)}")
