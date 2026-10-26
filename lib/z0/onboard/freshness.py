"""Freshness check before APPLY (design §6.3 step 2). Pure.

APPLY re-detects the volatile facts (ports, tailnet IP, toolchain versions, unit
states, checkout HEADs, disk tier) and compares them with the host.json the plan was
made from. There is no wall-clock expiry. On drift the plan is made again with the
same grants; the kernel (decide_replan) says whether to continue and show the diff,
or stop and confirm again. `--yes` cannot widen a grant.
"""
from __future__ import annotations

from typing import Optional

from . import kernel as k
from .expand import z0_disk_gib


def volatile(host: dict) -> dict:
    """The facts that may change between plan and apply."""
    services = host.get("services") or {}
    tools = {name: (entry.get("state"), entry.get("version"), entry.get("path"))
             for name, entry in sorted((host.get("toolchains") or {}).items())}
    units = sorted((u.get("name"), u.get("active"), u.get("deployed_sha"))
                   for u in services.get("units") or [])
    checkouts = sorted((c.get("path"), c.get("head"), c.get("dirty"))
                       for c in host.get("checkouts") or [])
    return {
        "ports": sorted((str(port), str(owner)) for port, owner
                        in (services.get("port_owners") or {}).items()),
        "tailnet_ipv4": (host.get("tailscale") or {}).get("ipv4"),
        "toolchains": tools,
        "python_window": host.get("python_window"),
        "units": units,
        "checkouts": checkouts,
        "disk_tier": k.disk_tier(z0_disk_gib(host)).name,
        "host_id": host.get("host_id"),
    }


def drift(old: dict, new: dict) -> list:
    """Names of the volatile facts that changed (empty: the plan is still fresh)."""
    a, b = volatile(old), volatile(new)
    return [key for key in a if a[key] != b[key]]


def _todo(plan_obj: dict) -> dict:
    return {e["step"]["id"]: e["step"] for e in plan_obj["steps"] if e["state"]["status"] == "todo"}


def widens(old_plan: dict, new_plan: dict) -> bool:
    """A re-plan widens consent when it would run a C1 or C2 step that the confirmed
    plan did not list as todo (the person never saw it)."""
    before, after = _todo(old_plan), _todo(new_plan)
    return any(sid not in before and step["consent"]["class"] != "C0"
               for sid, step in after.items())


def diff_lines(old_plan: dict, new_plan: dict) -> list:
    before = {e["step"]["id"]: e["state"]["status"] for e in old_plan["steps"]}
    after = {e["step"]["id"]: e["state"]["status"] for e in new_plan["steps"]}
    lines = []
    for sid in sorted(set(before) | set(after)):
        if before.get(sid) != after.get(sid):
            lines.append(f"{sid}: {before.get(sid, '-')} -> {after.get(sid, '-')}")
    return lines


def decide(old_host: dict, new_host: dict, old_plan: dict, new_plan: Optional[dict],
           yes: bool) -> k.Replan:
    """The kernel's verdict for this freshness check."""
    changed = bool(drift(old_host, new_host))
    wide = bool(new_plan is not None and widens(old_plan, new_plan))
    return k.decide_replan(changed, wide, yes)
