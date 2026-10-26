"""z0intelligence acceptance (design §8.4, work package Z3).

- `runtime`: `~/.z0int/bin/python` exists, is executable and points into a runtime venv
  that is not inside a git checkout (principle 5: live code never runs from a checkout);
- `import`: the import check step passed (z0int, mcp, aodl_contract, fff, typesafe_sdk);
- `harness_plugins`: one line per detected, allowed harness: plugin installed (stamp
  present) or the ask that finishes it; a missing plugin is never a failure (C1);
- `router`: the loopback router answers /healthz when its unit was installed by this run
  or adopted; otherwise unavailable with the reason.
"""
from __future__ import annotations

import os
import re

from ..actions.base import has_git_ancestor

PLUGIN_STEPS = {"claude-code": "z0intelligence.plugin.claude", "codex": "z0intelligence.plugin.codex",
                "omp": "z0intelligence.plugin.omp"}
_EXEC = re.compile(r'^exec "([^"]+)"', re.M)


def _entry(name, status, detail, required=True, warnings=None):
    out = {"component": "z0intelligence", "name": name, "status": status, "detail": detail,
           "required": required}
    if warnings:
        out["warnings"] = warnings
    return out


def _shim_target(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            match = _EXEC.search(fh.read(4096))
    except OSError:
        return None
    return match.group(1) if match else None


def evaluate(view) -> list:
    if "z0intelligence" not in (view.plan.get("targets") or []):
        return []
    summary = (view.plan.get("components") or {}).get("z0intelligence") or {}
    if summary.get("verdict") not in (None, "allow"):
        return [_entry("runtime", "unavailable", f"z0intelligence is {summary.get('verdict')} "
                                                 f"({summary.get('reason', '')})", required=False)]
    ctx = view.ctx
    out = []
    shim = ctx.expand("~/.z0int/bin/python")
    shim_status = view.check_status("z0intelligence.shim") if "z0intelligence.shim" in view.steps else "skipped"
    if os.access(shim, os.X_OK):
        target = _shim_target(shim)
        if target and has_git_ancestor(os.path.dirname(os.path.dirname(target))):
            out.append(_entry("runtime", "failed", "the shim points into a git checkout (principle 5)"))
        else:
            out.append(_entry("runtime", "passed", "~/.z0int/bin/python -> runtime venv"))
    elif shim_status in ("failed",):
        out.append(_entry("runtime", "failed", "the shim step failed"))
    else:
        out.append(_entry("runtime", "unavailable", "no shim (C1 `services` not granted, or blocked)",
                          required=False))

    if "z0intelligence.checks.import" in view.steps:
        status = view.check_status("z0intelligence.checks.import")
        out.append(_entry("import", status, view.results.get("z0intelligence.checks.import", {}).get("reason", ""),
                          required=status != "unavailable"))

    lines, warnings = [], []
    for harness, sid in PLUGIN_STEPS.items():
        entry = (view.ctx.host.get("harnesses") or {}).get(harness) or {}
        if entry.get("state") != "installed":
            continue
        status = view.check_status(sid) if sid in view.steps else "skipped"
        lines.append(f"{harness}={status}")
        if status != "passed":
            warnings.append(f"z0intelligence plugin for {harness}: {status}; finish with "
                            "`./z0 onboard --auto --accept harness`")
    if lines:
        bad = any(s.endswith("=failed") for s in lines)
        out.append(_entry("harness_plugins", "failed" if bad else "passed", ", ".join(lines),
                          required=False, warnings=warnings))
    else:
        out.append(_entry("harness_plugins", "unavailable", "no supported harness detected", required=False))

    if "z0intelligence.router.unit" in view.steps:
        status = view.check_status("z0intelligence.router.unit")
        out.append(_entry("router", status, view.results.get("z0intelligence.router.unit", {}).get("reason", ""),
                          required=False))
    else:
        out.append(_entry("router", "unavailable", "no systemd user session (no unit planned)", required=False))
    return out
