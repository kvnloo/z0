"""Hub acceptance (design §8.1): the z0 checkout itself.

- `scripts/registry-check` passes (hub step z0.registry_check);
- the plan is deterministic (`plan --stdout --check-deterministic`, z0.plan_deterministic);
- `./z0 init --profile P --dry-run` lists exactly the profile's components (the profile
  only; supplementals such as dash and z0evals are excluded), z0.init_dry_run;
- memento is never planned (law M1).
"""
from __future__ import annotations

import re

HUB = (("registry_check", "z0.registry_check"), ("plan_deterministic", "z0.plan_deterministic"))
_LISTED = re.compile(r"^  ([a-z0-9][a-z0-9_-]*)\s*$", re.M)


def _entry(name, status, detail, required=True):
    return {"component": "z0", "name": name, "status": status, "detail": detail, "required": required}


def _from_step(view, name, sid):
    if sid not in view.steps:
        return _entry(name, "skipped", f"{sid} is not in this plan", required=False)
    status = view.check_status(sid)
    return _entry(name, status, view.results.get(sid, {}).get("reason", ""))


def _profile_members(view) -> list:
    from .. import regsnap
    profile = view.plan.get("profile")
    try:
        return regsnap.resolve_profile(view.snap, profile) if profile else []
    except KeyError:
        return []


def evaluate(view) -> list:
    out = [_from_step(view, name, sid) for name, sid in HUB]
    init = _from_step(view, "init_dry_run", "z0.init_dry_run")
    if init["status"] == "passed":
        output = view.results.get("z0.init_dry_run", {}).get("output")
        if output is not None:
            listed = set(_LISTED.findall(output))
            want = set(_profile_members(view))
            if listed != want:
                init = _entry("init_dry_run", "failed",
                              f"listed {sorted(listed)}, the profile has {sorted(want)}")
            else:
                init["detail"] = f"lists the {len(want)} profile component(s)"
    out.append(init)
    planned = set(view.plan.get("targets") or []) | {e["step"].get("component") for e in view.plan["steps"]}
    out.append(_entry("memento_never_planned", "failed" if "memento" in planned else "passed",
                      "law M1"))
    return out
