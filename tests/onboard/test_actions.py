"""The APPLY actions one by one (design §2.5), on temp dirs with a synthetic plan.

Covers what the z0evals flow does not exercise: build_tree -> stage_release ->
swap_current (law S1: live code only from a stamped release, never a tree with .git),
the pinned toolchain download (sha256 mismatch and archive escapes install nothing),
write_file backups and the adopted-tree guard, run's creates|probe rule, and the
http check on loopback.
"""
from __future__ import annotations

import hashlib
import http.server
import io
import os
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest

from tests.onboard.fakeapply import git, make_origin
from tests.onboard.support import ROOT, require_yaml, snapshot


def ctx_for(tmp: Path, steps: list, *, components=None, snap=None, urls=None, host=None):
    from z0.onboard.actions.base import ActionCtx
    from z0.onboard.journal import Journal
    home, z0_home = tmp / "home", tmp / "home" / ".z0"
    run = z0_home / "onboard" / "runs" / "20261026T000000Z-0000abcd"
    run.mkdir(parents=True)
    plan_obj = {"steps": [{"step": s, "state": {"status": "todo"}} for s in steps],
                "components": components or {}, "prepared_path": ["/usr/bin", "/bin"],
                "grants": {"bundles": [], "source": "none"}, "mode": "auto"}
    return ActionCtx(z0_home=str(z0_home), home=str(home), run_id=run.name, run_dir=run,
                     journal=Journal(run / "journal.jsonl", run.name), plan=plan_obj,
                     snap=snap or {"components": {"components": {}}}, host=host or {},
                     repo_root=str(ROOT), base_env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                     urls=urls or {})


def effects(ctx):
    from z0.onboard import journal
    return [e["effect"] for e in journal.effects(ctx.journal.entries())]


class ReleaseChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sha = make_origin(self.root / "origin" / "demo")
        comp = {"repo": "kvnloo/demo", "install": {"ref": self.sha, "clone": "https://example.com/x.git"}}
        self.snap = {"components": {"components": {"demo": comp}}}
        self.steps = [
            {"id": "demo.build", "component": "demo", "kind": "build_tree", "consent": {"class": "C0"},
             "where": "build", "creates": [f"$Z0_HOME/build/demo/{self.sha}"]},
            {"id": "demo.release", "component": "demo", "kind": "stage_release", "consent": {"class": "C0"},
             "where": "release", "needs": ["demo.build"],
             "creates": [f"~/.local/lib/demo/releases/{self.sha}"]},
            {"id": "demo.current", "component": "demo", "kind": "swap_current",
             "consent": {"class": "C1", "bundle": "services"}, "where": "release",
             "needs": ["demo.release"], "creates": ["~/.local/lib/demo/demo-current"]},
        ]
        self.ctx = ctx_for(self.root, self.steps, snap=self.snap,
                           urls={"kvnloo/demo": (self.root / "origin" / "demo").as_uri()})

    def tearDown(self):
        self.tmp.cleanup()

    def run_all(self):
        from z0.onboard.actions import ACTIONS
        for step in self.ctx.plan["steps"]:
            self.ctx.step_id = step["step"]["id"]
            ACTIONS[step["step"]["kind"]](self.ctx, step["step"])

    def test_S1_release_has_no_git_and_current_points_at_it(self):
        self.run_all()
        build = Path(self.ctx.expand(self.steps[0]["creates"][0]))
        release = Path(self.ctx.expand(self.steps[1]["creates"][0]))
        link = Path(self.ctx.expand(self.steps[2]["creates"][0]))
        self.assertTrue((build / ".git").exists())
        self.assertEqual(git("rev-parse", "HEAD", cwd=build), self.sha)
        self.assertFalse((release / ".git").exists())
        self.assertTrue((release / "deployed.json").is_file())
        self.assertTrue((release / "scripts" / "build_site.py").is_file())
        self.assertEqual(os.readlink(link), str(release))
        kinds = [e["kind"] for e in effects(self.ctx)]
        self.assertEqual(kinds.count("dir"), 2)
        self.assertIn("symlink", kinds)
        self.assertEqual(effects(self.ctx)[-1]["target"], f"~/.local/lib/demo/releases/{self.sha}")

    def test_S1_red_swap_to_a_tree_with_git_is_refused(self):
        from z0.onboard.actions import ActionError, swap_current
        from z0.onboard.actions.build_tree import execute as build
        self.ctx.step_id = "demo.build"
        build(self.ctx, self.steps[0])
        # A registry error that would point `current` at the build tree (it has .git).
        self.steps[1]["creates"] = list(self.steps[0]["creates"])
        with self.assertRaises(ActionError) as caught:
            swap_current.execute(self.ctx, self.steps[2])
        self.assertIn("through_checkout", str(caught.exception))
        self.assertFalse(os.path.lexists(self.ctx.expand(self.steps[2]["creates"][0])))

    def test_rollback_restores_link_first_then_removes_release(self):
        from z0.onboard.rollback import rollback_run
        self.run_all()
        counts = rollback_run(self.ctx.run_dir, self.ctx.z0_home, self.ctx.home, out=lambda *_: None)
        self.assertNotIn("kept_current", counts)
        self.assertFalse(os.path.lexists(self.ctx.expand("~/.local/lib/demo")))
        self.assertFalse(os.path.lexists(self.ctx.expand("$Z0_HOME/build")))

    def test_a_release_another_current_link_points_at_is_kept(self):
        from z0.onboard.rollback import rollback_run
        self.run_all()
        release = self.ctx.expand(self.steps[1]["creates"][0])
        os.symlink(release, self.ctx.expand("~/.local/lib/demo/other-current"))
        counts = rollback_run(self.ctx.run_dir, self.ctx.z0_home, self.ctx.home, out=lambda *_: None)
        self.assertEqual(counts.get("kept_current"), 1)
        self.assertTrue(os.path.isdir(release))

    def test_previous_current_is_restored(self):
        from z0.onboard.rollback import rollback_run
        old = Path(self.ctx.expand("~/.local/lib/demo/releases/old"))
        old.mkdir(parents=True)
        os.symlink(str(old), self.ctx.expand("~/.local/lib/demo/demo-current"))
        self.run_all()
        rollback_run(self.ctx.run_dir, self.ctx.z0_home, self.ctx.home, out=lambda *_: None)
        self.assertEqual(os.readlink(self.ctx.expand("~/.local/lib/demo/demo-current")), str(old))
        self.assertTrue(old.is_dir())


