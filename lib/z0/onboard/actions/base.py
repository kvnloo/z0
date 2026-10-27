"""What every APPLY action shares (design §2.5, §6.3): paths, the prepared env, the
journal, ownership markers and argv execution.

Rules every action follows:
- argv only, never a shell; argv[0] resolves under the prepared PATH (law T1);
- the env is an allowlist plus the step's declared env: no secret value reaches a
  child, PIP_BREAK_SYSTEM_PACKAGES is unset, PIP_NO_INPUT=1, LANG=C.UTF-8;
- every effect is journaled right after it happens (dirs carry `.z0-owned` with the run
  id, files a sha256, links their prior target), so rollback can prove ownership (R1);
- a directory an action was creating when it failed is removed again at once, so a
  re-run starts clean and nothing unjournaled is left behind;
- captured output is redacted before it is logged; adopted checkouts are never written
  to by z0's own file operations.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..journal import MARKER, Journal, marker_owner, sha256_file
from ..redact import Redactor

# Environment passed to every step: no secrets, no user aliases (§6.3).
ENV_ALLOW = ("HOME", "USER", "LOGNAME", "TMPDIR", "XDG_RUNTIME_DIR", "HTTPS_PROXY", "https_proxy",
             "HTTP_PROXY", "http_proxy", "NO_PROXY", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR",
             # container and test hooks for detect (see cli.sandbox_from_env)
             "Z0_DETECT_SYSROOT", "Z0_DETECT_SYSTEM_DIRS", "Z0_DETECT_OFFLINE")
FIXED_ENV = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PIP_NO_INPUT": "1",
             "PIP_DISABLE_PIP_VERSION_CHECK": "1", "GIT_TERMINAL_PROMPT": "0",
             "npm_config_update_notifier": "false", "npm_config_fund": "false",
             "npm_config_audit": "false", "PYTHONDONTWRITEBYTECODE": "1"}
OUTPUT_TAIL = 4000


class ActionError(Exception):
    """A step failed; the message is one redacted line for the receipt."""


@dataclass
class Outcome:
    ok: bool
    detail: str = ""
    output: str = ""


@dataclass
class RunResult:
    rc: Optional[int]
    out: str = ""

    @property
    def ok(self) -> bool:
        return self.rc == 0


def subprocess_runner(argv: list, cwd: Optional[str], env: dict, timeout: float) -> RunResult:
    try:
        proc = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        out = exc.output.decode("utf-8", "replace") if exc.output else ""
        return RunResult(None, out + f"\n[timed out after {timeout:.0f}s]")
    except OSError as exc:
        return RunResult(None, f"[could not run: {exc.strerror}]")
    return RunResult(proc.returncode, proc.stdout.decode("utf-8", "replace"))


@dataclass
class ActionCtx:
    """One APPLY (or VERIFY) run. Tests swap `runner`, `urls` and `fetch`."""
    z0_home: str
    home: str
    run_id: str
    run_dir: Path
    journal: Journal
    plan: dict
    snap: dict
    host: dict
    repo_root: str
    base_env: dict = field(default_factory=lambda: dict(os.environ))
    runner: Callable = subprocess_runner
    urls: dict = field(default_factory=dict)       # registry repo -> clone URL override
    fetch: Optional[Callable] = None               # (url, dest_path) download; default urllib
    redactor: Optional[Redactor] = None
    extra_path: list = field(default_factory=list)  # toolchain bin dirs made by this run
    warnings: list = field(default_factory=list)
    step_id: str = ""

    def __post_init__(self):
        self.home = str(self.home).rstrip("/") or "/"
        self.z0_home = str(self.z0_home).rstrip("/")
        self.redactor = self.redactor or Redactor(self.home)
        self.steps = {e["step"]["id"]: e["step"] for e in self.plan["steps"]}

    # --- paths --------------------------------------------------------------------
    def expand(self, text: str) -> str:
        text = str(text)
        if text == "~" or text.startswith("~/"):
            return self.home + text[1:]
        if text == "$Z0_HOME" or text.startswith("$Z0_HOME/"):
            return self.z0_home + text[len("$Z0_HOME"):]
        return text

    def form(self, path) -> str:
        """Plan form of an absolute path: `$Z0_HOME/...`, `~/...`, else as is."""
        path = os.path.abspath(str(path))
        if path == self.z0_home or path.startswith(self.z0_home + "/"):
            return "$Z0_HOME" + path[len(self.z0_home):]
        if path == self.home or path.startswith(self.home + "/"):
            return "~" + path[len(self.home):]
        return path

    def component(self, cid: Optional[str]) -> dict:
        comps = (self.snap.get("components") or {}).get("components") or {}
        return comps.get(cid or "", {}) or {}

    def tree(self, cid: str) -> Optional[str]:
        entry = (self.plan.get("components") or {}).get(cid) or {}
        return self.expand(entry["tree"]) if entry.get("tree") else None

    def adopted_trees(self) -> list:
        return [self.expand(e["tree"]) for e in (self.plan.get("components") or {}).values()
                if e.get("adopted") and e.get("tree")]

    def in_adopted(self, path: str) -> bool:
        path = os.path.abspath(path)
        return any(path == t or path.startswith(t.rstrip("/") + "/") for t in self.adopted_trees())

    def chain(self, step: dict) -> list:
        """The steps `step` needs, nearest first (breadth first, declared order)."""
        seen, out, frontier = {step["id"]}, [], list(step.get("needs") or [])
        while frontier:
            nxt = []
            for sid in frontier:
                if sid in seen or sid not in self.steps:
                    continue
                seen.add(sid)
                out.append(self.steps[sid])
                nxt.extend(self.steps[sid].get("needs") or [])
            frontier = nxt
        return out

    def nearest(self, step: dict, kinds: tuple, same_component: bool = True) -> Optional[dict]:
        for dep in self.chain(step):
            if dep["kind"] in kinds and (not same_component or dep.get("component") == step.get("component")):
                return dep
        return None

    @staticmethod
    def created_path(step: dict) -> Optional[str]:
        creates = step.get("creates") or []
        return creates[0] if creates else None

    def venv_dir(self, step: dict) -> Optional[str]:
        """Target dir of a `venv` step: its first `creates`, else the probe's venv root."""
        if step.get("creates"):
            return self.expand(step["creates"][0])
        probe = (step.get("probe") or {}).get("exists")
        if probe and "/bin/" in probe:
            return self.expand(probe.split("/bin/", 1)[0])
        return None

    def workdir(self, step: dict) -> str:
        """Where a step runs (§2.5 `where`): the nearest tree its `needs` lead to (a
        stamped release for `release`, the build tree or the adopt_or_clone tree
        otherwise), else the component's tree, else the z0 checkout (hub steps)."""
        where = step.get("where")
        for dep in self.chain(step):
            if dep.get("component") != step.get("component"):
                continue
            if where == "release" and dep["kind"] == "stage_release" and dep.get("creates"):
                return self.expand(dep["creates"][0])
            if where != "release" and dep["kind"] == "build_tree" and dep.get("creates"):
                return self.expand(dep["creates"][0])
            if where != "release" and dep["kind"] == "adopt_or_clone":
                tree = self.tree(dep["component"])
                if tree:
                    return tree
        if step.get("component") and step["component"] != "z0" and self.tree(step["component"]):
            return self.tree(step["component"])
        return self.repo_root

    def venv_of(self, step: dict) -> Optional[str]:
        if step["kind"] == "venv":
            return self.venv_dir(step)
        dep = self.nearest(step, ("venv",))
        return self.venv_dir(dep) if dep else None

    def journal_steps_done(self, step_id: str) -> bool:
        """True when this run journaled an effect for `step_id` (it ran here)."""
        return any(e.get("event") == "effect" and e.get("step") == step_id
                   for e in self.journal.entries())

    # --- env and PATH (law T1) ------------------------------------------------------
    def path_dirs(self, venv: Optional[str] = None) -> list:
        dirs = [self.expand(d) for d in self.plan.get("prepared_path") or []]
        system = [d for d in dirs if d in ("/usr/bin", "/bin")]
        rest = [d for d in dirs if d not in system]
        extra = [d for d in self.extra_path if d not in rest]
        front = [os.path.join(venv, "bin")] if venv else []
        return front + rest + extra + (system or ["/usr/bin", "/bin"])

    def env_for(self, step: dict, venv: Optional[str] = None) -> dict:
        env = {key: self.base_env[key] for key in ENV_ALLOW if key in self.base_env}
        env["HOME"] = self.home
        env["Z0_HOME"] = self.z0_home
        env.update(FIXED_ENV)
        # tool download caches live in z0's own cache dir, never in ~/.bun (rollback R2)
        env["BUN_INSTALL_CACHE_DIR"] = os.path.join(self.z0_home, "cache", "bun")
        env["BUN_RUNTIME_TRANSPILER_CACHE_PATH"] = os.path.join(self.z0_home, "cache", "bun-transpiler")
        env["PATH"] = os.pathsep.join(self.path_dirs(venv))
        if venv:
            env["VIRTUAL_ENV"] = venv
        for key, value in (step.get("env") or {}).items():
            if key == "PATH":
                parts = [self.expand(p) for p in str(value).split(":") if p]
                parts += [d for d in self.extra_path if d not in parts]
                env["PATH"] = os.pathsep.join(([os.path.join(venv, "bin")] if venv else []) + parts)
            else:
                env[key] = self.expand(str(value))
        env.pop("PIP_BREAK_SYSTEM_PACKAGES", None)
        return env

    def resolve(self, name: str, cwd: str, env: dict) -> Optional[str]:
        name = self.expand(name)
        if os.path.isabs(name):
            return name if os.access(name, os.X_OK) else None
        if "/" in name:
            path = os.path.normpath(os.path.join(cwd, name))
            return path if os.access(path, os.X_OK) else None
        return shutil.which(name, path=env.get("PATH", ""))

    def exec(self, argv: list, *, cwd: str, env: dict, timeout: float = 600,
             label: Optional[str] = None) -> RunResult:
        """Run argv (no shell) and log its redacted output under runs/<id>/logs/."""
        argv = [self.expand(a) for a in argv]
        exe = self.resolve(argv[0], cwd, env)
        if exe is None:
            result = RunResult(None, f"[{argv[0]}: not found on the prepared PATH]")
        elif not os.path.isdir(cwd):
            result = RunResult(None, f"[working directory {self.form(cwd)} does not exist]")
        else:
            result = self.runner([exe, *argv[1:]], cwd, env, timeout)
        result = RunResult(result.rc, self.redactor(result.out or ""))
        self.log(label or self.step_id, f"$ {' '.join(self.form(a) if os.path.isabs(a) else a for a in argv)}"
                 f"  (cwd {self.form(cwd)}, rc {result.rc})\n{result.out}\n")
        return result

    def log(self, name: str, text: str) -> None:
        logs = self.run_dir / "logs"
        old = os.umask(0o077)
        try:
            logs.mkdir(exist_ok=True, mode=0o700)
            with open(logs / f"{name or 'run'}.log", "a", encoding="utf-8") as fh:
                fh.write(self.redactor(text))
        finally:
            os.umask(old)

    @staticmethod
    def tail(text: str) -> str:
        return text[-OUTPUT_TAIL:]

    # --- journaled file operations ---------------------------------------------------
    def record(self, effect: dict) -> None:
        self.journal.effect(self.step_id, effect)

    def makedirs(self, path: str) -> None:
        """Create `path`'s missing ancestors and `path` itself, journaling each new one
        as `mkdir` (removed again on rollback only while empty)."""
        missing = []
        current = os.path.abspath(path)
        while not os.path.exists(current):
            missing.append(current)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        for directory in reversed(missing):
            os.mkdir(directory, 0o755)
            self.record({"kind": "mkdir", "path": self.form(directory)})

    def own(self, path: str) -> None:
        """Mark a directory this run created as z0-owned and journal it (`dir`)."""
        with open(os.path.join(path, MARKER), "w", encoding="utf-8") as fh:
            fh.write(self.run_id + "\n")
        exclude = os.path.join(path, ".git", "info", "exclude")
        if os.path.isdir(os.path.join(path, ".git")):
            os.makedirs(os.path.dirname(exclude), exist_ok=True)
            with open(exclude, "a", encoding="utf-8") as fh:
                fh.write(f"/{MARKER}\n")
        self.record({"kind": "dir", "path": self.form(path), "marker": self.run_id})

    @contextlib.contextmanager
    def creating(self, path: str):
        """Create a new directory tree at `path` (it must not exist). Its parents are
        made and journaled first; on failure whatever was made at `path` is removed;
        on success it is marked owned and journaled."""
        if os.path.lexists(path):
            raise ActionError(f"{self.form(path)} already exists and was not made by this run")
        self.makedirs(os.path.dirname(path))
        try:
            yield path
        except BaseException:
            if os.path.lexists(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.islink(path):
                os.unlink(path)
            raise
        if not os.path.isdir(path):
            raise ActionError(f"{self.form(path)} was not created")
        self.own(path)

    def record_created(self, path: str) -> None:
        """Journal a path a command created: a dir is marked owned, a file hashed."""
        if os.path.isdir(path) and not os.path.islink(path):
            self.own(path)
        elif os.path.isfile(path) and not os.path.islink(path):
            self.record({"kind": "file", "path": self.form(path), "sha256": sha256_file(path)})
        elif os.path.islink(path):
            self.record({"kind": "symlink", "path": self.form(path), "target": self.link_form(os.readlink(path)),
                         "prior": None})

    def write_file(self, path: str, data: bytes, mode: int = 0o600) -> str:
        """Atomic write (umask 077, then `mode`, checked after the write). An existing
        file is backed up to runs/<id>/backups/ first and journaled as `replace`."""
        if self.in_adopted(path):
            raise ActionError(f"{self.form(path)} is inside an adopted checkout; z0 never writes there")
        if os.path.islink(path) or os.path.isdir(path):
            raise ActionError(f"{self.form(path)} exists and is not a regular file")
        self.makedirs(os.path.dirname(path))
        prior_sha = sha256_file(path)
        prior_mode = (os.stat(path).st_mode & 0o7777) if prior_sha is not None else None
        backup = None
        if prior_sha is not None:
            backups = self.run_dir / "backups"
            old = os.umask(0o077)
            try:
                backups.mkdir(exist_ok=True, mode=0o700)
                backup = backups / f"{len(list(backups.iterdir())):03d}-{os.path.basename(path)}"
                shutil.copyfile(path, backup)
                os.chmod(backup, 0o600)
            finally:
                os.umask(old)
        old = os.umask(0o077)
        try:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".z0-tmp-")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        finally:
            os.umask(old)
        if (os.stat(path).st_mode & 0o777) != mode:
            raise ActionError(f"{self.form(path)}: mode is not {oct(mode)} after the write")
        digest = sha256_file(path)
        if backup is None:
            self.record({"kind": "file", "path": self.form(path), "sha256": digest})
        else:
            self.record({"kind": "replace", "path": self.form(path), "sha256": digest,
                         "prior_sha256": prior_sha, "prior_mode": prior_mode,
                         "backup": str(backup.relative_to(self.run_dir))})
        return digest

    def symlink(self, link: str, target: str) -> None:
        """Atomically point `link` at `target`, journaling the prior target."""
        if os.path.lexists(link) and not os.path.islink(link):
            raise ActionError(f"{self.form(link)} exists and is not a symlink")
        prior = os.readlink(link) if os.path.islink(link) else None
        self.makedirs(os.path.dirname(link))
        tmp = f"{link}.z0-tmp-{os.getpid()}"
        if os.path.lexists(tmp):
            os.unlink(tmp)
        os.symlink(target, tmp)
        os.replace(tmp, link)
        self.record({"kind": "symlink", "path": self.form(link), "target": self.link_form(target),
                     "prior": self.link_form(prior) if prior else None})

    def link_form(self, target: str) -> str:
        """A link target as journaled: plan form when absolute, as is when relative."""
        return self.form(target) if os.path.isabs(target) else target


def is_owned_by(path: str, run_id: str) -> bool:
    return marker_owner(path) == run_id


def has_git_ancestor(path: str) -> bool:
    """Law S1's runtime scan: a `.git` in the path or any ancestor means a checkout."""
    current = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent
