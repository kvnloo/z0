"""Placeholder expansion for registry steps, shared by detect and plan (pure).

Registry steps are host-independent text with `{placeholders}`. The plan expands them
from facts, so detect (which stats probe paths for `workspace.owned`) and plan (which
compares against them) see the same strings. Paths stay in `~/...` or `$Z0_HOME/...`
form: no absolute home path is ever produced here (law H2).

Placeholders:
  {id} {name} {repo} {pin} {pin8} {rev_app} {rev_bridge} {tree} {profile}
  {torch_version}, and the argv-only list placeholder "{torch_index_args}".
"""
from __future__ import annotations

import copy
import re
from typing import Any, Optional

from . import kernel as k
from .util import version_ge

PLACEHOLDER = re.compile(r"\{([a-z_0-9]+)\}")
LIST_PLACEHOLDERS = ("{torch_index_args}",)
SCALARS = ("id", "name", "repo", "pin", "pin8", "rev_app", "rev_bridge", "tree", "profile",
           "torch_version")


def select_tree(comp: dict, host: dict) -> dict:
    """The component's z0 work tree: a clean adopted checkout used in place, else the
    z0-owned clone (§2.5 adopt_or_clone). Never a dirty or off-origin tree."""
    repo = str(comp.get("repo") or "")
    name = repo.split("/", 1)[-1]
    matches = [c for c in host.get("checkouts") or []
               if str(c.get("origin", "")).lower() == repo.lower()]
    clean = [c for c in matches if c.get("dirty", 1) == 0]
    if clean:
        best = sorted(clean, key=lambda c: (c["path"].rstrip("/").rsplit("/", 1)[-1] != name,
                                            len(c["path"]), c["path"]))[0]
        return {"tree": best["path"], "adopted": True, "dirty_candidates": len(matches) - len(clean)}
    return {"tree": f"$Z0_HOME/repos/{name}", "adopted": False,
            "dirty_candidates": len(matches)}


def torch_index_args(host: dict, onboarding: dict) -> list:
    torch = (onboarding.get("hardware") or {}).get("torch") or {}
    gpu = (host.get("hardware") or {}).get("gpu") or {}
    hw = hw_class(host)
    cuda_ok = version_ge(gpu.get("cuda_max"), torch.get("min_cuda", "12.8"))
    index = k.decide_torch_index(hw, cuda_ok, bool(gpu.get("rocm")), z0_disk_gib(host) < 10)
    if index is k.TorchIndex.CPU:
        return ["--index-url", torch.get("cpu_index", "")]
    if index is k.TorchIndex.ROCM:
        return ["--index-url", torch.get("rocm_index", "")]
    return []


def hw_class(host: dict) -> "k.HwClass":
    raw = (((host.get("hardware") or {}).get("gpu") or {}).get("class")) or "cpu"
    return k.HwClass[raw.upper()] if raw.upper() in k.HwClass.__members__ else k.HwClass.CPU


def z0_disk_gib(host: dict) -> float:
    disks = (host.get("hardware") or {}).get("disks") or []
    for disk in disks:
        if "z0_home" in (disk.get("role") or []):
            return float(disk.get("free_gib", 0))
    return float(disks[0].get("free_gib", 0)) if disks else 0.0


def component_context(cid: str, comp: dict, host: dict, onboarding: dict,
                      profile: Optional[str] = None) -> dict:
    install = comp.get("install") or {}
    revs = (comp.get("onboard") or {}).get("revs") or {}
    pin = str(install.get("ref") or "")
    repo = str(comp.get("repo") or "")
    torch = (onboarding.get("hardware") or {}).get("torch") or {}
    ctx = {
        "id": cid, "name": repo.split("/", 1)[-1], "repo": repo, "pin": pin, "pin8": pin[:8],
        "rev_app": str(revs.get("app") or pin), "rev_bridge": str(revs.get("bridge") or pin),
        "tree": select_tree(comp, host)["tree"], "profile": profile or "",
        "torch_version": str(torch.get("version") or ""),
        "torch_index_args": torch_index_args(host, onboarding),
    }
    return ctx


def _sub(text: str, ctx: dict) -> str:
    return PLACEHOLDER.sub(lambda m: str(ctx[m.group(1)]) if m.group(1) in ctx
                           and m.group(1) in SCALARS else m.group(0), text)


def _walk(node: Any, ctx: dict, in_argv: bool = False) -> Any:
    if isinstance(node, str):
        return _sub(node, ctx)
    if isinstance(node, list):
        out = []
        for item in node:
            if in_argv and item in LIST_PLACEHOLDERS:
                out.extend(ctx.get(item.strip("{}"), []))
            else:
                out.append(_walk(item, ctx, in_argv))
        return out
    if isinstance(node, dict):
        return {key: _walk(value, ctx, in_argv=key == "argv") for key, value in node.items()}
    return node


def expand_step(step: dict, ctx: dict) -> dict:
    """A deep copy of `step` with placeholders filled from `ctx`."""
    return _walk(copy.deepcopy(step), ctx)


def leftover_placeholders(node: Any) -> list:
    """Placeholders that survived expansion (registry-check flags them)."""
    found: list = []
    if isinstance(node, str):
        found.extend(PLACEHOLDER.findall(node))
    elif isinstance(node, list):
        for item in node:
            found.extend(leftover_placeholders(item))
    elif isinstance(node, dict):
        for value in node.values():
            found.extend(leftover_placeholders(value))
    return found


def step_paths(step: dict) -> list:
    """Every path a step declares it creates or probes (for workspace.owned)."""
    paths = list(step.get("creates") or [])
    probe = step.get("probe") or {}
    if probe.get("exists"):
        paths.append(probe["exists"])
    return paths
