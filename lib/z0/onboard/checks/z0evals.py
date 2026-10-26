"""z0evals acceptance (design §8.2): the first end-to-end target.

- `tiers`: tier 0 (stdlib python) and tier 1 (the venv) passed; tier 2 (the web
  export) passed, or is unavailable for a stated reason (offline, no node);
- `venv`: the component's own venv exists and is the interpreter tier 1 ran with;
- `worktree_status`: `git status --porcelain` holds only the allowlisted generated
  file (`?? web/data/optchat-long-horizon-v0.json`); anything else is reported;
- `no_private_paths`: no z0evals effect touched `~/.z0int` or `~/.hermes` (§8.2 step 9).
"""
from __future__ import annotations

import os

ALLOWED_PORCELAIN = ("?? web/data/optchat-long-horizon-v0.json",)
FORBIDDEN = ("~/.z0int", "~/.hermes")
REQUIRED_TIERS = ("tier0", "tier1")
OPTIONAL_TIERS = ("tier2",)


def _entry(name, status, detail, required=True, warnings=None):
    out = {"component": "z0evals", "name": name, "status": status, "detail": detail, "required": required}
    if warnings:
        out["warnings"] = warnings
    return out


def evaluate(view) -> list:
    if "z0evals" not in (view.plan.get("targets") or []):
        return []
    summary = (view.plan.get("components") or {}).get("z0evals") or {}
    if summary.get("verdict") not in (None, "allow"):
        return [_entry("tiers", "unavailable", f"z0evals is {summary.get('verdict')} "
                                               f"({summary.get('reason', '')})", required=False)]
    tiers = view.acceptance.get("z0evals") or {}
    if all(tiers.get(t) == "unavailable" for t in REQUIRED_TIERS):
        return [_entry("tiers", "unavailable", "no tier can run on this host (see Unavailable)",
                       required=False)]
    bad = [t for t in REQUIRED_TIERS if tiers.get(t) != "passed"]
    optional = {t: tiers.get(t, "skipped") for t in OPTIONAL_TIERS}
    if any(v == "failed" for v in optional.values()):
        bad += [t for t, v in optional.items() if v == "failed"]
    detail = ", ".join(f"{t}={tiers.get(t, 'skipped')}" for t in REQUIRED_TIERS + OPTIONAL_TIERS)
    out = [_entry("tiers", "failed" if bad else "passed", detail)]

    tree = view.ctx.tree("z0evals")
    venv = os.path.join(tree, ".venv") if tree else None
    if venv and os.path.isfile(os.path.join(venv, "bin", "python")):
        out.append(_entry("venv", "passed", f"{view.ctx.form(venv)}"))
    elif tiers.get("tier1") == "passed":
        out.append(_entry("venv", "failed", "tier 1 passed but the venv is missing"))
    else:
        out.append(_entry("venv", "unavailable", "no venv", required=False))

    if tree and os.path.isdir(os.path.join(tree, ".git")):
        env = view.ctx.env_for({"id": "z0evals.porcelain"})
        result = view.ctx.runner(["git", "--no-optional-locks", "status", "--porcelain"], tree, env, 60)
        if result.rc == 0:
            extra = [line for line in result.out.splitlines()
                     if line.strip() and line.rstrip() not in ALLOWED_PORCELAIN]
            warnings = [f"z0evals worktree: unexpected `{line.strip()}`" for line in extra[:20]]
            out.append(_entry("worktree_status", "passed",
                              "only allowlisted changes" if not extra else f"{len(extra)} unexpected path(s) reported",
                              required=False, warnings=warnings))
        else:
            out.append(_entry("worktree_status", "skipped", "git status failed", required=False))

    touched = [e["effect"]["path"] for e in view.effects
               if e.get("step", "").startswith("z0evals.")
               and any(str(e["effect"].get("path", "")).startswith(p) for p in FORBIDDEN)]
    out.append(_entry("no_private_paths", "failed" if touched else "passed",
                      "never touches ~/.z0int or ~/.hermes"))
    return out
