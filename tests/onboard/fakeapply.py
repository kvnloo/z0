"""Fixtures for APPLY / VERIFY / ROLLBACK tests (design §10 layer 2). No real host change.

Builds on fakehost (temp HOME, sysroot, fake bins) and adds:
- a fake z0evals origin: a local git repo whose scripts stand in for the real tier
  scripts (each one exits 0; the generators create what the registry says they create);
- a pinned "node" toolchain archive (file:// URL, real sha256) whose `npm` stub makes
  the web tier's outputs;
- a registry snapshot patched to point z0evals at the fake origin's commit, the node
  pin at the archive, and with the hub steps removed (they run the real checkout's
  scripts; tests/onboard/test_apply_checks.py covers them with a fake runner).

Every write lands under the test's temp dir; `calls.log` records every fake bin call.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
from typing import Optional

from tests.onboard import fakehost
from tests.onboard.support import ROOT, snapshot

GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}

ORIGIN_FILES = {
    ".gitignore": ".venv/\nsite/\nweb/data/posts/\nweb/node_modules/\nweb/out/\n__pycache__/\n",
    "requirements.txt": "# the fake origin needs no packages (offline install)\n",
    ".verified-oss-loop/rollout.py": "print('worker base: main')\n",
    ".verified-oss-loop/pages-url-map.py": "import sys\nsys.exit(0)\n",
    "tests/__init__.py": "",
    "tests/test_arm_identity.py": "print('arm identity ok')\n",
    "tests/expire_claims.py": "print('claims ok')\n",
    "tests/test_pages_publication.py": "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n",
    "tests/test_optchat_publication.py": "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n",
    "tests/test_build_posts.py": "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n",
    "scripts/validate.py": "import sys\nassert sys.prefix != sys.base_prefix, 'not in the venv'\nprint('valid')\n",
    "scripts/validate_optchat_publication.py": "print('ok')\n",
    "scripts/audit_web_source.py": "print('ok')\n",
    "scripts/audit_web_export.py": "import os, sys\nsys.exit(0 if os.path.isfile('web/out/index.html') else 1)\n",
    "scripts/build_site.py": "import os\nos.makedirs('site', exist_ok=True)\nopen('site/index.html', 'w').write('<html></html>')\n",
    "scripts/build_site_data.py": "open('web/data/optchat-long-horizon-v0.json', 'w').write('{}')\n",
    "scripts/build_posts.py": "import os\nos.makedirs('web/data/posts', exist_ok=True)\nopen('web/data/posts/a.json', 'w').write('{}')\n",
    "web/data/.keep": "",
    "web/package.json": '{"name": "fake-web", "private": true}\n',
}

NPM = """#!/bin/sh
printf "%s\\n" "npm $*" >> "$FAKE_LOG"
case "$*" in
  "ci --no-audit --no-fund --prefix web") mkdir -p web/node_modules ;;
  "--prefix web run typecheck") test -d web/node_modules ;;
  "--prefix web run build") test "$Z0_BASE_PATH" = /z0evals && mkdir -p web/out && echo '<html>' > web/out/index.html ;;
  *) exit 9 ;;