def _tar(entries: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in entries.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class PinnedToolchain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ctx_with(self, archive: bytes, sha: str):
        path = self.root / "dist" / "tool.tar.gz"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(archive)
        spec = {"version": "1.0.0", "url": path.as_uri(), "layout": "tool-{target}/bin/tool",
                "targets": {f"{os.uname().sysname.lower()}-{os.uname().machine}": {"target": "t", "sha256": sha},
                            "linux-x86_64": {"target": "t", "sha256": sha},
                            "linux-arm64": {"target": "t", "sha256": sha}}}
        snap = {"components": {"components": {}}, "toolchains": {"tools": {"tool": {"install": spec}}}}
        host = {"os": {"os": "linux", "arch": "x86_64" if os.uname().machine == "x86_64" else "arm64"}}
        step = {"id": "toolchain.tool", "component": "z0", "kind": "ensure_toolchain",
                "consent": {"class": "C1", "bundle": "toolchains"}, "toolchain": {"tool": "tool", "version": "1.0.0"}}
        return ctx_for(self.root, [step], snap=snap, host=host), step

    def test_installs_user_local_and_puts_it_on_the_path(self):
        from z0.onboard.actions import ensure_toolchain
        data = _tar({"tool-t/bin/tool": "#!/bin/sh\necho 1.0.0\n"})
        ctx, step = self.ctx_with(data, hashlib.sha256(data).hexdigest())
        ensure_toolchain.execute(ctx, step)
        binary = Path(ctx.expand("$Z0_HOME/toolchains/tool/1.0.0/bin/tool"))
        self.assertTrue(os.access(binary, os.X_OK))
        self.assertIn(str(binary.parent), ctx.path_dirs())
        self.assertIn({"kind": "dir", "path": "$Z0_HOME/toolchains/tool/1.0.0", "marker": ctx.run_id},
                      effects(ctx))

    def test_sha256_mismatch_installs_nothing(self):
        from z0.onboard.actions import ActionError, ensure_toolchain
        data = _tar({"tool-t/bin/tool": "#!/bin/sh\n"})
        ctx, step = self.ctx_with(data, "0" * 64)
        with self.assertRaises(ActionError) as caught:
            ensure_toolchain.execute(ctx, step)
        self.assertIn("sha256 mismatch", str(caught.exception))
        self.assertEqual(os.listdir(ctx.expand("$Z0_HOME/toolchains/tool")), [])

    def test_archive_escape_is_refused(self):
        from z0.onboard.actions import ActionError, ensure_toolchain
        data = _tar({"../../evil": "x", "tool-t/bin/tool": "#!/bin/sh\n"})
        ctx, step = self.ctx_with(data, hashlib.sha256(data).hexdigest())
        with self.assertRaises(ActionError):
            ensure_toolchain.execute(ctx, step)
        self.assertFalse(any(p.name == "evil" for p in self.root.rglob("evil")))
        self.assertFalse(os.path.exists(ctx.expand("$Z0_HOME/toolchains/tool/1.0.0")))

    def test_system_tool_is_never_installed(self):
        from z0.onboard.actions import ActionError, ensure_toolchain
        ctx, _ = self.ctx_with(b"", "0" * 64)
        step = {"id": "toolchain.ffmpeg-x", "component": "z0", "kind": "ensure_toolchain",
                "consent": {"class": "C0"}, "toolchain": {"tool": "no-such-tool-z0", "version": "system"}}
        with self.assertRaises(ActionError) as caught:
            ensure_toolchain.execute(ctx, step)
        self.assertIn("C2", str(caught.exception))


class WriteFileAndRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_file_backs_up_and_rollback_restores(self):
        from z0.onboard.actions import write_file
        from z0.onboard.rollback import rollback_run
        step = {"id": "demo.env", "component": "demo", "kind": "write_file",
                "consent": {"class": "C1", "bundle": "services"}, "where": "home",
                "creates": ["~/.config/demo/demo.env"]}
        ctx = ctx_for(self.root, [step])
        target = Path(ctx.expand(step["creates"][0]))
        target.parent.mkdir(parents=True)
        target.write_text("OLD=1\n")
        os.chmod(target, 0o640)
        write_file.RENDERERS["demo.env"] = lambda c, s: (b"NEW=1\n", 0o600)
        try:
            write_file.execute(ctx, step)
        finally:
            del write_file.RENDERERS["demo.env"]
        self.assertEqual(target.read_text(), "NEW=1\n")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
        self.assertEqual(effects(ctx)[0]["kind"], "replace")
        rollback_run(ctx.run_dir, ctx.z0_home, ctx.home, out=lambda *_: None)
        self.assertEqual(target.read_text(), "OLD=1\n")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o640)

    def test_write_file_without_a_renderer_writes_nothing(self):
        from z0.onboard.actions import ActionError, write_file
        step = {"id": "z0intelligence.shim", "component": "z0intelligence", "kind": "write_file",
                "consent": {"class": "C1", "bundle": "services"}, "where": "home",
                "creates": ["~/.z0int/bin/python"]}
        ctx = ctx_for(self.root, [step])
        with self.assertRaises(ActionError):
            write_file.execute(ctx, step)
        self.assertFalse(os.path.exists(ctx.expand("~/.z0int")))

    def test_z0_never_writes_its_own_files_into_an_adopted_checkout(self):
        from z0.onboard.actions import ActionError
        tree = self.root / "home" / "workspace" / "demo"
        tree.mkdir(parents=True)
        ctx = ctx_for(self.root, [], components={"demo": {"tree": "~/workspace/demo", "adopted": True}})
        with self.assertRaises(ActionError):
            ctx.write_file(str(tree / "x.env"), b"x", 0o600)

    def test_run_needs_creates_or_probe_and_must_create(self):
        from z0.onboard.actions import ActionError, run
        tree = self.root / "home" / ".z0" / "repos" / "demo"
        tree.mkdir(parents=True)
        components = {"demo": {"tree": "$Z0_HOME/repos/demo", "adopted": False}}
        bare = {"id": "demo.x", "component": "demo", "kind": "run", "consent": {"class": "C0"},
                "where": "build", "argv": ["true"]}
        ctx = ctx_for(self.root, [bare], components=components)
        with self.assertRaises(ActionError) as caught:
            run.execute(ctx, bare)
        self.assertIn("refused", str(caught.exception))
        liar = dict(bare, id="demo.y", creates=["$Z0_HOME/repos/demo/out.txt"])
        with self.assertRaises(ActionError) as caught:
            run.execute(ctx, liar)
        self.assertIn("did not create", str(caught.exception))
        honest = dict(bare, id="demo.z", argv=["sh", "-c", "echo hi > out.txt"],
                      creates=["$Z0_HOME/repos/demo/out.txt"])
        run.execute(ctx, honest)
        self.assertEqual(effects(ctx)[-1]["path"], "$Z0_HOME/repos/demo/out.txt")

    def test_run_env_is_an_allowlist(self):
        from z0.onboard.actions import run
        tree = self.root / "home" / ".z0" / "repos" / "demo"
        tree.mkdir(parents=True)
        ctx = ctx_for(self.root, [], components={"demo": {"tree": "$Z0_HOME/repos/demo"}})
        ctx.base_env.update(CEREBRAS_API_KEY="z0-canary-7f3a9c1e5b", PIP_BREAK_SYSTEM_PACKAGES="1")
        step = {"id": "demo.env", "component": "demo", "kind": "run", "consent": {"class": "C0"},
                "where": "build", "argv": ["sh", "-c", "env > env.txt"],
                "creates": ["$Z0_HOME/repos/demo/env.txt"]}
        run.execute(ctx, step)
        text = (tree / "env.txt").read_text()
        self.assertNotIn("CEREBRAS_API_KEY", text)
        self.assertNotIn("PIP_BREAK_SYSTEM_PACKAGES", text)
        self.assertIn("PIP_NO_INPUT=1", text)
        self.assertIn("LANG=C.UTF-8", text)


