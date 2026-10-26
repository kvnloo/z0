"""`adopt_or_clone` (§2.5): match by origin. A clean adopted tree is used in place for
repo-local work (the plan chose it); it is recorded as `adopted` and never written to,
checked out or moved. Otherwise z0 makes its own clone at the plan's tree
(`$Z0_HOME/repos/<name>`), detached at the pin. Undo: remove the clone only if this run
created it (its `.z0-owned` marker names the run).

The step's argv (z0evals: `git fetch origin main dev nightly preview`) runs in z0's own
clone after the checkout; a failure there is a warning, not a failed step, because the
pinned tree is already complete.
"""
from __future__ import annotations

import os
import shutil

from .base import ActionCtx, ActionError, Outcome


def source_url(ctx: ActionCtx, comp: dict) -> str:
    repo = str(comp.get("repo") or "")
    url = ctx.urls.get(repo) or (comp.get("install") or {}).get("clone")
    if not url:
        raise ActionError(f"no clone URL for {repo or 'this component'}")
    return str(url)


def git(ctx: ActionCtx, step: dict, args: list, cwd: str, timeout: float = 900):
    env = ctx.env_for(step)
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_ASKPASS="", SSH_ASKPASS="")
    return ctx.exec(["git", *args], cwd=cwd, env=env, timeout=timeout)


def checkout_pin(ctx: ActionCtx, step: dict, url: str, dest: str, pin: str) -> None:
    """Clone `url` into `dest` and detach at `pin`, with submodules (and LFS objects
    when the tree uses LFS and git-lfs is present)."""
    parent = os.path.dirname(dest)
    if not git(ctx, step, ["clone", "--quiet", "--no-checkout", url, dest], cwd=parent).ok:
        raise ActionError(f"git clone of {ctx.form(url) if os.path.isabs(url) else url} failed")
    if not git(ctx, step, ["-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", pin],
               cwd=dest).ok:
        raise ActionError(f"pin {pin[:12]} is not in the clone")
    if os.path.isfile(os.path.join(dest, ".gitmodules")):
        if not git(ctx, step, ["submodule", "update", "--quiet", "--init", "--recursive"], cwd=dest).ok:
            raise ActionError("git submodule update failed")
    attrs = os.path.join(dest, ".gitattributes")
    if os.path.isfile(attrs) and "filter=lfs" in open(attrs, encoding="utf-8", errors="replace").read():
        if ctx.resolve("git-lfs", dest, ctx.env_for(step)):
            if not git(ctx, step, ["lfs", "pull"], cwd=dest).ok:
                raise ActionError("git lfs pull failed")
        else:
            ctx.warnings.append(f"{step['id']}: the tree uses Git LFS but git-lfs is not installed")


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    cid = step["component"]
    entry = (ctx.plan.get("components") or {}).get(cid) or {}
    tree = ctx.tree(cid)
    if not tree:
        raise ActionError(f"the plan names no tree for {cid}")
    if entry.get("adopted"):
        ctx.record({"kind": "adopted", "path": ctx.form(tree)})
        return Outcome(True, f"adopted the clean checkout at {ctx.form(tree)} (used in place)")
    comp = ctx.component(cid)
    pin = str((comp.get("install") or {}).get("ref") or "")
    if not pin:
        raise ActionError(f"{cid} has no pinned ref")
    url = source_url(ctx, comp)
    # Crash safety: clone into a z0-named staging dir and rename it into place, so a run
    # that is killed mid-clone (an agent's shell timeout, Ctrl-C) leaves no half tree at
    # `tree`; the next run removes the stale staging dir (only z0 uses that name).
    staging = f"{tree}.z0-partial"
    if os.path.lexists(staging):
        shutil.rmtree(staging, ignore_errors=True)
    with ctx.creating(tree):
        try:
            checkout_pin(ctx, step, url, staging, pin)
            os.rename(staging, tree)
        finally:
            if os.path.lexists(staging):
                shutil.rmtree(staging, ignore_errors=True)
    detail = f"cloned {comp.get('repo')} at {pin[:12]} into {ctx.form(tree)}"
    if step.get("argv"):
        if not git(ctx, step, list(step["argv"])[1:], cwd=tree, timeout=step.get("timeout_s", 600)).ok:
            ctx.warnings.append(f"{step['id']}: `{' '.join(step['argv'])}` failed (the pinned tree is complete)")
    return Outcome(True, detail)
