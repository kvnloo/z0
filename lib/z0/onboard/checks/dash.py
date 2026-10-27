"""dash acceptance (design §8.3, work package Z4).

- `bridge`: with a tailnet, the installed unit answers 401 on the tailnet IPv4 (step
  dash.health); without one, the loopback self-test passed (dash.selftest.loopback) and
  the report carries the `tailscale up` ask;
- `credentials`: when the bridge ran as a unit, `~/.dash` is 0700 and its token files are
  0600 (the bridge creates them; z0 never reads their values here).
"""
from __future__ import annotations

import os
import stat


def _entry(name, status, detail, required=True, warnings=None):
    out = {"component": "dash", "name": name, "status": status, "detail": detail, "required": required}
    if warnings:
        out["warnings"] = warnings
    return out


def evaluate(view) -> list:
    if "dash" not in (view.plan.get("targets") or []):
        return []
    summary = (view.plan.get("components") or {}).get("dash") or {}
    if summary.get("verdict") not in (None, "allow"):
        return [_entry("bridge", "unavailable", f"dash is {summary.get('verdict')} ({summary.get('reason', '')})",
                       required=False)]
    tailnet = bool((view.ctx.host.get("tailscale") or {}).get("ipv4"))
    out = []
    if tailnet and "dash.health" in view.steps:
        status = view.check_status("dash.health")
        out.append(_entry("bridge", status, "tailnet: " + view.results.get("dash.health", {}).get("reason", ""),
                          required=status != "unavailable"))
    elif "dash.selftest.loopback" in view.steps:
        status = view.check_status("dash.selftest.loopback")
        out.append(_entry("bridge", status, "no tailnet: " +
                          view.results.get("dash.selftest.loopback", {}).get("reason", ""),
                          required=status != "unavailable",
                          warnings=["dash: join a tailnet (`tailscale up`), then run "
                                    "`./z0 onboard --auto --accept services` to install the bridge unit"]))
    else:
        out.append(_entry("bridge", "skipped", "no bridge step planned", required=False))

    creds = view.ctx.expand("~/.dash")
    if tailnet and os.path.isdir(creds):
        bad = []
        if stat.S_IMODE(os.stat(creds).st_mode) & 0o077:
            bad.append("~/.dash is not 0700")
        for name in os.listdir(creds):
            path = os.path.join(creds, name)
            if os.path.isfile(path) and stat.S_IMODE(os.stat(path).st_mode) & 0o077:
                bad.append(f"~/.dash/{name} is not 0600")
        out.append(_entry("credentials", "failed" if bad else "passed", "; ".join(bad) or "modes ok"))
    return out
