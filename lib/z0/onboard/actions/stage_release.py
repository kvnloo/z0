"""`stage_release` (§2.5, law S1): copy the build tree without `.git` to
`<release_root>/<id>/<sha>` and write `deployed.json`. Dependencies are installed *in
the release* by the steps that follow (`where: release`). Live code (units, shims,
plugins, env files) points only at releases like this one, never at a checkout.
Undo: remove it, unless a `*-current` link points at it.
"""
from __future__ import annotations

import json
import os
import shutil

from .base import ActionCtx, ActionError, Outcome

SKIP = (".git", ".z0-owned")


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    if not step.get("creates"):
        raise ActionError("stage_release needs a `creates` path")
    dest = ctx.expand(step["creates"][0])
    source_step = ctx.nearest(step, ("build_tree",))
    if source_step is not None and source_step.get("creates"):
        source = ctx.expand(source_step["creates"][0])
    else:
        source = ctx.tree(step["component"])
    if not source or not os.path.isdir(source):
        raise ActionError("no build tree to stage from")
    comp = ctx.component(step["component"])
    sha = os.path.basename(dest.rstrip("/"))
    with ctx.creating(dest):
        shutil.copytree(source, dest, symlinks=True, ignore=shutil.ignore_patterns(*SKIP))
        stamp = {"component": step["component"], "repo": comp.get("repo"), "sha": sha,
                 "source": ctx.form(source), "run": ctx.run_id, "step": step["id"]}
        with open(os.path.join(dest, "deployed.json"), "w", encoding="utf-8") as fh:
            json.dump(stamp, fh, indent=2, sort_keys=True)
            fh.write("\n")
    return Outcome(True, f"release {sha[:12]} staged at {ctx.form(dest)}")
