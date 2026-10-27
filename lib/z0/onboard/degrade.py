"""Degraded runs: a failure off the first-task path does not end onboarding.

`registry/onboarding.yaml` names the first-task path (`first_task_path`): the
components a contributor needs to reach a first task (z0intelligence, z0evals). A failed
step or required check is *critical* when it belongs to one of them, to the z0 hub, or
to no component, or when it is a toolchain that a critical component needs. Blocked
steps never decide the code by themselves: a degradable failure cannot block a critical
step (no critical component depends on, or needs a tool of, a degradable one), so a
blocked critical step always comes with a critical failure, and plan-time blocks (a
tier waiting on a consent ask) were never failures. Any other failure is *degradable*: the run
finishes, the report lists it under "Failed", and VERIFY exits DEGRADED_EXIT (5) instead
of 1, so an agent goes on to the first task.

Without `first_task_path` every failure is critical (exit 1): the earlier behaviour.
"""
from __future__ import annotations

from . import regsnap

DEGRADED_EXIT = 5


def first_task_path(snap: dict) -> set:
    return set(regsnap.onboarding(snap).get("first_task_path") or [])


def classify(plan_obj: dict, results: dict, failed_checks: list, snap: dict,
             tool_users: dict) -> tuple:
    """(critical failures, degraded component ids).

    `results`: step id -> {"status": ...}; `failed_checks`: required check items
    ({"component", "name"}) that failed; `tool_users`: toolchain step id -> the
    components that need that tool."""
    crit = first_task_path(snap)
    comp_of = {e["step"]["id"]: e["step"].get("component") for e in plan_obj["steps"]}
    critical, degraded = [], set()

    def degradable_owner(sid: str, cid):
        """The component (or toolchain) a failure degrades, or None when critical."""
        if not crit:
            return None
        if cid and cid != "z0":
            return None if cid in crit else cid
        users = tool_users.get(sid)
        if users and not (users & crit):
            return sid
        return None

    for sid, result in results.items():
        status, cid = result.get("status"), comp_of.get(sid)
        if status == "failed":
            owner = degradable_owner(sid, cid)
            if owner is None:
                critical.append(sid)
            else:
                degraded.add(owner)
    for item in failed_checks:
        cid = item["component"]
        name = f"{cid}.{item['name']}"
        if cid == "z0" or not crit or cid in crit:
            critical.append(name)
        else:
            degraded.add(cid)
    return critical, sorted(degraded)


__all__ = ["DEGRADED_EXIT", "classify", "first_task_path"]
