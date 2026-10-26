"""A throwaway fake host for detect tests: temp HOME, sysroot and fakebin.

Nothing here touches the real host's harness configs or services: every probed
program is a stub in a temp dir (or a symlink to a harmless real tool: sh, git,
python3), /etc and /proc come from a temp sysroot, and the network is a stub.
Stubs log their argv to <root>/calls.log so tests can prove what ran.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

CANARY = "z0-canary-7f3a9c1e5b"

STUBS = {
    "nproc": 'echo 8',
    "lscpu": 'printf "# core\\n0\\n0\\n1\\n1\\n2\\n2\\n3\\n3\\n"',
    "ldd": 'echo "ldd (GNU libc) 2.41"',
    "pacman": 'exit 0',
    "systemctl": '''case "$*" in
  *is-system-running*) echo running ;;
  *list-units*) echo "dash-bridge.service loaded active running Dash bridge"; echo "other.service loaded active running x" ;;
  *show*) echo "ExecStart={ path=$FAKE_HOME/.local/lib/dash/releases/5f3ee27f6e431ba83abfe9a4a94b2c0757910ddb/bun ; argv[]=bun run index.ts }"; echo "WorkingDirectory=$FAKE_HOME/.local/lib/dash/releases/5f3ee27f6e431ba83abfe9a4a94b2c0757910ddb/bridge"; echo "ActiveState=active" ;;
esac''',
    "loginctl": 'echo Linger=no',
    "pactl": 'echo "0 alsa_output.monitor module"',
    "arecord": 'exit 1',
    "ss": 'echo "LISTEN 0 512 100.64.0.7:4747 0.0.0.0:* users:((\\"bun\\",pid=42,fd=3))"',
    "tailscale": '''case "$1" in
  ip) echo 100.64.0.7 ;;
  status) echo '{"BackendState":"Running","Self":{"DNSName":"fake.example.ts.net.","TailscaleIPs":["100.64.0.7"]},"Peer":{"x":{"HostName":"secret-peer"}}}' ;;
esac''',
}

HOME_BINS = {
    ".local/bin/claude": 'echo "2.1.0 (Claude Code)"',
    ".local/bin/codex": 'echo "codex-cli 0.162.1"',
    ".local/bin/grok": 'touch "$FAKE_ROOT/grok-was-executed"; echo grok 9.9.9',
    ".local/bin/uv": 'echo "uv 0.12.21"',
    ".local/bin/mystery-tool": 'touch "$FAKE_ROOT/unknown-was-executed"',
    ".bun/bin/bun": 'echo 1.4.3',
}


def _stub(path: Path, body: str, root: Path) -> None:
    body = body.replace("$FAKE_HOME", str(root / "home")).replace("$FAKE_ROOT", str(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n"
                    f'printf "%s\\n" "${{0##*/}} $*" >> "{root}/calls.log"\n'
                    f"{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _git(*args, cwd) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd),
                        "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def build(root: Path) -> dict:
    """Create the fake host under `root`; returns paths and the env to use."""
    home, sysroot, sysbin, userbin = root / "home", root / "sysroot", root / "sysbin", root / "userbin"
    for d in (home, sysroot, sysbin, userbin):
        d.mkdir(parents=True, exist_ok=True)
    (sysroot / "etc").mkdir()
    (sysroot / "etc/os-release").write_text('NAME="Fake Linux"\nID=arch\n')
    (sysroot / "etc/machine-id").write_text("0123456789abcdef0123456789abcdef\n")
    (sysroot / "proc").mkdir()
    (sysroot / "proc/meminfo").write_text("MemTotal:       16252928 kB\nMemFree: 1 kB\n")
    drm = sysroot / "sys/class/drm/card0/device"
    drm.mkdir(parents=True)
    (drm / "vendor").write_text("0x1002\n")
    for name, body in STUBS.items():
        _stub(sysbin / name, body, root)
    for tool in ("sh", "git"):
        os.symlink(shutil.which(tool), sysbin / tool)
    os.symlink(sys.executable, sysbin / "python3")
    for rel, body in HOME_BINS.items():
        _stub(home / rel, body, root)
    # A registry well-known dir (/usr/local/bin): detect must look for it in the sysroot.
    _stub(sysroot / "usr/local/bin/rustup", 'echo "rustup 1.29.2 (fake)"', root)
    # Never-open paths, each holding the canary.
    for rel in (".hermes/config.yaml", ".ssh/id_ed25519", ".dash/token", ".z0int/shadow/x.json",
                ".claude/.credentials.json", ".codex/auth.json"):
        path = home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CANARY)
    (home / ".dash/token").chmod(0o600)
    (home / ".dash").chmod(0o700)
    (home / ".claude/projects").mkdir(parents=True)
    (home / ".grok").mkdir()
    repo = home / "workspace/z0evals"
    repo.mkdir(parents=True)
    _git("init", "-q", cwd=repo)
    _git("remote", "add", "origin", "https://github.com/kvnloo/z0evals.git", cwd=repo)
    (repo / "README.md").write_text("x\n")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    other = home / "workspace/private-thing"
    other.mkdir(parents=True)
    _git("init", "-q", cwd=other)
    _git("remote", "add", "origin", "https://github.com/someone/private-thing.git", cwd=other)
    env = {"HOME": str(home), "PATH": str(userbin), "USER": "fake", "FAKE_ROOT": str(root),
           "FAKE_HOME": str(home), "CEREBRAS_API_KEY": CANARY, "WAYLAND_DISPLAY": "wayland-1",
           "LANG": "C"}
    return {"root": root, "home": home, "sysroot": sysroot, "sysbin": sysbin, "userbin": userbin,
            "env": env, "repo": repo}


def tree_state(root: Path, skip=()) -> dict:
    """Path -> (size, mtime_ns, mode) for every entry under root (symlinks not followed)."""
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if os.path.join(dirpath, d) not in skip]
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            state[path] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return state
