"""`service_unit` (§2.5, §8.3, §8.4): render a systemd *user* unit from a z0 template,
reload, enable, and (when its code is already in place) start it and wait for health.

Rules:
- templates live in `lib/z0/onboard/templates/systemd/<template>.service`; `%h` paths
  only, plus the absolute interpreter/bun paths this run resolved;
- an existing unit file is never silently replaced: the probe (the unit path) makes an
  existing unit `already_satisfied` (adopted, law S3); a unit is only written when absent;
- binds are closed classes (loopback | tailnet_ipv4); health is checked on that bind only
  (law S2) through the same probe as `check` (`verify.http`);
- a unit whose WorkingDirectory is a `*-current` link that does not exist yet is enabled
  but not started: its `swap_current` step starts it after the swap (§8.3 step 7);
- macOS (launchd) services are guided-only (§8.4) and never reach this action in auto.
Undo: the unit file is journaled (rollback removes it if unchanged); rollback does not
stop a running unit, the report lists `systemctl --user disable --now <unit>`.
"""
from __future__ import annotations

import os
import shutil
import time

from .base import ActionCtx, ActionError, Outcome
from .check import _http
from .renderers import template

DEFAULT_LIMITS = {"restart_sec": 3, "timeout_start_sec": 90, "memory_max": "1G"}


def systemctl(ctx: ActionCtx, step: dict, *args: str):
    env = ctx.env_for(step)
    for key in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
        if ctx.base_env.get(key):
            env[key] = ctx.base_env[key]
    return ctx.exec(["systemctl", "--user", *args], cwd=ctx.home, env=env, timeout=120,
                    label=f"{ctx.step_id}.systemctl")


def render(ctx: ActionCtx, step: dict) -> str:
    service = step.get("service") or {}
    name = service.get("template")
    if not name:
        raise ActionError("service_unit needs service.template")
    try:
        text = template("systemd", f"{name}.service")
    except OSError:
        raise ActionError(f"no unit template {name}.service") from None
    limits = dict(DEFAULT_LIMITS)
    limits.update(service.get("limits") or {})
    env = ctx.env_for(step)
    fills = {key: str(value) for key, value in limits.items()}
    if "{bun}" in text:
        bun = shutil.which("bun", path=env["PATH"])
        if not bun:
            raise ActionError("bun is not on the prepared PATH")
        fills["bun"] = bun
    if "{python}" in text:
        python = shutil.which("python3", path=env["PATH"])
        if not python:
            raise ActionError("python3 is not on the prepared PATH")
        fills["python"] = python
    for key, value in fills.items():
        text = text.replace("{" + key + "}", value)
    return text


def _workdir_ready(ctx: ActionCtx, text: str) -> bool:
    for line in text.splitlines():
        if line.startswith("WorkingDirectory="):
            path = line.split("=", 1)[1].replace("%h", ctx.home)
            return os.path.isdir(path)
    return True


def wait_healthy(ctx: ActionCtx, step: dict, budget_s: float = 60.0) -> Outcome:
    health = ((step.get("service") or {}).get("health") or {}).get("http")
    if not health:
        return Outcome(True, "started (no health probe declared)")
    deadline = time.monotonic() + budget_s
    last = None
    while time.monotonic() < deadline:
        try:
            return _http(ctx, health)
        except ActionError as exc:
            last = exc
            time.sleep(2)
    raise ActionError(f"not healthy after {budget_s:.0f}s: {last}")


def start_and_check(ctx: ActionCtx, step: dict) -> Outcome:
    unit = step["service"]["unit"]
    result = systemctl(ctx, step, "restart", unit)
    if result.rc != 0:
        raise ActionError(f"systemctl --user restart {unit} exited {result.rc}")
    return wait_healthy(ctx, step)


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    service = step.get("service") or {}
    unit = service.get("unit")
    if not unit or "/" in unit or not unit.endswith(".service"):
        raise ActionError("service.unit must be a bare *.service name")
    if service.get("bind") not in ("loopback", "tailnet_ipv4"):
        raise ActionError(f"bind {service.get('bind')!r} is not a closed bind class (S2)")
    if not shutil.which("systemctl", path=ctx.env_for(step)["PATH"]):
        raise ActionError("systemctl is not available (no systemd user session)")
    path = ctx.expand(f"~/.config/systemd/user/{unit}")
    if os.path.lexists(path):
        raise ActionError(f"{ctx.form(path)} exists and was not written by this run (adopt it; "
                          "z0 never replaces a unit it did not write)")
    text = render(ctx, step)
    ctx.write_file(path, text.encode("utf-8"), 0o644)
    for args in (("daemon-reload",), ("enable", unit)):
        result = systemctl(ctx, step, *args)
        if result.rc != 0:
            raise ActionError(f"systemctl --user {' '.join(args)} exited {result.rc}")
    if not _workdir_ready(ctx, text):
        return Outcome(True, f"{unit} written and enabled; it starts after its release swap")
    outcome = start_and_check(ctx, step)
    return Outcome(True, f"{unit} enabled and started; {outcome.detail}")
