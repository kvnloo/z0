"""`run` (§2.5): argv only (no shell), in the step's `where`, env from the allowlist,
with a timeout; `creates` or `probe` is required (registry-check enforces it too).
Every `creates` path must exist afterwards; the ones this step newly made are
journaled (dirs marked owned, files hashed). Undo: a declared `undo`, else what was
journaled; nothing else is ever deleted.
"""
from __future__ import annotations

import os

from .base import ActionCtx, ActionError, Outcome


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    argv = list(step.get("argv") or [])
    if not argv:
        raise ActionError("run step has no argv")
    if not step.get("creates") and not (step.get("probe") or {}).get("exists"):
        raise ActionError("run step has neither `creates` nor `probe` (refused)")
    cwd = ctx.workdir(step)
    venv = ctx.venv_of(step)
    created = [ctx.expand(p) for p in step.get("creates") or []]
    existed = {p: os.path.lexists(p) for p in created}
    result = ctx.exec(argv, cwd=cwd, env=ctx.env_for(step, venv=venv),
                      timeout=step.get("timeout_s", 600))
    if not result.ok:
        raise ActionError(f"`{' '.join(argv)}` failed (rc {result.rc})")
    missing = [p for p in created if not os.path.lexists(p)]
    if missing:
        raise ActionError(f"did not create {', '.join(ctx.form(p) for p in missing)}")
    for path in created:
        if not existed[path]:
            ctx.record_created(path)
    probe = (step.get("probe") or {}).get("exists")
    if probe and not os.path.lexists(ctx.expand(probe)):
        raise ActionError(f"{probe} does not exist after the run")
    return Outcome(True, "ok", ctx.tail(result.out))
