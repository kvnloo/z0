"""`write_file` renderers for work packages Z3 (z0intelligence) and Z4 (dash).

Each renderer is `render(ctx, step) -> (bytes, mode)`. It reads only the plan, the
current detection (ctx.host) and paths this run made; it never reads a secret value.
Rendered files hold absolute paths of THIS host's home only (they live in that home,
never in a repo), so no host literal reaches the public tree.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .base import ActionCtx, ActionError

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def template(*parts: str) -> str:
    with open(os.path.join(TEMPLATES, *parts), encoding="utf-8") as fh:
        return fh.read()


def _runtime_python(ctx: ActionCtx, step: dict) -> str:
    """The z0int runtime venv's interpreter: the nearest `venv` step this step needs."""
    venv = ctx.venv_of(step)
    if not venv:
        raise ActionError("no z0intelligence runtime venv in this step's chain")
    python = os.path.join(venv, "bin", "python")
    if not os.access(python, os.X_OK):
        raise ActionError(f"{ctx.form(python)} is not an executable interpreter")
    return python


def z0int_shim(ctx: ActionCtx, step: dict):
    """~/.z0int/bin/python: the one interpreter every harness hook and MCP server runs
    (`${Z0INT_PYTHON:-$HOME/.z0int/bin/python}` in the z0int plugins). It points into the
    immutable runtime venv, never into a checkout (principle 5)."""
    python = _runtime_python(ctx, step)
    text = ("#!/bin/sh\n"
            "# z0int runtime interpreter (written by `z0 onboard`; re-run it to repoint)\n"
            f'exec "{python}" "$@"\n')
    return text.encode("utf-8"), 0o755


def z0int_hermes_json(ctx: ActionCtx, step: dict):
    """~/.z0int/config/hermes.json: the interpreter the Hermes adapter falls back to."""
    shim = ctx.expand("~/.z0int/bin/python")
    if not os.access(shim, os.X_OK):
        raise ActionError("~/.z0int/bin/python is missing (the shim step did not run)")
    return (json.dumps({"python": shim}, indent=2) + "\n").encode("utf-8"), 0o600


def z0int_service_env(ctx: ActionCtx, step: dict):
    """~/.config/z0intelligence/service.env for the loopback router unit."""
    shim = ctx.expand("~/.z0int/bin/python")
    lines = ["# z0intelligence router (written by `z0 onboard`; loopback only)",
             f"Z0INT_PYTHON={shim}", "Z0INT_BIND=127.0.0.1"]
    return ("\n".join(lines) + "\n").encode("utf-8"), 0o600


def _bridge_path(ctx: ActionCtx, bun: str) -> list:
    """The bridge's PATH: bun first, then the plan's prepared PATH. The prepared PATH
    already replaces any shared bin dir that holds a `configure: never` harness (grok,
    cursor-agent) with z0's link dir (law P1), so no excluded harness is reachable."""
    out = [bun]
    for directory in [ctx.expand(d) for d in ctx.plan.get("prepared_path") or []] + ["/usr/bin", "/bin"]:
        if directory not in out:
            out.append(directory)
    return out


def _bun_dir(ctx: ActionCtx) -> Optional[str]:
    for directory in ctx.extra_path + [ctx.expand(d) for d in ctx.plan.get("prepared_path") or []]:
        if os.access(os.path.join(directory, "bun"), os.X_OK):
            return directory
    return None


def dash_bridge_env(ctx: ActionCtx, step: dict):
    """~/.config/dash-services/bridge.env (§8.3 step 4). DASH_HOST is the tailnet IPv4
    of the current detection only (law S2); gate/supervision/approval vars stay unset."""
    ipv4 = (ctx.host.get("tailscale") or {}).get("ipv4")
    if not ipv4:
        raise ActionError("no tailnet IPv4 in the current detection; the bridge binds nowhere else")
    bun = _bun_dir(ctx)
    if not bun:
        raise ActionError("bun is not on the prepared PATH")
    path = _bridge_path(ctx, bun)
    lines = ["# dash bridge (written by `z0 onboard`)", f"DASH_HOST={ipv4}", "DASH_PORT=4747",
             f"DASH_CWD={ctx.home}", f"PATH={':'.join(path)}"]
    for key in ("HERMES_HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME"):
        value = ctx.base_env.get(key)
        if value:
            lines.append(f"{key}={value}")
    return ("\n".join(lines) + "\n").encode("utf-8"), 0o600


def dash_wait_tailnet(ctx: ActionCtx, step: dict):
    return template("dash", "dash-wait-tailnet.py").encode("utf-8"), 0o755


RENDERERS = {
    "z0intelligence.shim": z0int_shim,
    "z0intelligence.hermes_json": z0int_hermes_json,
    "z0intelligence.service_env": z0int_service_env,
    "dash.bridge.env": dash_bridge_env,
    "dash.bridge.wait_tailnet": dash_wait_tailnet,
}
