"""Work packages Z3/Z4 actions on temp dirs with fakes (design §8.3, §8.4, §10 layer 2).

- write_file renderers: the z0int shim points into the runtime venv (never a checkout),
  hermes.json names the shim, the dash env binds the current tailnet IPv4 only and its
  PATH never reaches a `configure: never` harness dir (P1);
- harness_plugin: refuses grok/cursor (P1) and absent harnesses; for Claude Code adds the
  release as a marketplace, installs, and stamps; the fake harness logs its argv;
- service_unit: refuses an open bind (S2), never replaces an existing unit (S3), writes a
  unit from the template, enables it, and defers the start until its release swap;
- check `verify.serve`: a loopback self-test answers, is stopped, and its tokens are
  redacted from the log and its disposable dir removed.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import textwrap
import unittest

from tests.onboard.test_actions import ctx_for, effects


def fake_bin(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


class Renderers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _z0int_ctx(self):
        steps = [
            {"id": "z0intelligence.runtime", "component": "z0intelligence", "kind": "venv",
             "consent": {"class": "C0"}, "where": "venv", "creates": ["~/.local/lib/z0int-runtime/abc"]},
            {"id": "z0intelligence.install", "component": "z0intelligence", "kind": "pip_install",
             "consent": {"class": "C0"}, "where": "venv", "needs": ["z0intelligence.runtime"]},
            {"id": "z0intelligence.shim", "component": "z0intelligence", "kind": "write_file",
             "consent": {"class": "C1", "bundle": "services"}, "where": "home",
             "needs": ["z0intelligence.install"], "creates": ["~/.z0int/bin/python"]},
            {"id": "z0intelligence.hermes_json", "component": "z0intelligence", "kind": "write_file",
             "consent": {"class": "C1", "bundle": "services"}, "where": "home",
             "needs": ["z0intelligence.shim"], "creates": ["~/.z0int/config/hermes.json"]},
        ]
        ctx = ctx_for(self.root, steps)
        venv = Path(ctx.expand("~/.local/lib/z0int-runtime/abc"))
        (venv / "bin").mkdir(parents=True)
        os.symlink(sys.executable, venv / "bin" / "python")
        return ctx, steps

    def test_shim_points_into_runtime_venv_and_hermes_json_names_it(self):
        from z0.onboard.actions import ACTIONS
        ctx, steps = self._z0int_ctx()
        for step in steps[2:]:
            ctx.step_id = step["id"]
            ACTIONS["write_file"](ctx, step)
        shim = Path(ctx.expand("~/.z0int/bin/python"))
        self.assertTrue(os.access(shim, os.X_OK))
        self.assertIn(ctx.expand("~/.local/lib/z0int-runtime/abc/bin/python"), shim.read_text())
        import json
        self.assertEqual(json.loads(Path(ctx.expand("~/.z0int/config/hermes.json")).read_text())["python"],
                         str(shim))
        self.assertEqual(stat.S_IMODE(os.stat(ctx.expand("~/.z0int/config/hermes.json")).st_mode), 0o600)
        kinds = [e["kind"] for e in effects(ctx)]
        self.assertIn("file", kinds)

    def test_shim_refuses_without_runtime(self):
        from z0.onboard.actions import ACTIONS, ActionError
        ctx, steps = self._z0int_ctx()
        os.unlink(ctx.expand("~/.local/lib/z0int-runtime/abc/bin/python"))
        ctx.step_id = "z0intelligence.shim"
        with self.assertRaises(ActionError):
            ACTIONS["write_file"](ctx, steps[2])
        self.assertFalse(os.path.exists(ctx.expand("~/.z0int/bin/python")))

    def test_dash_env_binds_tailnet_only_and_path_excludes_never_harness_dir(self):
        from z0.onboard.actions import ACTIONS, ActionError
        step = {"id": "dash.bridge.env", "component": "dash", "kind": "write_file",
                "consent": {"class": "C1", "bundle": "services"}, "where": "home",
                "creates": ["~/.config/dash-services/bridge.env"]}
        bun_dir = self.root / "toolchains" / "bun"
        fake_bin(bun_dir, "bun", "exit 0\n")
        shared = self.root / "shared-bin"
        fake_bin(shared, "grok", "exit 0\n")
        ctx = ctx_for(self.root, [step], host={"tailscale": {"ipv4": "198.51.100.7"},
                                               "harnesses": {"grok": {"state": "installed",
                                                                      "path": str(shared / "grok")}}})
        ctx.plan["prepared_path"] = ["$Z0_HOME/bin/links", "/usr/bin", "/bin"]
        ctx.extra_path = [str(bun_dir)]
        ctx.step_id = step["id"]
        ACTIONS["write_file"](ctx, step)
        text = Path(ctx.expand(step["creates"][0])).read_text()
        self.assertIn("DASH_HOST=198.51.100.7\n", text)
        self.assertNotIn(str(shared), text)
        self.assertTrue(text.split("PATH=", 1)[1].startswith(str(bun_dir)))
        self.assertNotIn("APPROVAL", text)
        # no tailnet: nothing is written
        ctx2 = ctx_for(self.root / "b", [step], host={})
        ctx2.extra_path = [str(bun_dir)]
        ctx2.step_id = step["id"]
        with self.assertRaises(ActionError):
            ACTIONS["write_file"](ctx2, step)


class HarnessPlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = self.root / "argv.log"
        self.bins = self.root / "bins"
        for name in ("claude", "codex", "grok"):
            fake_bin(self.bins, name, f'echo "{name} $*" >> "{self.log}"\nexit 0\n')
        self.release = self.root / "home" / ".local" / "lib" / "z0int-shadow" / "abc"
        (self.release / ".claude-plugin").mkdir(parents=True)
        (self.release / ".claude-plugin" / "marketplace.json").write_text("{}")
        self.snap = {"components": {"components": {}},
                     "harnesses": {"harnesses": {"claude-code": {"policy": {"configure": "auto"}},
                                                 "grok": {"policy": {"configure": "never"}}}}}

    def tearDown(self):
        self.tmp.cleanup()

    def _ctx(self, harness, state="installed"):
        steps = [
            {"id": "z0intelligence.release", "component": "z0intelligence", "kind": "stage_release",
             "consent": {"class": "C0"}, "where": "release", "creates": ["~/.local/lib/z0int-shadow/abc"]},
            {"id": f"z0intelligence.plugin.{harness}", "component": "z0intelligence", "kind": "harness_plugin",
             "harness": harness, "consent": {"class": "C1", "bundle": "harness"}, "where": "release",
             "needs": ["z0intelligence.release"],
             "argv": ["claude" if harness != "grok" else "grok", "plugin", "install", "z0intelligence@z0intelligence"]},
        ]
        host = {"harnesses": {harness: {"state": state, "path": str(self.bins / ("claude" if harness != "grok"
                                                                                 else "grok"))}}}
        ctx = ctx_for(self.root, steps, snap=self.snap, host=host)
        return ctx, steps[1]

    def test_claude_marketplace_then_install_then_stamp(self):
        from z0.onboard.actions import ACTIONS
        ctx, step = self._ctx("claude-code")
        ctx.step_id = step["id"]
        outcome = ACTIONS["harness_plugin"](ctx, step)
        self.assertTrue(outcome.ok)
        lines = self.log.read_text().splitlines()
        self.assertEqual(lines[0], f"claude plugin marketplace add {self.release}")
        self.assertEqual(lines[1], "claude plugin install z0intelligence@z0intelligence")
        self.assertTrue(os.path.isfile(ctx.expand("$Z0_HOME/onboard/stamps/" + step["id"])))

    def test_P1_never_harness_refused(self):
        from z0.onboard.actions import ACTIONS, ActionError
        ctx, step = self._ctx("grok")
        ctx.step_id = step["id"]
        with self.assertRaises(ActionError):
            ACTIONS["harness_plugin"](ctx, step)
        self.assertFalse(self.log.exists())

    def test_absent_harness_refused(self):
        from z0.onboard.actions import ACTIONS, ActionError
        ctx, step = self._ctx("claude-code", state="absent")
        ctx.step_id = step["id"]
        with self.assertRaises(ActionError):
            ACTIONS["harness_plugin"](ctx, step)


class ServiceUnit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = self.root / "systemctl.log"
        self.bins = self.root / "bins"
        fake_bin(self.bins, "systemctl", f'echo "$*" >> "{self.log}"\nexit 0\n')
        fake_bin(self.bins, "bun", "exit 0\n")
        os.symlink(sys.executable, self.bins / "python3")

    def tearDown(self):
        self.tmp.cleanup()

    def _ctx(self, bind="tailnet_ipv4"):
        step = {"id": "dash.bridge.unit", "component": "dash", "kind": "service_unit",
                "consent": {"class": "C1", "bundle": "services"}, "where": "release",
                "service": {"template": "dash-bridge", "unit": "dash-bridge.service", "bind": bind,
                            "port": 4747, "limits": {"memory_max": "1G", "restart_sec": 10,
                                                     "timeout_start_sec": 120}}}
        ctx = ctx_for(self.root, [step])
        ctx.plan["prepared_path"] = [str(self.bins), "/usr/bin", "/bin"]
        ctx.step_id = step["id"]
        return ctx, step

    def test_writes_enables_and_defers_start_until_swap(self):
        from z0.onboard.actions import ACTIONS
        ctx, step = self._ctx()
        outcome = ACTIONS["service_unit"](ctx, step)
        unit = Path(ctx.expand("~/.config/systemd/user/dash-bridge.service")).read_text()
        self.assertIn(f"ExecStart={self.bins}/bun run index.ts", unit)
        self.assertIn("MemoryMax=1G", unit)
        self.assertIn("RestartSec=10", unit)
        self.assertNotIn("{", unit)
        self.assertEqual(self.log.read_text().splitlines(), ["--user daemon-reload",
                                                             "--user enable dash-bridge.service"])
        self.assertIn("starts after its release swap", outcome.detail)

    def test_S2_open_bind_refused(self):
        from z0.onboard.actions import ACTIONS, ActionError
        ctx, step = self._ctx(bind="any")
        with self.assertRaises(ActionError):
            ACTIONS["service_unit"](ctx, step)

    def test_S3_existing_unit_never_replaced(self):
        from z0.onboard.actions import ACTIONS, ActionError
        ctx, step = self._ctx()
        path = Path(ctx.expand("~/.config/systemd/user/dash-bridge.service"))
        path.parent.mkdir(parents=True)
        path.write_text("# the owner's unit\n")
        with self.assertRaises(ActionError):
            ACTIONS["service_unit"](ctx, step)
        self.assertEqual(path.read_text(), "# the owner's unit\n")


class ServeSelfTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_serve_answers_then_is_stopped_and_token_redacted(self):
        from z0.onboard.actions import ACTIONS
        server = self.root / "srv" / "server.py"
        server.parent.mkdir()
        server.write_text(textwrap.dedent("""
            import http.server, os, sys
            cred = os.environ["CRED_DIR"]; os.makedirs(cred, exist_ok=True)
            token = "tok_" + "A1b2C3d4E5f6G7h8I9j0"
            open(os.path.join(cred, "token"), "w").write(token)
            print("pair with", token, flush=True)
            class H(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(401); self.end_headers()
                def log_message(self, *a): pass
            http.server.HTTPServer(("127.0.0.1", int(os.environ["PORT"])), H).serve_forever()
        """))
        step = {"id": "demo.selftest", "component": "demo", "kind": "check", "consent": {"class": "C0"},
                "verify": {"serve": {"argv": [sys.executable, str(server)], "path": "/", "expect_status": 401,
                                     "timeout_s": 30, "env": {"PORT": "@port@", "CRED_DIR": "@tmp@/cred"}}}}
        ctx = ctx_for(self.root, [step])
        ctx.repo_root = str(server.parent)
        ctx.step_id = step["id"]
        outcome = ACTIONS["check"](ctx, step)
        self.assertTrue(outcome.ok)
        self.assertIn("401", outcome.detail)
        log = (ctx.run_dir / "logs" / "demo.selftest.log").read_text()
        self.assertNotIn("A1b2C3d4E5f6G7h8I9j0", log)
        self.assertFalse((ctx.run_dir / "serve" / "demo.selftest").exists())


if __name__ == "__main__":
    unittest.main()
