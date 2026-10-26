"""`swap_current` (§2.5, law S1): atomically point `<id>-current` at the staged release.
Undo: restore the previous target from the journal.

Before the swap the kernel decides the target's root kind (decide_exec_root): a target
with a `.git` ancestor is a checkout and is refused, so live code can never be pointed
at a mutable tree, whatever the registry says.
"""
from __future__ import annotations

import os

from .. import kernel as k
from .base import ActionCtx, ActionError, Outcome, has_git_ancestor


def root_kind(ctx: ActionCtx, path: str) -> "k.RootKind":
    if has_git_ancestor(path):
        return k.RootKind.CHECKOUT
    if os.path.isfile(os.path.join(path, "deployed.json")):
        return k.RootKind.RELEASE
    return k.RootKind.OTHER


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    if not step.get("creates"):
        raise ActionError("swap_current needs a `creates` link path")
    link = ctx.expand(step["creates"][0])
    release_step = ctx.nearest(step, ("stage_release",))
    if release_step is None or not release_step.get("creates"):
        raise ActionError("no staged release to point at")
    target = ctx.expand(release_step["creates"][0])
    verdict = k.decide_exec_root(root_kind(ctx, target))
    if verdict.kind is not k.Kind.ALLOW:
        raise ActionError(f"refused ({verdict.reason.name.lower()}): {ctx.form(target)} is not a "
                          "stamped release (S1)")
    ctx.symlink(link, target)
    return Outcome(True, f"{ctx.form(link)} -> {ctx.form(target)}")
