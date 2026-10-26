"""`write_file` (§2.5): render a file atomically (umask 077, mode checked after the
write), its hash in the journal; an existing file is backed up first. Undo: delete it
(or restore the backup) only if the hash is unchanged; otherwise keep it and report.

Two sources of content:
- `z0.path_links` (law P1): the z0-owned dir of links that replaces, on the prepared
  PATH, a shared bin dir that also holds a `configure: never` harness. Its links come
  from the plan's `path_links`.
- RENDERERS: a renderer per step id, registered by the work package that owns the
  file (Z3: the z0int shim and hermes.json; Z4: the dash env file and wait script).
  A step without one fails cleanly; nothing is written.
"""
from __future__ import annotations

import os
from typing import Callable, Dict

from .base import ActionCtx, ActionError, Outcome

# step id -> renderer(ctx, step) -> (bytes, mode)
RENDERERS: Dict[str, Callable] = {}


def _path_links(ctx: ActionCtx, step: dict) -> Outcome:
    links = ctx.plan.get("path_links") or []
    directory = ctx.expand(step["creates"][0])
    if os.path.isdir(directory):
        made = False
    else:
        with ctx.creating(directory):
            os.mkdir(directory, 0o755)
        made = True
    for link in links:
        path, target = ctx.expand(link["link"]), ctx.expand(link["target"])
        if os.path.dirname(path) != directory:
            raise ActionError(f"{link['link']} is outside {step['creates'][0]}")
        if os.path.islink(path) and os.readlink(path) == target:
            continue
        ctx.symlink(path, target)
    return Outcome(True, f"{len(links)} link(s) in {step['creates'][0]}" + ("" if made else " (dir kept)"))


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    if step["id"] == "z0.path_links":
        return _path_links(ctx, step)
    renderer = RENDERERS.get(step["id"])
    if renderer is None:
        raise ActionError(f"no renderer for {step['id']} yet (it ships with its component's "
                          "work package); nothing written")
    if not step.get("creates"):
        raise ActionError("write_file needs a `creates` path")
    data, mode = renderer(ctx, step)
    path = ctx.expand(step["creates"][0])
    digest = ctx.write_file(path, data, mode)
    return Outcome(True, f"wrote {step['creates'][0]} (sha256 {digest[:12]})")
