"""Toolchains, the python window, and the prepared PATH (§4, law T1).

Prepared PATH = resolved toolchain bin dirs, then $Z0_HOME/toolchains/*/bin, then
(at apply time) the component venv bin, then the system dirs. Allowed harness bin dirs
are added by harnesses.py; bin dirs of `configure: never` harnesses never are.
Every tool's `sh_resolves` is then checked with `sh -c 'command -v X'` under exactly
that PATH, so what detect reports is what every `run`, unit and check will see.
"""
from __future__ import annotations

import os

from ..util import version_tuple

WINDOW = ((3, 10), (3, 14))


def _dirs(ctx, patterns) -> list:
    found = []
    for pattern in patterns or []:
        for path in ctx.glob(pattern):
            if os.path.isdir(path) and path not in found:
                found.append(path)
    return found


def candidate_dirs(ctx) -> dict:
    detect = (ctx.registry.get("toolchains") or {}).get("detect") or {}
    return {
        "z0_toolchain": _dirs(ctx, detect.get("z0_dirs")),
        "well_known_dir": _dirs(ctx, detect.get("well_known_dirs")),
        "version_manager": _dirs(ctx, detect.get("shims")),
        "path": [d for d in ctx.user_path() if os.path.isdir(d)],
        "system": [d for d in ctx.system_dirs if os.path.isdir(d)],
    }


def _find(ctx, names, dirs_by_source) -> tuple:
    for source in ("z0_toolchain", "well_known_dir", "version_manager", "path", "system"):
        for name in names:
            path = ctx.which(name, dirs_by_source[source])
            if path:
                return path, "path" if source == "system" else source
    return None, None


def _version(ctx, path: str, cmd) -> str:
    if not cmd:
        return ""
    result = ctx.run([path, *cmd[1:]], timeout=5)
    parsed = version_tuple(result.out + " " + result.err) if result.rc is not None else None
    return ".".join(str(part) for part in parsed) if parsed else ""


def _in_window(version: str) -> bool:
    parsed = version_tuple(version)
    return parsed is not None and WINDOW[0] <= parsed[:2] < WINDOW[1]


def detect(ctx) -> tuple:
    """Returns (toolchains, python_window). Fills ctx.prepared_path (without harness dirs)."""
    tools = (ctx.registry.get("toolchains") or {}).get("tools") or {}
    dirs = candidate_dirs(ctx)
    result: dict = {}
    resolved_dirs: list = []
    for tool, spec in tools.items():
        path, source = _find(ctx, spec.get("binaries") or [tool], dirs)
        if not path:
            result[tool] = {"state": "absent"}
            continue
        entry = {"state": "present", "path": ctx.tilde(path), "source": source}
        version = _version(ctx, path, spec.get("version_cmd"))
        if version:
            entry["version"] = version
        result[tool] = entry
        directory = os.path.dirname(path)
        if directory not in resolved_dirs and directory not in dirs["system"]:
            resolved_dirs.append(directory)

    window = "impossible"
    py = tools.get("python3") or {}
    front = []
    if _in_window(result.get("python3", {}).get("version", "")):
        window = "present"
    else:
        # The stranger case (§1.1, §1.3): python3 is absent or outside the window, and
        # stage 0 made one (the z0 venv, from the bootstrap CPython). That interpreter
        # becomes `python3` and its dir leads the prepared PATH, so every step that runs
        # `python3` gets it (T1), not a missing or too-old one.
        bootstrap = _dirs(ctx, ["$Z0_HOME/bootstrap/python/*/bin"])
        for directory in _dirs(ctx, ["$Z0_HOME/venv/bin"]) + bootstrap:
            path = ctx.which("python3", [directory])
            version = _version(ctx, path, ["python3", "--version"]) if path else ""
            if path and _in_window(version):
                result["python3"] = {"state": "present", "path": ctx.tilde(path),
                                     "version": version, "source": "z0_bootstrap"}
                front = [directory]
                window = "present"
                break
        search = bootstrap + dirs["well_known_dir"] + dirs["version_manager"] + dirs["path"] + dirs["system"]
        names = (py.get("window_binaries") or []) if window != "present" else []
        for name in names:
            path = ctx.which(name, search)
            if path and _in_window(_version(ctx, path, [name, "--version"])):
                window = "present"  # z0int's own venv can use it; `python3` stays as found
                break
    if window != "present" and (result.get("uv", {}).get("state") == "present"
                                or result.get("curl", {}).get("state") == "present"):
        window = "makeable"

    resolved_dirs = [d for d in resolved_dirs if d not in front]
    z0_bins = [d for d in dirs["z0_toolchain"] if d not in resolved_dirs and d not in front]
    ctx.prepared_path = front + resolved_dirs + z0_bins + [d for d in dirs["system"]]
    return result, window


def finalize(ctx, toolchains: dict) -> None:
    """T1: record whether each present tool resolves under `sh -c` with the prepared PATH."""
    tools = (ctx.registry.get("toolchains") or {}).get("tools") or {}
    names = [(tool, (tools.get(tool) or {}).get("binaries", [tool])[0])
             for tool, entry in toolchains.items() if entry.get("state") == "present"]
    if not names:
        return
    script = 'for t; do command -v "$t" >/dev/null 2>&1 && echo "+$t" || echo "-$t"; done'
    out = ctx.run(["sh", "-c", script, "sh", *[binary for _, binary in names]],
                  path_dirs=ctx.prepared_path).out
    ok = {line[1:] for line in out.splitlines() if line.startswith("+")}
    for tool, binary in names:
        toolchains[tool]["sh_resolves"] = binary in ok


def prepared_path(ctx) -> list:
    return [ctx.tilde(d) for d in ctx.prepared_path]
