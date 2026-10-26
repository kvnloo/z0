"""registry-check onboarding rules (§2.7) with one red case per rule, and the H2 host
literal scan over everything Z1 renders or ships (registry, fixtures, goldens, matrix)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest

from tests.onboard import support
from tests.onboard.support import EXPECTED, FIXTURES, ROOT, require_yaml


@require_yaml
class RegistryRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from z0.onboard import regcheck
        cls.rc = regcheck
        cls.raw, cls.templates = regcheck.load_texts(ROOT)

    def errors(self, snap=None, raw=None):
        return self.rc.check(snap or support.snapshot(), raw or self.raw, self.templates)

    def steps(self, snap, cid):
        return snap["components"]["components"][cid]["onboard"]["steps"]

    def step(self, snap, sid):
        cid = sid.split(".", 1)[0]
        return next(s for s in self.steps(snap, cid) if s["id"] == sid)

    def assert_red(self, snap, needle, raw=None):
        found = [e for e in self.errors(snap, raw) if needle in e]
        self.assertTrue(found, f"expected an error containing {needle!r}")

    def test_green_registry(self):
        self.assertEqual(self.errors(), [])

    def test_script_passes(self):
        out = subprocess.run([str(ROOT / "scripts/registry-check")], capture_output=True, text=True,
                             env={"PATH": f"{sys.executable.rsplit('/', 1)[0]}:/usr/bin:/bin"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(out.stdout.startswith("ok: "))

    def test_red_R_sync_drift(self):
        snap = support.snapshot()
        snap["components"]["components"]["tokenomics"]["install"]["command"] = "pip install tokenomics"
        self.assert_red(snap, "R-sync install.command")
        snap = support.snapshot()
        self.step(snap, "z0evals.t1.validate")["argv"] = ["python3", "scripts/validate.py"]
        self.assert_red(snap, "R-sync verify.command")

    def test_red_run_without_creates_or_probe_or_where(self):
        snap = support.snapshot()
        step = self.step(snap, "oh-my-pi.install")
        del step["creates"]
        self.assert_red(snap, "run needs creates or probe")
        snap = support.snapshot()
        del self.step(snap, "oh-my-pi.install")["where"]
        self.assert_red(snap, "run needs argv and where")

    def test_red_configure_never_harness(self):
        snap = support.snapshot()
        self.step(snap, "z0intelligence.plugin.claude")["harness"] = "grok"
        self.assert_red(snap, "configure: never")
        snap = support.snapshot()
        snap["harnesses"]["harnesses"]["cursor-agent"]["policy"]["offload"] = "allowed"
        self.assert_red(snap, "cursor-agent: configure/offload/exec_probe must be never")

    def test_red_open_bind_and_checkout_where(self):
        snap = support.snapshot()
        self.step(snap, "dash.bridge.unit")["service"]["bind"] = "0.0.0.0"
        self.assert_red(snap, "is not closed (S2)")
        snap = support.snapshot()
        self.step(snap, "dash.bridge.unit")["where"] = "build"
        self.assert_red(snap, "(S1)")
        snap = support.snapshot()
        self.step(snap, "z0evals.venv")["where"] = "checkout"
        self.assert_red(snap, "where 'checkout'")

    # Host literals are built at runtime so this public file names no real host either.
    MOUNT = "/m" + "nt/models-x"
    TAILNET_ID = "tail" + "c0ffee42"
    TAILNET_IP = "100." + "101.2.3"

    def test_red_harness_plugin_or_target_outside_releases(self):
        """S1 covers plugin paths and the shim/env-file targets, not only units."""
        snap = support.snapshot()
        self.step(snap, "oh-my-pi.setup")["where"] = "build"
        self.assert_red(snap, "harness plugin links a release or an owned venv")
        snap = support.snapshot()
        self.step(snap, "z0intelligence.shim")["target_where"] = "home"
        self.assert_red(snap, "target_where is for write_file")
        snap = support.snapshot()
        self.step(snap, "z0intelligence.verify")["target_where"] = "venv"
        self.assert_red(snap, "target_where is for write_file")

    def test_red_unknown_when_fact(self):
        snap = support.snapshot()
        self.step(snap, "z0evals.web.gate")["when"] = [
            {"fact": "network.npm_registry", "op": "eq", "value": True}]
        self.assert_red(snap, "network has no key 'npm_registry'")
        snap = support.snapshot()
        self.step(snap, "dash.gate.test")["when"] = [
            {"fact": "toolchains.ffmpeg.status", "op": "eq", "value": "present"}]
        self.assert_red(snap, "toolchains.ffmpeg has no field 'status'")
        snap = support.snapshot()
        self.step(snap, "flow.source")["when"] = [{"fact": "sesion.desktop", "op": "ne", "value": "none"}]
        self.assert_red(snap, "unknown fact root 'sesion'")

    def test_repo_setup_block(self):
        """§2.6: a repo step that repeats a registry step under another id would be
        planned twice; a misspelt `when` fact silently disables its tier."""
        snap = support.snapshot()
        good = {"steps": [
            {"id": "z0evals.t1.validate", "kind": "check", "consent": {"class": "C0"},
             "where": "build", "argv": [".venv/bin/python", "scripts/validate.py"]}],
            "tiers": [{"id": "web", "when": [{"fact": "network.npmjs", "op": "eq", "value": True}]}]}
        self.assertEqual(self.rc.check_repo_setup(snap, "z0evals", good), [])
        bad = json.loads(json.dumps(good))
        bad["steps"][0]["id"] = "z0evals.validate"
        bad["tiers"][0]["when"][0]["fact"] = "network.npm_registry"
        errors = self.rc.check_repo_setup(snap, "z0evals", bad)
        self.assertTrue([e for e in errors if "same argv as registry step z0evals.t1.validate" in e])
        self.assertTrue([e for e in errors if "npm_registry" in e])

    def test_red_denylisted_literal(self):
        for text, needle in ((f"# deploy to {self.MOUNT}/x", "/mnt/"),
                             (f"# host host-a.{self.TAILNET_ID}.ts.net", "tail[0-9a-f]"),
                             (f"# bind {self.TAILNET_IP}", "(6[4-9]|"),
                             ("# under /home/someone/x", "(home|Users)"),
                             ("# /workspace/app-home", "'/workspace/'")):
            with self.subTest(text=text):
                raw = dict(self.raw)
                raw["registry/components.yaml"] += f"\n{text}\n"
                self.assert_red(None, needle, raw)

    def test_tilde_workspace_is_not_the_workspace_literal(self):
        deny = support.snapshot()["onboarding"]["denylists"]["redaction"]
        self.assertEqual(self.rc.scan_literals("~/workspace/z0evals", deny), [])
        self.assertEqual(self.rc.scan_literals("$Z0_HOME/repos/x ~/.local/lib/dash", deny), [])
        self.assertTrue(self.rc.scan_literals("/workspace/app-home", deny))
        self.assertTrue(self.rc.scan_literals("x /home/someone/y", deny))
        self.assertTrue(self.rc.scan_literals(self.MOUNT, deny))

    def test_red_auto_target_without_acceptance(self):
        snap = support.snapshot()
        del snap["components"]["components"]["z0evals"]["onboard"]["acceptance"]
        self.assert_red(snap, "z0evals: in the auto target set but has no acceptance")

    def test_red_forbidden_provider_policy(self):
        snap = support.snapshot()
        snap["onboarding"]["llm"]["forbidden"] = ["grok"]
        self.assert_red(snap, "must name grok and cursor")
        snap = support.snapshot()
        snap["onboarding"]["bind_classes"].append("lan")
        self.assert_red(snap, "bind_classes")

    def test_red_unpinned_toolchain(self):
        snap = support.snapshot()
        snap["toolchains"]["tools"]["bun"]["install"]["targets"]["linux-x86_64"]["sha256"] = "x"
        self.assert_red(snap, "sha256 missing or malformed")
        snap = support.snapshot()
        snap["toolchains"]["tools"]["bun"]["install"]["version"] = "latest"
        self.assert_red(snap, "pinned version")

    def test_red_effectful_step_without_declared_effect(self):
        snap = support.snapshot()
        step = self.step(snap, "tokenomics.venv")
        del step["creates"]
        del step["probe"]
        self.assert_red(snap, "declares creates or probe.exists (I1)")

    def test_red_unknown_need_and_placeholder(self):
        snap = support.snapshot()
        self.step(snap, "z0evals.deps")["needs"] = ["z0evals.nope"]
        self.assert_red(snap, "unknown need z0evals.nope")
        snap = support.snapshot()
        self.step(snap, "z0evals.deps")["argv"] = ["pip", "{oops}"]
        self.assert_red(snap, "unknown placeholders")


@require_yaml
class LegacyUnchanged(unittest.TestCase):
    """`z0 init` keeps today's behaviour: commands.py is untouched (§12) and the profile
    sets do not grow; dash and z0evals are onboard supplementals only (D-3)."""

    def test_profiles_resolve_as_before(self):
        from z0 import registry
        expect = {
            "minimal": ["oh-my-pi"], "core": ["oh-my-pi", "tokenomics"],
            "personal": ["z0intelligence", "oh-my-pi", "tokenomics"],
            "desktop": ["flow", "oh-my-pi", "tokenomics"],
            "compute": ["kerdoios", "oh-my-pi", "tokenomics"],
            "research": ["z0intelligence", "tokenomics", "evolution-lab", "frontier-kb"],
            "full": ["oh-my-pi", "tokenomics", "z0intelligence", "flow", "kerdoios",
                     "evolution-lab", "frontier-kb", "aodl", "agenttrace"],
        }
        for name, comps in expect.items():
            self.assertEqual(registry.resolve_profile(name), comps, name)

    def test_init_dry_run_output(self):
        out = subprocess.run([sys.executable, "-m", "z0", "init", "--profile", "core", "--dry-run"],
                             capture_output=True, text=True, cwd=ROOT,
                             env={"PYTHONPATH": str(ROOT / "lib"), "PATH": "/usr/bin:/bin",
                                  "HOME": "/nonexistent", "Z0_HOME": "/nonexistent/.z0",
                                  "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("oh-my-pi", out.stdout)
        self.assertNotIn("dash", out.stdout)
        self.assertNotIn("z0evals", out.stdout)


@require_yaml
class HostLiterals(unittest.TestCase):
    """Law H2: nothing Z1 renders or ships carries a denylisted literal or a $HOME path."""

    def test_no_denylisted_literals_or_home_paths(self):
        from z0.onboard import regcheck
        deny = support.snapshot()["onboarding"]["denylists"]["redaction"]
        rendered = sorted(EXPECTED.glob("*.json")) + [ROOT / "generated/onboarding-matrix.md"]
        self.assertGreaterEqual(len(rendered), 8)
        for path in rendered:
            with self.subTest(file=path.name):
                self.assertEqual(regcheck.scan_literals(path.read_text(encoding="utf-8"), deny), [])
        # Fixtures are detected facts: ~-paths only, tailnet IPs in the documentation range.
        for path in sorted(FIXTURES.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(fixture=path.name):
                self.assertIsNone(re.search(r'"/(home|Users)/', text))
                self.assertEqual(set(re.findall(r"\b100\.(\d+)\.(\d+)\.\d+", text)) - {("64", "0")}, set())

    def test_plans_take_tailnet_ips_only_from_detection(self):
        from z0.onboard.plan import plan
        for name in support.fixture_names():
            host = support.fixture(name)
            text = json.dumps(plan(host, support.snapshot()))
            ips = set(re.findall(r"\b100\.\d+\.\d+\.\d+\b", text))
            allowed = {(host.get("tailscale") or {}).get("ipv4")} - {None}
            self.assertLessEqual(ips, allowed, name)


if __name__ == "__main__":
    unittest.main()
