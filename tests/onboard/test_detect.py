"""DETECT on a fake host (§4): read-only, never raises, never opens denylisted paths,
never prints a secret, never executes grok or an unknown binary, and T1 (the
prepared PATH resolves every tool under `sh -c`)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.onboard import fakehost, support
from tests.onboard.support import require_yaml

_AUDIT = {"on": False, "opens": [], "execs": []}


def _hook(event, args):
    if _AUDIT["on"] and event == "open" and args and isinstance(args[0], (str, bytes)):
        _AUDIT["opens"].append((str(args[0]), args[1] if len(args) > 1 else "r"))
    if _AUDIT["on"] and event == "subprocess.Popen" and args:
        _AUDIT["execs"].append(str(args[0]))


sys.addaudithook(_hook)


@require_yaml
class DetectFakeHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from z0.onboard.detect import Ctx, detect
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fake = fakehost.build(Path(cls.tmp.name))
        cls.Ctx, cls.detect_fn = Ctx, staticmethod(detect)
        before = fakehost.tree_state(cls.fake["home"])
        _AUDIT["opens"].clear()
        _AUDIT["execs"].clear()
        _AUDIT["on"] = True
        try:
            cls.host = detect(cls.ctx())
        finally:
            _AUDIT["on"] = False
        cls.opens = list(_AUDIT["opens"])
        cls.execs = list(_AUDIT["execs"])
        cls.after_diff = (before, fakehost.tree_state(cls.fake["home"]))
        cls.text = json.dumps(cls.host, sort_keys=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def ctx(cls, **kw):
        fake = cls.fake
        args = dict(registry=support.snapshot(), env=dict(fake["env"]), sysroot=str(fake["sysroot"]),
                    system_dirs=[str(fake["sysbin"])], uname=("Linux", "x86_64"),
                    hostname="fakehost", now="2026-10-25T00:00:00Z",
                    http_head=lambda url, timeout: "fonts" not in url)
        args.update(kw)
        return cls.Ctx(**args)

    def test_facts(self):
        host = self.host
        self.assertEqual(host["os"]["distro"], "arch")
        self.assertEqual(host["os"]["libc"], "glibc")
        self.assertEqual(host["os"]["pkg_manager"], "pacman")
        self.assertEqual(host["hardware"]["ram_gib"], 15.5)
        self.assertEqual(host["hardware"]["cpu"], {"logical": 8, "physical": 4})
        self.assertEqual(host["hardware"]["gpu"], {"class": "amd", "rocm": False})
        self.assertEqual(host["session"]["desktop"], "wayland")
        self.assertTrue(host["session"]["systemd_user"])
        self.assertFalse(host["session"]["audio_in"])
        self.assertEqual(host["network"]["fonts_google"], False)
        self.assertEqual(host["network"]["github"], True)
        self.assertEqual(host["tailscale"]["ipv4"], "100.64.0.7")
        self.assertEqual(len(host["host_id"]), 16)

    def test_harnesses_and_policy(self):
        harnesses = self.host["harnesses"]
        self.assertEqual(harnesses["claude-code"]["state"], "installed")
        self.assertEqual(harnesses["claude-code"]["version"], "2.1.0")
        self.assertTrue(harnesses["claude-code"]["sessions_present"])
        self.assertEqual(harnesses["grok"]["state"], "installed")
        self.assertTrue(harnesses["grok"]["policy_excluded"])
        self.assertNotIn("version", harnesses["grok"])
        self.assertEqual(harnesses["hermes"]["state"], "config_only")
        self.assertEqual(harnesses["opencode"]["state"], "absent")

    def test_P1_grok_and_unknown_binaries_never_execute(self):
        root = self.fake["root"]
        self.assertFalse((root / "grok-was-executed").exists())
        self.assertFalse((root / "unknown-was-executed").exists())
        calls = (root / "calls.log").read_text().split("\n")
        self.assertFalse([c for c in calls if c.startswith("grok") or c.startswith("mystery-tool")])
        unknown = [u for u in self.host["unknowns"] if u["id"] == "bin.mystery-tool"]
        self.assertEqual(unknown[0]["kind"], "harness_classify")
        self.assertEqual(unknown[0]["facts"]["shebang"], "#!/bin/sh")
        self.assertEqual(unknown[0]["safe_default"], "unsupported")

    def test_T1_prepared_path_resolves_tools_off_the_user_path(self):
        tools = self.host["toolchains"]
        self.assertEqual(tools["bun"]["path"], "~/.bun/bin/bun")
        self.assertEqual(tools["bun"]["version"], "1.4.3")
        self.assertTrue(tools["bun"]["sh_resolves"])
        self.assertIn("~/.bun/bin", self.host["prepared_path"])
        self.assertEqual(self.host["prepared_path"][-1], str(self.fake["sysbin"]))
        prepared = ":".join(p.replace("~", str(self.fake["home"]), 1) for p in self.host["prepared_path"])
        out = subprocess.run(["/bin/sh", "-c", "command -v bun && command -v claude && command -v git"],
                             env={"PATH": prepared}, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.split()[0], str(self.fake["home"] / ".bun/bin/bun"))

    def test_T1_red_a_tool_outside_the_prepared_path_does_not_resolve(self):
        prepared = ":".join(p.replace("~", str(self.fake["home"]), 1) for p in self.host["prepared_path"]
                            if p != "~/.bun/bin")
        out = subprocess.run(["/bin/sh", "-c", "command -v bun"], env={"PATH": prepared},
                             capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)

    def test_sealed_every_probe_and_path_stays_in_the_fake_host(self):
        """No real host binary runs and no real host dir is reported: the registry's
        absolute well-known dirs (/usr/local/bin, /opt/homebrew/bin) are read under the
        fake sysroot, so a real brew tailscale or npm-global claude is never seen."""
        root = str(self.fake["root"])
        self.assertTrue(self.execs, "audit hook saw no subprocess")
        for exe in self.execs:
            self.assertTrue(exe.startswith(root + "/"), f"ran a binary outside the fake host: {exe}")
        for tool, entry in self.host["toolchains"].items():
            if entry.get("path"):
                self.assertTrue(entry["path"].startswith("~/") or entry["path"].startswith(root + "/"),
                                f"{tool}: {entry['path']}")
        for directory in self.host["prepared_path"]:
            self.assertTrue(directory.startswith("~/") or directory.startswith(root + "/"), directory)
        rustup = self.host["toolchains"]["rustup"]
        self.assertEqual(rustup["path"], str(self.fake["sysroot"] / "usr/local/bin/rustup"))
        self.assertEqual(rustup["source"], "well_known_dir")

    def test_sealed_expand_maps_absolute_paths_into_the_sysroot(self):
        ctx = self.ctx()
        sysroot = str(self.fake["sysroot"])
        self.assertEqual(ctx.expand("/opt/homebrew/bin"), sysroot + "/opt/homebrew/bin")
        self.assertEqual(ctx.expand("~/.bun/bin"), str(self.fake["home"] / ".bun/bin"))
        self.assertEqual(ctx.expand(sysroot + "/proc/meminfo"), sysroot + "/proc/meminfo")
        self.assertEqual(self.Ctx(registry={}, sysroot="/", env={"HOME": "/h"}).expand("/opt/x"), "/opt/x")

    def test_P1_policy_excluded_binary_records_its_dir(self):
        harnesses = self.host["harnesses"]
        self.assertEqual(harnesses["grok"]["bin_dir"], "~/.local/bin")
        self.assertNotIn("path", harnesses["grok"])
        self.assertEqual(harnesses["claude-code"]["path"], "~/.local/bin/claude")

    def test_checkouts_only_registry_repos(self):
        paths = [c["path"] for c in self.host["checkouts"]]
        self.assertEqual(paths, ["~/workspace/z0evals"])
        self.assertEqual(self.host["checkouts"][0]["dirty"], 0)
        self.assertNotIn("private-thing", self.text)

    def test_services(self):
        units = self.host["services"]["units"]
        self.assertEqual([u["name"] for u in units], ["dash-bridge.service"])
        self.assertEqual(units[0]["exec_root_kind"], "release")
        self.assertEqual(units[0]["deployed_sha"], "5f3ee27f6e431ba83abfe9a4a94b2c0757910ddb")
        self.assertEqual(self.host["services"]["port_owners"], {"4747": "bun"})

    def test_secrets_by_name_only(self):
        secrets = self.host["secrets"]
        self.assertEqual(secrets["CEREBRAS_API_KEY"], {"present": True})
        self.assertEqual(secrets["dash_token"], {"present": True, "mode_ok": True})
        self.assertNotIn(fakehost.CANARY, self.text)
        self.assertNotIn("secret-peer", self.text)

    def test_home_written_as_tilde(self):
        self.assertNotIn(str(self.fake["home"]), self.text)

    def test_read_only_and_denylist_never_opened(self):
        before, after = self.after_diff
        self.assertEqual(before, after, "detect changed files under HOME")
        self.assertTrue(any(p.endswith("proc/meminfo") for p, _ in self.opens), "audit hook is live")
        writes = [(p, m) for p, m in self.opens if isinstance(m, str) and any(c in m for c in "wax+")]
        self.assertEqual(writes, [])
        home = str(self.fake["home"])
        denied = [p for p, _ in self.opens if p.startswith(home) and any(
            part in p for part in ("/.hermes/", "/.ssh/", "/.dash/token", "/.z0int/shadow",
                                   ".credentials", "/.codex/auth"))]
        self.assertEqual(denied, [])
        calls = (self.fake["root"] / "calls.log").read_text()
        self.assertNotIn("git status", calls)  # git runs from the real binary, not a stub
        self.assertIn("tailscale status --json", calls)

    def test_schema_valid(self):
        validator = support.validator("host-profile")
        if validator is None:
            self.skipTest("jsonschema not installed (optional)")
        self.assertEqual([e.message for e in validator.iter_errors(self.host)], [])

    def test_never_raises(self):
        def boom(*args, **kwargs):
            raise RuntimeError("probe exploded")

        host = self.detect_fn(self.ctx(runner=boom, http_head=boom))
        self.assertEqual(host["version"], 1)
        self.assertEqual(host["toolchains"]["bun"]["state"], "present")
        self.assertNotIn("version", host["toolchains"]["bun"])
        self.assertFalse(any(host["network"].values()))

    def test_a_crashing_detector_becomes_a_warning(self):
        from z0.onboard.detect import hardware
        original = hardware.detect
        hardware.detect = lambda *a, **k: (_ for _ in ()).throw(ValueError("x"))
        try:
            host = self.detect_fn(self.ctx())
        finally:
            hardware.detect = original
        self.assertIn("detector hardware failed: ValueError", host["warnings"])
        self.assertEqual(host["hardware"]["gpu"], {"class": "cpu"})


if __name__ == "__main__":
    unittest.main()
