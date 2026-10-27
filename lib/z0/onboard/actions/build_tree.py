"""`build_tree` (§2.5): a z0-owned tree at one SHA, with `.git`, submodules and LFS
objects, for the steps that need git metadata (rollout.py, dash scripts, static gates).
It is never what live code runs from: `stage_release` copies it without `.git`.
Undo: remove the owned tree.

The tree is cloned from the component's origin (or the test/container URL override)
and detached at the SHA named by the step's `creates` path (`.../<id>/<sha>`).
"""
from __future__ import annotations

import os
import re

from .adopt_or_clone import checkout_pin, source_url
from .base import ActionCtx, ActionError, Outcome


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    if not step.get("creates"):
        raise ActionError("build_tree needs a `creates` path")
    dest = ctx.expand(step["creates"][0])
    sha = os.path.basename(dest.rstrip("/"))
    comp = ctx.component(step["component"])
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        sha = str((comp.get("install") or {}).get("ref") or "")
    if not sha:
        raise ActionError("no SHA for the build tree")
    with ctx.creating(dest):
        checkout_pin(ctx, step, source_url(ctx, comp), dest, sha)
    return Outcome(True, f"build tree at {sha[:12]}")
