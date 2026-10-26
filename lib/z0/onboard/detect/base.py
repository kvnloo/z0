"""Detect context: the only door from detectors to the host (design §4).

Read-only by construction: it offers stat, bounded reads that honour the read
denylist, and `run` (argv only, minimal allowlisted env, stdin closed, timeout, never
raises). Tests swap `sysroot`, `system_dirs`, `uname`, `hostname` and `http_head` so no
detector touches the real host's configs or services. With a `sysroot` other than `/`,
every absolute path outside $HOME and $Z0_HOME (the registry's well-known dirs such as
/usr/local/bin and /opt/homebrew/bin) is read under the sysroot too: a sealed fake host
never sees, or runs, the real host's binaries.
"""
from __future__ import annotations

import fnmatch
import glob
import os
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..util import tilde

# Environment passed to probed programs: no secrets, no user aliases (§2.2).
ENV_ALLOW = ("HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "XDG_RUNTIME_DIR",
             "DBUS_SESSION_BUS_ADDRESS")


@dataclass
class RunResult:
    rc: Optional[int]          # None: not found, not runnable, or timed out
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.rc == 0


def _subprocess_runner(argv, env, timeout, cwd) -> RunResult:
    try:
        proc = subprocess.run(argv, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError, ValueError):
        return RunResult(None)
    return RunResult(proc.returncode, proc.stdout.decode("utf-8", "replace"),
                     proc.stderr.decode("utf-8", "replace"))


def _http_head(url: str, timeout: float) -> bool:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "z0-onboard"})
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True          # any HTTP answer means reachable
    except Exception:  # noqa: BLE001 - offline, DNS, TLS, timeout: all "unreachable"
        return False


@dataclass
class Ctx:
    registry: dict
    env: dict = field(default_factory=lambda: dict(os.environ))
    home: Optional[str] = None
    z0_home: Optional[str] = None
    sysroot: str = "/"
    system_dirs: Optional[list] = None
    uname: Optional[tuple] = None        # (sysname, machine)
    hostname: Optional[str] = None
    now: Optional[str] = None
    runner: Callable = _subprocess_runner
    http_head: Callable = _http_head
    prepared_path: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    unknowns: list = field(default_factory=list)

    def __post_init__(self):
        self.home = str(self.home or self.env.get("HOME") or Path.home())
        self.z0_home = str(self.z0_home or self.env.get("Z0_HOME") or os.path.join(self.home, ".z0"))
        if self.system_dirs is None:
            detect = (self.registry.get("toolchains") or {}).get("detect") or {}
            self.system_dirs = list(detect.get("system_dirs") or ["/usr/bin", "/bin"])
        if self.uname is None:
            info = os.uname()
            self.uname = (info.sysname, info.machine)
        if self.hostname is None:
            self.hostname = socket.gethostname()

    # --- paths ------------------------------------------------------------------
    def expand(self, text: str) -> str:
        """`~` and `$Z0_HOME` to absolute paths (for local stat/glob only). Under a test
        sysroot, any other absolute path is mapped into it."""
        if text == "~" or text.startswith("~/"):
            text = self.home + text[1:]
        if text == "$Z0_HOME" or text.startswith("$Z0_HOME/"):
            text = self.z0_home + text[len("$Z0_HOME"):]
        if self.sealed() and os.path.isabs(text) and not self._under(text, self.home) \
                and not self._under(text, self.z0_home) and not self._under(text, self.sysroot):
            text = self.sys(text)
        return text

    def sealed(self) -> bool:
        return os.path.normpath(self.sysroot or "/") != "/"

    @staticmethod
    def _under(path: str, root: str) -> bool:
        root = root.rstrip("/") or "/"
        return path == root or path.startswith(root + "/")

    def tilde(self, path: str) -> str:
        return tilde(str(path), self.home)

    def z0_form(self, path: str) -> str:
        """`$Z0_HOME/...` for paths under Z0_HOME, else `~/...` (the plan's path forms)."""
        path = str(path)
        root = self.z0_home.rstrip("/")
        if path == root or path.startswith(root + "/"):
            return "$Z0_HOME" + path[len(root):]
        return self.tilde(path)

    def sys(self, path: str) -> str:
        """A system path (/proc, /etc, /sys) under the test sysroot."""
        return os.path.join(self.sysroot, path.lstrip("/"))

    def glob(self, pattern: str) -> list:
        return sorted(glob.glob(self.expand(pattern)))

    def denied(self, path: str) -> bool:
        patterns = ((self.registry.get("onboarding") or {}).get("denylists") or {}).get("reads") or []
        form = self.tilde(path)
        return any(fnmatch.fnmatch(form, pat) or fnmatch.fnmatch(os.path.basename(form), pat)
                   for pat in patterns)

    def stat(self, path: str):
        try:
            return os.stat(path)
        except OSError:
            return None

    def lexists(self, path: str) -> bool:
        return os.path.lexists(path)

    def read_text(self, path: str, limit: int = 65536) -> Optional[str]:
        """Bounded read; refuses denylisted paths (never opened, §4)."""
        if self.denied(path):
            return None
        try:
            with open(path, "rb") as fh:
                return fh.read(limit).decode("utf-8", "replace")
        except OSError:
            return None

    # --- programs ---------------------------------------------------------------
    def search_dirs(self) -> list:
        return list(self.prepared_path) if self.prepared_path else self.user_path() + list(self.system_dirs)

    def user_path(self) -> list:
        return [d for d in (self.env.get("PATH") or "").split(os.pathsep) if d]

    def which(self, name: str, dirs: Optional[list] = None) -> Optional[str]:
        for directory in dirs if dirs is not None else self.search_dirs():
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def child_env(self, path_dirs: Optional[list] = None) -> dict:
        env = {key: self.env[key] for key in ENV_ALLOW if key in self.env}
        env["HOME"] = self.home
        env["LANG"] = env["LC_ALL"] = "C"
        env["PATH"] = os.pathsep.join(path_dirs if path_dirs is not None else self.search_dirs())
        return env

    def run(self, argv: list, timeout: float = 5.0, cwd: Optional[str] = None,
            path_dirs: Optional[list] = None) -> RunResult:
        """Run argv (no shell). argv[0] is resolved under the search dirs first."""
        if not argv:
            return RunResult(None)
        exe = argv[0] if os.path.isabs(argv[0]) else self.which(argv[0], path_dirs)
        if exe is None:
            return RunResult(None)
        try:
            return self.runner([exe, *argv[1:]], self.child_env(path_dirs), timeout, cwd)
        except Exception:  # noqa: BLE001 - detectors never raise
            return RunResult(None)

    def unknown(self, item: dict) -> None:
        self.unknowns.append(item)

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)
