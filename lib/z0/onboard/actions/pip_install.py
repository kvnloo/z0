"""`pip_install` (§2.5): install into the component's own venv (the nearest `venv` step
the step needs). A bare `pip`/`pip3` argv runs as `<venv>/bin/python -m pip`; a
relative argv (`.venv/bin/pip`) runs from the component tree. The index URL is the one
the plan put in the argv (torch: §5.2). Env: PIP_NO_INPUT=1, VIRTUAL_ENV, the venv bin
first on PATH, and PIP_BREAK_SYSTEM_PACKAGES unset: system Python is never written.

Idempotence (I1): when the step's probe is a stamp under `<venv>/.z0/`, the stamp is
written after a successful install (and journaled with its hash); any other probe must
exist after the install or the step fails.
"""
from __future__ import annotations

import os

from .base import ActionCtx, ActionError, Outcome


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    venv = ctx.venv_of(step)
    if not venv or not os.path.exists(os.path.join(venv, "bin", "python")):
        raise ActionError("no owned venv to install into")
    argv = list(step.get("argv") or [])
    if not argv:
        raise ActionError("pip_install has no argv")
    if argv[0] in ("pip", "pip3"):
        argv = [os.path.join(venv, "bin", "python"), "-m", "pip", *argv[1:]]
    if "--break-system-packages" in argv:
        raise ActionError("--break-system-packages is never used")
    cwd = ctx.workdir(step)
    result = ctx.exec(argv, cwd=cwd, env=ctx.env_for(step, venv=venv), timeout=step.get("timeout_s", 1800))
    if not result.ok:
        raise ActionError(f"pip install failed (rc {result.rc})")
    probe = (step.get("probe") or {}).get("exists")
    if probe:
        path = ctx.expand(probe)
        if not os.path.exists(path):
            if os.path.basename(os.path.dirname(path)) == ".z0":
                _stamp(ctx, path, step)
            else:
                raise ActionError(f"{probe} does not exist after the install")
    return Outcome(True, f"installed into {ctx.form(venv)}")


def _stamp(ctx: ActionCtx, path: str, step: dict) -> None:
    """The stamp lives in the owned venv (repo-local and gitignored for a clean adopted
    checkout, C0); it is journaled with its hash."""
    ctx.makedirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"installed by z0 onboard run {ctx.run_id}: {' '.join(step.get('argv') or [])}\n")
    ctx.record_created(path)