esac
"""


def git(*args, cwd) -> str:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd), **GIT_ENV}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def make_origin(path: Path) -> str:
    """The fake z0evals origin; returns its HEAD SHA (branches main/dev/nightly/preview)."""
    path.mkdir(parents=True)
    for rel, text in ORIGIN_FILES.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    git("init", "-q", "-b", "main", cwd=path)
    git("add", "-A", cwd=path)
    git("commit", "-qm", "fake z0evals", cwd=path)
    for branch in ("dev", "nightly", "preview"):
        git("branch", branch, cwd=path)
    return git("rev-parse", "HEAD", cwd=path)


def make_node_archive(path: Path, version: str, target: str, log: Path) -> str:
    """A node toolchain tarball with fake `node` and `npm`; returns its sha256."""
    top = f"node-v{version}-{target}"
    files = {f"{top}/bin/node": f"#!/bin/sh\necho v{version}\n",
             f"{top}/bin/npm": NPM.replace("$FAKE_LOG", str(log))}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
    path.write_bytes(buf.getvalue())
    return hashlib.sha256(buf.getvalue()).hexdigest()


def patched_snapshot(origin_url: str, sha: str, node_url: str, node_sha: str, *, hub: bool = False) -> dict:
    snap = snapshot()
    comp = snap["components"]["components"]["z0evals"]
    comp["install"]["ref"] = sha
    comp["install"]["clone"] = origin_url
    if not hub:
        snap["onboarding"]["hub"] = {"steps": []}
    node = snap["toolchains"]["tools"]["node"]["install"]
    node["url"] = node_url
    for target in node["targets"].values():
        target["sha256"] = node_sha
    return snap


class FakeApply:
    """One fake host plus everything an APPLY needs, under `root`."""

    def __init__(self, root: Path, *, adopt: bool = False, online: bool = False, hub: bool = False,
                 fast: bool = True):
        """`fast`: make the z0evals venv without pip and turn its (empty) install into a
        no-op, which saves ~25 s of ensurepip per apply. One test class keeps the
        registry's real `python3 -m venv` + `.venv/bin/pip install -r` path."""
        self.root = root
        self.fake = fakehost.build(root)
        self.home = self.fake["home"]
        self.z0_home = self.home / ".z0"
        self.online = online
        self.log = root / "calls.log"
        self.origin = root / "origin" / "z0evals"
        self.sha = make_origin(self.origin)
        node_tar = root / "dist" / "node.tar.gz"
        node_tar.parent.mkdir()
        self.node_sha = make_node_archive(node_tar, "22.23.4", "linux-x64", self.log)
        self.snap = patched_snapshot(self.origin.as_uri(), self.sha, node_tar.as_uri(), self.node_sha, hub=hub)
        self.snap["repo_setups"] = {}
        if fast:
            for step in self.snap["components"]["components"]["z0evals"]["onboard"]["steps"]:
                if step["id"] == "z0evals.venv":
                    step["argv"] = ["python3", "-m", "venv", "--without-pip", ".venv"]
                elif step["id"] == "z0evals.deps":
                    step["argv"] = [".venv/bin/python", "-c", "import sys; sys.exit(0)"]
        for target in self.snap["toolchains"]["tools"]["node"]["install"]["targets"].values():
            target["target"] = "linux-x64"
        # The README-only checkout fakehost makes would be adopted; replace it.
        repo = self.fake["repo"]
        subprocess.run(["rm", "-rf", str(repo)], check=True)
        if adopt:
            git("clone", "-q", str(self.origin), str(repo), cwd=root)
            git("checkout", "-q", "--detach", self.sha, cwd=repo)
            git("remote", "set-url", "origin", "https://github.com/kvnloo/z0evals.git", cwd=repo)
        self.env = dict(self.fake["env"])
        self.env["Z0_HOME"] = str(self.z0_home)

    # --- detect / plan --------------------------------------------------------------
    def detect(self) -> dict:
        from z0.onboard.detect import Ctx, detect
        ctx = Ctx(registry=self.snap, env=self.env, home=str(self.home), z0_home=str(self.z0_home),
                  sysroot=str(self.fake["sysroot"]), system_dirs=[str(self.fake["sysbin"])],
                  http_head=lambda url, timeout: self.online)
        host = detect(ctx)
        # The temp volume's real free space is not part of the fixture: fix it at 100 GiB.
        for disk in (host.get("hardware") or {}).get("disks") or []:
            disk["free_gib"] = 100.0
        return host

    def request(self, grants: Optional[dict] = None, mode: str = "auto") -> dict:
        return {"mode": mode, "profile": "minimal", "with_ids": [], "without_ids": ["oh-my-pi", "dash"],
                "grants": grants or {"bundles": [], "source": "none"}, "pin_policy": "pinned",
                "llm": "none"}

    def plan(self, host: dict, request: dict) -> dict:
        from z0.onboard.plan import plan
        return plan(host, self.snap, mode=request["mode"], profile=request["profile"],
                    with_ids=request["with_ids"], without_ids=request["without_ids"],
                    grants=request["grants"], pin_policy=request["pin_policy"], llm=request["llm"])

    def write_run(self, host: dict, plan_obj: dict) -> Path:
        run = self.z0_home / "onboard" / "runs" / f"20261026T000000Z-{plan_obj['plan_hash'][:8]}"
        n = 0
        while run.exists():
            n += 1
            run = run.with_name(f"20261026T0000{n:02d}Z-{plan_obj['plan_hash'][:8]}")
        run.mkdir(parents=True, mode=0o700)
        for name, obj in (("host.json", host), ("plan.json", plan_obj)):
            (run / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
        return run

    def deps(self, *, detect: bool = True, confirm=None, out=None):
        from z0.onboard.apply import Deps
        lines = []
        return Deps(z0_home=str(self.z0_home), home=str(self.home), repo_root=str(ROOT),
                    snap=self.snap, base_env=self.env, detect=self.detect if detect else None,
                    replan=self.plan, confirm=confirm, out=out or lines.append)

    def calls(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    # --- whole flows ------------------------------------------------------------------
    def onboard(self, grants: Optional[dict] = None):
        """detect -> plan -> write run -> apply -> verify. Returns (run, apply result, code, receipt)."""
        from z0.onboard.apply import apply_run
        from z0.onboard.verify import verify_run
        host = self.detect()
        request = self.request(grants)
        plan_obj = self.plan(host, request)
        run = self.write_run(host, plan_obj)
        deps = self.deps(detect=False)
        result = apply_run(run, deps)
        code, receipt = verify_run(run, deps, prior=result.results, host=result.host,
                                   apply_code=result.code)
        return run, result, code, receipt


def tree_bytes(root: Path, skip=()) -> dict:
    """path -> (kind, sha256 | link target, mode) for every entry under root; dirs only
    by presence and mode (their mtimes change when children come and go)."""
    out = {}
    skip = tuple(str(s) for s in skip)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not os.path.join(dirpath, d).startswith(skip)]
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            if path.startswith(skip):
                continue
            st = os.lstat(path)
            if os.path.islink(path):
                out[path] = ("link", os.readlink(path), st.st_mode)
            elif os.path.isdir(path):
                out[path] = ("dir", "", st.st_mode)
            else:
                out[path] = ("file", hashlib.sha256(Path(path).read_bytes()).hexdigest(), st.st_mode)
    return out
