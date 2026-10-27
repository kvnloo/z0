"""`ensure_toolchain` (§2.5): resolve the tool; else a user-local pinned install with a
sha256 check into `$Z0_HOME/toolchains/<tool>/<version>`. Undo: remove the owned dir.

- `version: system` tools (git, ffmpeg, ...) are never installed: sudo and system
  packages are C2. A missing one fails with the package hint the plan already showed.
- `python`: CPython from uv (`uv python install`), with uv itself the pinned download
  when it is not on the prepared PATH. Both land under $Z0_HOME/toolchains.
- archives (.tar.gz, .tar.xz, .zip) are unpacked with path checks; the top directory
  named by the registry `layout` is stripped, so binaries sit at `<dir>/` or `<dir>/bin/`
  (the `$Z0_HOME/toolchains/*/*[/bin]` dirs detect puts on the prepared PATH).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile

from .base import ActionCtx, ActionError, Outcome


def _platform_key(ctx: ActionCtx, targets: dict) -> str:
    info = ctx.host.get("os") or {}
    os_name, arch, libc = info.get("os", "linux"), info.get("arch", "x86_64"), info.get("libc", "")
    if os_name == "linux" and str(libc).startswith("musl") and f"linux-musl-{arch}" in targets:
        return f"linux-musl-{arch}"
    return f"{os_name}-{arch}"


def _download_once(ctx: ActionCtx, url: str, dest: str) -> None:
    if ctx.fetch is not None:
        ctx.fetch(url, dest)
        return
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "z0-onboard"})
    with urllib.request.urlopen(request, timeout=120) as resp, open(dest, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)


def _download(ctx: ActionCtx, url: str, dest: str) -> None:
    """The pinned download, retried on network errors (sha256 is checked after).
    An HTTP 4xx is permanent (wrong URL or version): it fails at once."""
    import urllib.error

    errors: list = []

    def attempt() -> bool:
        try:
            _download_once(ctx, url, dest)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise
            errors.append(exc)
        except OSError as exc:   # URLError, timeouts and resets are OSErrors
            errors.append(exc)
        if os.path.lexists(dest):
            os.unlink(dest)
        return False

    if not ctx.retrying(f"download of {url}", attempt):
        raise errors[-1]


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_members(names, root: str) -> None:
    for name in names:
        target = os.path.realpath(os.path.join(root, name))
        if not (target == os.path.realpath(root) or target.startswith(os.path.realpath(root) + os.sep)):
            raise ActionError(f"archive member escapes the target dir: {name}")


def _unpack(archive: str, url: str, into: str) -> None:
    if url.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar")):
        with tarfile.open(archive) as tar:
            _safe_members(tar.getnames(), into)
            for member in tar.getmembers():
                if member.issym() or member.islnk():
                    _safe_members([os.path.join(os.path.dirname(member.name), member.linkname)], into)
            try:
                tar.extractall(into, filter="data")
            except TypeError:  # python without extraction filters
                tar.extractall(into)  # noqa: S202 - members checked above
    elif url.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            _safe_members(zf.namelist(), into)
            zf.extractall(into)
    else:  # a bare binary (rustup-init)
        shutil.copyfile(archive, os.path.join(into, os.path.basename(url)))


def _install_pinned(ctx: ActionCtx, tool: str, spec: dict, dest: str) -> str:
    """Download, check and unpack one pinned tool into `dest`; returns the binary path."""
    targets = spec.get("targets") or {}
    key = _platform_key(ctx, targets)
    target = targets.get(key)
    if not target:
        raise ActionError(f"{tool} {spec.get('version')}: no pinned build for {key}")
    fmt = {"version": spec["version"], "target": target["target"]}
    url = str(spec["url"]).format(**fmt)
    layout = str(spec.get("layout") or tool).format(**fmt)
    ctx.makedirs(os.path.dirname(dest))
    work = tempfile.mkdtemp(prefix=f".{tool}-", dir=os.path.dirname(dest))
    try:
        archive = os.path.join(work, "download")
        _download(ctx, url, archive)
        got = _sha256(archive)
        if got != target["sha256"]:
            raise ActionError(f"{tool} {spec['version']}: sha256 mismatch (got {got[:12]}, "
                              f"want {target['sha256'][:12]}); nothing installed")
        unpacked = os.path.join(work, "unpacked")
        os.mkdir(unpacked)
        _unpack(archive, url, unpacked)
        parts = layout.split("/")
        top = os.path.join(unpacked, parts[0])
        with ctx.creating(dest):
            if len(parts) > 1 and os.path.isdir(top):
                shutil.move(top, dest)
                binary = os.path.join(dest, *parts[1:])
            else:
                shutil.move(unpacked, dest)
                binary = os.path.join(dest, *parts)
            if not os.path.isfile(binary):
                raise ActionError(f"{tool}: {layout} is not in the archive")
            mode = os.stat(binary).st_mode
            os.chmod(binary, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _toolchains(ctx: ActionCtx) -> dict:
    return (ctx.snap.get("toolchains") or {}).get("tools") or {}


def _which(ctx: ActionCtx, name: str):
    return shutil.which(name, path=os.pathsep.join(ctx.path_dirs()))


def _ensure_uv(ctx: ActionCtx) -> str:
    found = _which(ctx, "uv")
    if found:
        return found
    spec = (_toolchains(ctx).get("uv") or {}).get("install") or {}
    dest = ctx.expand(f"$Z0_HOME/toolchains/uv/{spec['version']}")
    if os.path.isfile(os.path.join(dest, "uv")):
        return os.path.join(dest, "uv")
    binary = _install_pinned(ctx, "uv", spec, dest)
    ctx.extra_path.append(os.path.dirname(binary))
    return binary


def _python(ctx: ActionCtx, step: dict, version: str) -> Outcome:
    uv = _ensure_uv(ctx)
    dest = ctx.expand(f"$Z0_HOME/toolchains/python/{version}")
    with ctx.creating(dest):
        env = ctx.env_for(step)
        env.update(UV_PYTHON_INSTALL_DIR=os.path.join(dest, "cpython"),
                   UV_PYTHON_BIN_DIR=os.path.join(dest, "bin"), UV_NO_MODIFY_PATH="1",
                   UV_CACHE_DIR=os.path.join(ctx.z0_home, "cache", "uv"))
        result = ctx.exec([uv, "python", "install", version], cwd=dest, env=env, timeout=900)
        if not result.ok:
            raise ActionError(f"uv python install {version} failed (rc {result.rc})")
        bindir = os.path.join(dest, "bin")
        found = shutil.which(f"python{version}", path=bindir)
        if not found:
            import glob
            hits = sorted(glob.glob(os.path.join(dest, "cpython", "*", "bin", f"python{version}")))
            if hits:
                os.makedirs(bindir, exist_ok=True)
                os.symlink(hits[0], os.path.join(bindir, f"python{version}"))
                found = os.path.join(bindir, f"python{version}")
        if not found:
            raise ActionError(f"uv did not produce python{version}")
        if not os.path.lexists(os.path.join(bindir, "python3")):
            os.symlink(os.path.basename(found), os.path.join(bindir, "python3"))
    ctx.extra_path.append(os.path.join(dest, "bin"))
    return Outcome(True, f"CPython {version} via uv")


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    tool = step["toolchain"]["tool"]
    version = str(step["toolchain"]["version"])
    if version == "system":
        if _which(ctx, tool):
            return Outcome(True, f"{tool} resolves on the prepared PATH")
        raise ActionError(f"{tool} is not installed; it is a system package (C2, never automatic)")
    if tool == "python":
        return _python(ctx, step, version)
    spec = (_toolchains(ctx).get(tool) or {}).get("install") or {}
    if str(spec.get("version")) != version:
        raise ActionError(f"{tool}: the registry pins {spec.get('version')}, the plan wants {version}")
    dest = ctx.expand(f"$Z0_HOME/toolchains/{tool}/{version}")
    binary = _install_pinned(ctx, tool, spec, dest)
    ctx.extra_path.append(os.path.dirname(binary))
    return Outcome(True, f"{tool} {version} installed user-local (sha256 checked)")
