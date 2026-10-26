"""OS, arch, libc, distro, package manager, PEP 668 marker and host_id (§4)."""
from __future__ import annotations

import hashlib
import os
import re

PKG_MANAGERS = (("pacman", "pacman"), ("apt-get", "apt"), ("dnf", "dnf"), ("apk", "apk"),
                ("brew", "brew"))


def _os_arch(ctx) -> tuple:
    sysname, machine = ctx.uname
    os_name = {"Linux": "linux", "Darwin": "darwin"}.get(sysname, sysname.lower())
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64",
            "arm64": "arm64"}.get(machine, machine)
    return os_name, arch


def _libc(ctx, os_name: str) -> str:
    if os_name == "darwin":
        return "darwin"
    result = ctx.run(["ldd", "--version"])
    text = (result.out + result.err).lower()
    if "musl" in text or ctx.glob(ctx.sys("/lib/ld-musl-*")):
        return "musl"
    if "glibc" in text or "gnu libc" in text or "gnu c library" in text:
        return "glibc"
    return "unknown"


def _distro(ctx, os_name: str) -> str:
    if os_name == "darwin":
        result = ctx.run(["sw_vers", "-productVersion"])
        return f"macos-{result.out.strip()}" if result.ok and result.out.strip() else "macos"
    text = ctx.read_text(ctx.sys("/etc/os-release")) or ""
    match = re.search(r'^ID="?([A-Za-z0-9._-]+)"?', text, re.M)
    return match.group(1) if match else "unknown"


def _pep668(ctx) -> bool:
    result = ctx.run(["python3", "-c", "import sysconfig;print(sysconfig.get_path('stdlib'))"])
    stdlib = result.out.strip()
    return bool(result.ok and stdlib and os.path.exists(os.path.join(stdlib, "EXTERNALLY-MANAGED")))


def _machine_id(ctx, os_name: str) -> str:
    if os_name == "darwin":
        result = ctx.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.out)
        return match.group(1) if match else ""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        text = (ctx.read_text(ctx.sys(path), 256) or "").strip()
        if text:
            return text
    return ""


def host_id(machine_id: str, hostname: str) -> str:
    """sha256(machine-id || hostname)[:16]; neither raw value leaves detect."""
    return hashlib.sha256(f"{machine_id}{hostname}".encode()).hexdigest()[:16]


def detect(ctx) -> dict:
    os_name, arch = _os_arch(ctx)
    pkg = "none"
    for binary, name in PKG_MANAGERS:
        if ctx.which(binary):
            pkg = name
            break
    return {
        "host_id": host_id(_machine_id(ctx, os_name), ctx.hostname or ""),
        "os": {"os": os_name, "arch": arch, "libc": _libc(ctx, os_name),
               "distro": _distro(ctx, os_name), "pkg_manager": pkg, "pep668": _pep668(ctx)},
    }
