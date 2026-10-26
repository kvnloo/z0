"""Prior z0 state (§4): recorded host_id (law H1), deploy stamps, and which of the
paths the registry steps create or probe already exist (`owned`, used for
already_satisfied and law I1). stat only; workspace.yaml is scanned for one key."""
from __future__ import annotations

import glob
import os
import re

from .. import kernel as k
from ..expand import component_context, expand_step, step_paths

_HOST_ID = re.compile(r"^host_id:\s*['\"]?([0-9a-f]{16})['\"]?\s*$", re.M)


def recorded_host_id(ctx):
    text = ctx.read_text(os.path.join(ctx.z0_home, "workspace.yaml")) or ""
    match = _HOST_ID.search(text)
    return match.group(1) if match else None


def owned_paths(ctx, host: dict) -> list:
    comps = (ctx.registry.get("components") or {}).get("components") or {}
    onboarding = ctx.registry.get("onboarding") or {}
    found = set()
    for cid, comp in comps.items():
        context = component_context(cid, comp, host, onboarding)
        for step in (comp.get("onboard") or {}).get("steps") or []:
            for path in step_paths(expand_step(step, context)):
                if "{" in path:
                    continue
                if ctx.lexists(ctx.expand(path)):
                    found.add(path)
    for tool, spec in ((ctx.registry.get("toolchains") or {}).get("tools") or {}).items():
        version = (spec.get("install") or {}).get("version")
        if version and ctx.lexists(ctx.expand(f"$Z0_HOME/toolchains/{tool}/{version}")):
            found.add(f"$Z0_HOME/toolchains/{tool}/{version}")
    return sorted(found)


def detect(ctx, host: dict) -> dict:
    recorded = recorded_host_id(ctx)
    out: dict = {"host_match": k.host_match(recorded, host.get("host_id")).name.lower()}
    if recorded:
        out["recorded_host_id"] = recorded
    stamps = []
    for pattern in ("~/.local/share/dash/**/deployed.json", "~/.local/share/z0/**/deployed.json"):
        stamps.extend(ctx.tilde(p) for p in glob.glob(ctx.expand(pattern), recursive=True))
    out["stamps"] = sorted(stamps)[:50]
    out["owned"] = owned_paths(ctx, host)
    return out
