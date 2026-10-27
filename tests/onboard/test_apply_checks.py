"""Hub and z0evals acceptance checks, redaction (§9), the canary scan (X1), the
journal format and the pure freshness rules, without running a whole apply."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from tests.onboard import fakehost
from tests.onboard.fakeapply import FakeApply
from tests.onboard.support import ROOT, require_yaml, snapshot


class View:
    """The slice of verify.VerifyView the hub checks read."""

    def __init__(self, plan_obj, results, snap):
        from z0.onboard.verify import VerifyView
        self.inner = VerifyView(plan_obj, results, None, snap, [])

    def __getattr__(self, name):
        return getattr(self.inner, name)


def hub_plan(profile="core", extra_targets=()):
    steps = [{"step": {"id": sid, "component": "z0", "kind": "check", "consent": {"class": "C0"},
                       "argv": ["true"]}, "state": {"status": "todo"}}
             for sid in ("z0.registry_check", "z0.plan_deterministic", "z0.init_dry_run")]
    return {"profile": profile, "targets": ["oh-my-pi", "tokenomics", *extra_targets], "steps": steps}


@require_yaml
class HubChecks(unittest.TestCase):
    INIT_OK = "\nProfile: core\nRoot:    ~/.z0/repos\n\n  oh-my-pi\n    clone: x\n  tokenomics\n    clone: y\n"

    def evaluate(self, plan_obj, results):
        from z0.onboard.checks import z0
        return {i["name"]: i for i in z0.evaluate(View(plan_obj, results, snapshot()))}

    def passed(self, output):
        return {"z0.registry_check": {"status": "passed"}, "z0.plan_deterministic": {"status": "passed"},
                "z0.init_dry_run": {"status": "passed", "output": output}}

    def test_green(self):
        out = self.evaluate(hub_plan(), self.passed(self.INIT_OK))
        self.assertEqual({k: v["status"] for k, v in out.items()},
                         {"registry_check": "passed", "plan_deterministic": "passed",
                          "init_dry_run": "passed", "memento_never_planned": "passed"})

    def test_red_init_lists_a_supplemental(self):
        out = self.evaluate(hub_plan(), self.passed(self.INIT_OK + "  dash\n"))
        self.assertEqual(out["init_dry_run"]["status"], "failed")

    def test_red_registry_check_failed(self):
        results = self.passed(self.INIT_OK)
        results["z0.registry_check"] = {"status": "failed", "reason": "R-sync"}
        self.assertEqual(self.evaluate(hub_plan(), results)["registry_check"]["status"], "failed")

    def test_red_M1_memento_planned(self):
        out = self.evaluate(hub_plan(extra_targets=("memento",)), self.passed(self.INIT_OK))
        self.assertEqual(out["memento_never_planned"]["status"], "failed")


class Redaction(unittest.TestCase):
    def test_masks_values_patterns_and_home(self):
        from z0.onboard.redact import Redactor
        r = Redactor("/srv/fakehome", [fakehost.CANARY])
        text = (f"key={fakehost.CANARY} Authorization: Bearer abcdefghijkl token: {'a' * 24} "
                "sk-" + "x" * 20 + " ghp_" + "y" * 36 + " /srv/fakehome/.z0/x")
        out = r(text)
        self.assertNotIn(fakehost.CANARY, out)
        self.assertNotIn("abcdefghijkl", out)
        self.assertNotIn("a" * 24, out)
        self.assertNotIn("x" * 20, out)
        self.assertNotIn("y" * 36, out)
        self.assertIn("~/.z0/x", out)
        self.assertTrue(r.found_in(f"..{fakehost.CANARY}..".encode()))

    @require_yaml
    def test_registry_secret_names_are_registered_from_env_only(self):
        from z0.onboard.redact import from_env, secret_names
        snap = snapshot()
        self.assertIn("CEREBRAS_API_KEY", secret_names(snap))
        r = from_env(snap, {"CEREBRAS_API_KEY": fakehost.CANARY, "UNRELATED": "zzzzzzzzzz"})
        self.assertEqual(r.values, frozenset({fakehost.CANARY}))


@require_yaml
class CanaryScan(unittest.TestCase):
    def test_X1_red_a_canary_in_the_run_dir_fails_verify(self):
        from z0.onboard.apply import apply_run
        from z0.onboard.verify import verify_run
        with tempfile.TemporaryDirectory() as tmp:
            fa = FakeApply(Path(tmp))
            host = fa.detect()
            plan_obj = fa.plan(host, fa.request())
            run = fa.write_run(host, plan_obj)
            deps = fa.deps(detect=False)
            result = apply_run(run, deps)
            self.assertEqual(result.code, 0)
            (run / "logs" / "leak.log").write_text(f"oops {fakehost.CANARY}\n")
            code, receipt = verify_run(run, deps, prior=result.results, host=result.host)
            self.assertTrue(receipt["secrets_scan"]["canary_found"])
            self.assertEqual(code, 1)
            self.assertIn("CANARY FOUND", (run / "report.md").read_text())
            self.assertNotIn(fakehost.CANARY, (run / "report.md").read_text())
            self.assertNotIn(fakehost.CANARY, (run / "receipt.json").read_text())


class JournalFormat(unittest.TestCase):
    def test_append_fsync_mode_and_torn_line(self):
        from z0.onboard.journal import Journal, read
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            j = Journal(path, "r1")
            j.effect("s1", {"kind": "file", "path": "~/x", "sha256": "0" * 64})
            with open(path, "a") as fh:
                fh.write('{"event": "effect", "torn')
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(len(read(path)), 1)
            j2 = Journal(path, "r1")
            self.assertEqual(j2.effect("s2", {"kind": "mkdir", "path": "~/y"})["seq"], 2)
            with self.assertRaises(ValueError):
                j2.effect("s3", {"kind": "rm_rf", "path": "~"})


class Freshness(unittest.TestCase):
    HOST = {"host_id": "a" * 16, "toolchains": {"node": {"state": "present", "version": "22.1.0"}},
            "tailscale": {"ipv4": None}, "services": {"units": [], "port_owners": {}},
            "checkouts": [], "hardware": {"disks": [{"free_gib": 50, "role": ["z0_home"]}]}}

    def plan(self, todo):
        return {"steps": [{"step": {"id": sid, "consent": {"class": cls}}, "state": {"status": "todo"}}
                          for sid, cls in todo]}

    def test_no_drift_proceeds(self):
        from z0.onboard import freshness, kernel as k
        self.assertEqual(freshness.drift(self.HOST, json.loads(json.dumps(self.HOST))), [])
        self.assertIs(freshness.decide(self.HOST, self.HOST, self.plan([]), None, False), k.Replan.PROCEED)

    def test_drift_within_grants_shows_diff_and_widening_reconfirms_even_with_yes(self):
        from z0.onboard import freshness, kernel as k
        new = json.loads(json.dumps(self.HOST))
        new["toolchains"]["node"] = {"state": "absent"}
        self.assertEqual(freshness.drift(self.HOST, new), ["toolchains"])
        same = self.plan([("a", "C0")])
        self.assertIs(freshness.decide(self.HOST, new, same, self.plan([("a", "C0"), ("b", "C0")]), True),
                      k.Replan.SHOW_DIFF)
        self.assertIs(freshness.decide(self.HOST, new, same, self.plan([("a", "C0"), ("n", "C1")]), True),
                      k.Replan.RECONFIRM)

    def test_disk_drift_is_by_tier(self):
        from z0.onboard import freshness
        new = json.loads(json.dumps(self.HOST))
        new["hardware"]["disks"][0]["free_gib"] = 49
        self.assertEqual(freshness.drift(self.HOST, new), [])
        new["hardware"]["disks"][0]["free_gib"] = 5
        self.assertEqual(freshness.drift(self.HOST, new), ["disk_tier"])


class NoHostLiteralsInNewCode(unittest.TestCase):
    """H2 for Z2's own sources: public-leak-check finds nothing in them."""

    def test_leak_check_is_clean(self):
        import subprocess
        import sys
        paths = [str(ROOT / p) for p in ("lib/z0/onboard", "tests/onboard", "scripts/onboard-e2e",
                                         ".github/workflows") if (ROOT / p).exists()]
        out = subprocess.run([sys.executable, str(ROOT / "scripts/public-leak-check"), *paths],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)


if __name__ == "__main__":
    unittest.main()
