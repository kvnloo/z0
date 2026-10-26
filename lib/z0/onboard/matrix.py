"""generated/onboarding-matrix.md: what `./z0 onboard` plans per component (pure)."""
from __future__ import annotations

from . import regsnap
from .regcheck import auto_target_set, projection


def onboarding_matrix(snap: dict) -> str:
    comps = regsnap.components(snap)
    auto = set(auto_target_set(snap))
    lines = [
        "# Onboarding matrix",
        "",
        "| Component | Gate | Auto target | Tools | Steps | C1 bundles | C2 / asks | Services |",
        "|-----------|------|-------------|-------|-------|------------|-----------|----------|",
    ]
    for cid in sorted(comps):
        block = comps[cid].get("onboard") or {}
        steps = block.get("steps") or []
        tools = ", ".join(((block.get("requires") or {}).get("tools")) or []) or "-"
        bundles = sorted({(s.get("consent") or {}).get("bundle") for s in steps
                          if (s.get("consent") or {}).get("class") == "C1"} - {None})
        asks = sum(1 for s in steps if s.get("kind") == "ask"
                   or (s.get("consent") or {}).get("class") == "C2")
        services = ", ".join(f"{(s.get('service') or {}).get('unit', s['id'])} "
                             f"({(s.get('service') or {}).get('bind')}:{(s.get('service') or {}).get('port')})"
                             for s in steps if s.get("kind") == "service_unit") or "-"
        lines.append(f"| `{cid}` | {block.get('gate', 'generic')} | {'yes' if cid in auto else ''} "
                     f"| {tools} | {len(steps)} | {', '.join(bundles) or '-'} | {asks or '-'} "
                     f"| {services} |")
    lines += ["", "## Legacy projection (R-sync)", "",
              "`install.command` / `verify.command` are the shell projection of the steps marked "
              "`legacy_projection: true`; `scripts/registry-check` fails when they drift.", ""]
    for cid in sorted(comps):
        steps = (comps[cid].get("onboard") or {}).get("steps") or []
        install, verify = projection(steps, False), projection(steps, True)
        if install or verify:
            lines.append(f"- `{cid}`: install `{install or '-'}`; verify `{verify or '-'}`")
    lines += ["", "_Generated from `registry/components.yaml` `onboard:` blocks. Do not edit by hand._", ""]
    return "\n".join(lines)
