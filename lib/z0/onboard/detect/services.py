"""Existing units and port owners (§4, laws S1 and S3).

Read-only: `systemctl --user list-units/show`, `ss -ltnp` (Linux); `launchctl list`,
`lsof` (macOS). Only unit names, the exec-root kind and a deployed SHA are kept;
command lines with arguments and environment files are never recorded.
"""
from __future__ import annotations

import fnmatch
import os
import re

PATTERNS = ("dash-*", "z0*")
_SHA = re.compile(r"(?<![0-9a-f])([0-9a-f]{40}|[0-9a-f]{7,12})(?![0-9a-f])")


def root_kind(ctx, path: str) -> str:
    """Classify where live code runs from (kernel.RootKind, snake_case)."""
    if not path or not os.path.isabs(path):
        return "other"
    z0 = ctx.z0_home.rstrip("/")
    if path.startswith(z0 + "/build/"):
        return "build_tree"
    probe = path
    while probe and probe != "/":
        if os.path.exists(os.path.join(probe, ".git")):
            return "checkout"
        probe = os.path.dirname(probe)
    if path.startswith(z0 + "/toolchains/"):
        return "toolchain"
    if path.startswith(z0 + "/venvs/") or "/z0int-runtime/" in path:
        return "owned_venv"
    form = ctx.tilde(path)
    if form.startswith("~/.local/lib/") or form.startswith("~/.local/share/"):
        return "release"
    return "other"


def _show(ctx, unit: str) -> dict:
    out = ctx.run(["systemctl", "--user", "show", "-p", "ExecStart", "-p", "WorkingDirectory",
                   "-p", "ActiveState", unit]).out
    props = {}
    for line in out.splitlines():
        key, _, value = line.partition("=")
        props[key] = value
    exec_path = ""
    match = re.search(r"path=([^ ;]+)", props.get("ExecStart", ""))
    if match:
        exec_path = match.group(1)
    workdir = props.get("WorkingDirectory", "")
    kinds = [root_kind(ctx, p) for p in (workdir, exec_path) if p and p != "!"]
    order = ["checkout", "build_tree", "other", "release", "owned_venv", "toolchain"]
    kind = min(kinds, key=order.index) if kinds else "other"
    entry = {"active": props.get("ActiveState") == "active", "exec_root_kind": kind}
    resolved = os.path.realpath(workdir) if workdir else ""
    sha = _SHA.findall(resolved)
    if sha:
        entry["deployed_sha"] = sha[-1]
    return entry


def _linux(ctx, ports) -> dict:
    units = []
    listing = ctx.run(["systemctl", "--user", "list-units", "--all", "--no-legend", "--plain",
                       "--type=service"])
    for line in listing.out.splitlines():
        name = line.split()[0] if line.split() else ""
        base = name[:-len(".service")] if name.endswith(".service") else name
        if any(fnmatch.fnmatch(base, pat) for pat in PATTERNS):
            units.append({"name": name, "manager": "systemd_user", **_show(ctx, name)})
    owners = {}
    ss = ctx.run(["ss", "-ltnpH"])
    for line in ss.out.splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        port = cols[3].rsplit(":", 1)[-1]
        if port.isdigit() and int(port) in ports:
            proc = re.search(r'users:\(\("([^"]+)"', line)
            owners[port] = proc.group(1) if proc else "unknown"
    return {"units": units, "port_owners": owners}


def _darwin(ctx, ports) -> dict:
    units = []
    for line in ctx.run(["launchctl", "list"]).out.splitlines():
        cols = line.split()
        label = cols[-1] if cols else ""
        if label.startswith("com.z0.") or "dash" in label:
            units.append({"name": label, "manager": "launchd",
                          "active": bool(cols and cols[0] not in ("-", "0") and cols[0].isdigit()),
                          "exec_root_kind": "other"})
    owners = {}
    for line in ctx.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"]).out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 9:
            port = cols[8].rsplit(":", 1)[-1]
            if port.isdigit() and int(port) in ports:
                owners[port] = cols[0]
    return {"units": units, "port_owners": owners}


def detect(ctx, os_name: str) -> dict:
    ports = set((ctx.registry.get("onboarding") or {}).get("reserved_ports") or [])
    result = _darwin(ctx, ports) if os_name == "darwin" else _linux(ctx, ports)
    result["units"].sort(key=lambda u: u["name"])
    result["port_owners"] = dict(sorted(result["port_owners"].items()))
    return result
