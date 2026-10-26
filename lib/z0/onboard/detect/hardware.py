"""CPU, RAM, disks and GPU class (§4, §5.1). GPU vendor ambiguity becomes an unknown."""
from __future__ import annotations

import os
import re

DRM_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


def _gib(n_bytes: float) -> float:
    return round(n_bytes / 1024 ** 3, 1)


def _cpu(ctx, os_name: str) -> dict:
    logical = physical = 0
    if os_name == "darwin":
        logical = _int(ctx.run(["sysctl", "-n", "hw.ncpu"]).out)
        physical = _int(ctx.run(["sysctl", "-n", "hw.physicalcpu"]).out)
    else:
        logical = _int(ctx.run(["nproc"]).out)
        lscpu = ctx.run(["lscpu", "-p=core"])
        if lscpu.ok:
            cores = {line.strip() for line in lscpu.out.splitlines()
                     if line.strip() and not line.startswith("#")}
            physical = len(cores)
    logical = logical or os.cpu_count() or 1
    return {"logical": logical, "physical": physical or logical}


def _int(text: str) -> int:
    match = re.search(r"\d+", text or "")
    return int(match.group(0)) if match else 0


def _ram(ctx, os_name: str) -> float:
    if os_name == "darwin":
        return _gib(_int(ctx.run(["sysctl", "-n", "hw.memsize"]).out))
    text = ctx.read_text(ctx.sys("/proc/meminfo")) or ""
    match = re.search(r"^MemTotal:\s+(\d+)\s*kB", text, re.M)
    return _gib(int(match.group(1)) * 1024) if match else 0.0


def _free_gib(path: str) -> tuple:
    probe = path
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        st = os.statvfs(probe or "/")
    except OSError:
        return 0.0, 0.0
    return _gib(st.f_bavail * st.f_frsize), _gib(st.f_blocks * st.f_frsize)


def _disks(ctx) -> list:
    roles = {"z0_home": ctx.z0_home, "home": ctx.home}
    if ctx.env.get("HF_HOME"):
        roles["hf_home"] = ctx.env["HF_HOME"]
    disks: dict = {}
    for role, path in roles.items():
        try:
            dev = os.stat(_existing(path)).st_dev
        except OSError:
            continue
        free, total = _free_gib(path)
        entry = disks.setdefault(dev, {"mount": ctx.tilde(_existing(path)), "role": [],
                                       "free_gib": free, "total_gib": total})
        entry["role"].append(role)
    return list(disks.values())


def _existing(path: str) -> str:
    while path and not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path or "/"


def _gpu(ctx, os_name: str, arch: str) -> dict:
    if os_name == "darwin":
        return {"class": "apple" if arch == "arm64" else "intel_mac"}
    smi = ctx.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                   "--format=csv,noheader"])
    if smi.ok and smi.out.strip():
        first = [part.strip() for part in smi.out.splitlines()[0].split(",")]
        gpu = {"class": "nvidia"}
        if len(first) >= 2:
            gpu["driver"] = first[1]
        if len(first) >= 3:
            mib = _int(first[2])
            gpu["vram_gib"] = round(mib / 1024, 1)
        header = ctx.run(["nvidia-smi"])
        match = re.search(r"CUDA Version:\s*(\d+\.\d+)", header.out)
        if match:
            gpu["cuda_max"] = match.group(1)
        return gpu
    vendors = set()
    for path in ctx.glob(ctx.sys("/sys/class/drm/*/device/vendor")):
        vendors.add(DRM_VENDORS.get((ctx.read_text(path, 64) or "").strip(), "other"))
    if "amd" in vendors:
        rocm = ctx.run(["rocm-smi", "--showproductname"]).ok
        return {"class": "amd", "rocm": rocm}
    if "nvidia" in vendors or os.path.exists(ctx.sys("/proc/driver/nvidia/version")):
        ctx.unknown({"id": "gpu.vendor", "kind": "gpu_vendor_resolve",
                     "facts": {"drm_vendors": sorted(vendors), "nvidia_smi": False},
                     "candidates": ["nvidia", "cpu"], "safe_default": "cpu"})
    return {"class": "cpu"}


def detect(ctx, os_name: str, arch: str) -> dict:
    return {"cpu": _cpu(ctx, os_name), "ram_gib": _ram(ctx, os_name), "disks": _disks(ctx),
            "gpu": _gpu(ctx, os_name, arch)}
