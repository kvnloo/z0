"""DETECT (design §4): read-only, stdlib only, never raises. Produces host.json.

Each detector runs inside a guard: an exception becomes a warning and an empty result,
never a crash. `$HOME` is written as `~` throughout; no secret value is ever read.
"""
from __future__ import annotations

import datetime as _dt

from . import (checkouts, hardware, harnesses, network, osinfo, secrets, services, session,
               tailscale, toolchains, unknown_bins, workspace)
from .base import Ctx

__all__ = ["Ctx", "detect"]


def _guard(ctx: Ctx, name: str, fn, default):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - detectors never raise (§4)
        ctx.warn(f"detector {name} failed: {type(exc).__name__}")
        return default


def detect(ctx: Ctx) -> dict:
    base = _guard(ctx, "osinfo", lambda: osinfo.detect(ctx),
                  {"host_id": osinfo.host_id("", ctx.hostname or ""),
                   "os": {"os": "linux", "arch": "x86_64"}})
    os_name, arch = base["os"]["os"], base["os"]["arch"]
    host: dict = {"version": 1, "host_id": base["host_id"],
                  "detected_at": ctx.now or _dt.datetime.now(_dt.timezone.utc)
                  .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                  "os": base["os"]}
    host["hardware"] = _guard(ctx, "hardware", lambda: hardware.detect(ctx, os_name, arch),
                              {"cpu": {"logical": 1, "physical": 1}, "ram_gib": 0,
                               "gpu": {"class": "cpu"}})
    host["session"] = _guard(ctx, "session", lambda: session.detect(ctx, os_name), {})
    tools, window = _guard(ctx, "toolchains", lambda: toolchains.detect(ctx), ({}, "impossible"))
    host["python_window"] = window
    dirs = _guard(ctx, "toolchains.dirs", lambda: toolchains.candidate_dirs(ctx),
                  {"z0_toolchain": [], "well_known_dir": [], "version_manager": [], "path": [],
                   "system": []})
    host["harnesses"] = _guard(ctx, "harnesses", lambda: harnesses.detect(ctx, dirs), {})
    _guard(ctx, "toolchains.finalize", lambda: toolchains.finalize(ctx, tools), None)
    host["toolchains"] = tools
    host["prepared_path"] = toolchains.prepared_path(ctx)
    host["network"] = _guard(ctx, "network", lambda: network.detect(ctx), {})
    host["tailscale"] = _guard(ctx, "tailscale", lambda: tailscale.detect(ctx), {})
    found, revs = _guard(ctx, "checkouts", lambda: checkouts.detect(ctx), ([], {}))
    host["checkouts"], host["revs"] = found, revs
    host["services"] = _guard(ctx, "services", lambda: services.detect(ctx, os_name),
                              {"units": [], "port_owners": {}})
    host["secrets"] = _guard(ctx, "secrets", lambda: secrets.detect(ctx), {})
    _guard(ctx, "unknown_bins", lambda: unknown_bins.detect(ctx), None)
    host["workspace"] = _guard(ctx, "workspace", lambda: workspace.detect(ctx, host),
                               {"host_match": "fresh"})
    host["unknowns"] = sorted(ctx.unknowns, key=lambda u: u["id"])
    host["warnings"] = sorted(ctx.warnings)
    return host