class HttpCheck(unittest.TestCase):
    def test_loopback_status_and_no_tailnet(self):
        from z0.onboard.actions import ActionError, check

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(401)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ctx = ctx_for(Path(tmp), [])
                port = server.server_address[1]
                ok = {"id": "x.health", "component": "x", "kind": "check", "consent": {"class": "C0"},
                      "verify": {"http": {"bind": "loopback", "port": port, "path": "/", "expect_status": 401}}}
                self.assertTrue(check.execute(ctx, ok).ok)
                wrong = {**ok, "verify": {"http": {**ok["verify"]["http"], "expect_status": 200}}}
                with self.assertRaises(ActionError):
                    check.execute(ctx, wrong)
                tailnet = {**ok, "verify": {"http": {**ok["verify"]["http"], "bind": "tailnet_ipv4"}}}
                with self.assertRaises(ActionError) as caught:
                    check.execute(ctx, tailnet)
                self.assertIn("current detection", str(caught.exception))
        finally:
            server.shutdown()
            server.server_close()


@require_yaml
class RegistryKindsHaveActions(unittest.TestCase):
    def test_every_effectful_kind_in_the_registry_has_an_action_or_a_named_package(self):
        from z0.onboard.actions import ACTIONS, LATER
        kinds = {s["kind"] for c in snapshot()["components"]["components"].values()
                 for s in (c.get("onboard") or {}).get("steps") or []}
        self.assertEqual(sorted(k for k in kinds if k not in ACTIONS and k not in LATER and k != "ask"), [])


if __name__ == "__main__":
    unittest.main()
