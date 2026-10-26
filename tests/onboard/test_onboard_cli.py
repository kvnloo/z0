"""`./z0 onboard` end to end through the launcher, on a fake host (design §1.1-1.2, §3).

The registry is a patched copy (Z0_ONBOARD_REGISTRY): z0evals points at a local fake
origin and the node pin at a local archive. The hub checks run for real against this
checkout (registry-check, plan determinism, `z0 init --dry-run`). No TTY, so:
- no --yes: C0 applies, the C1 toolchain stays an ask, exit 3 (scenario 5);
- --yes: every bundle granted, exit 0, verify green (scenario 1, offline);
- a re-run plans nothing new (scenario 3); rollback undoes the runs (scenario 4).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.onboard import fakehost
from tests.onboard.fakeapply import FakeApply, tree_bytes
from tests.onboard.support import ROOT, require_yaml


def write_registry(snap: dict, root: Path) -> None:
    import yaml
    reg = root / "registry"
    reg.mkdir(parents=True)
    for name in ("components", "profiles", "harnesses", "toolchains", "onboarding"):
        (reg / f"{name}.yaml").write_text(yaml.safe_dump(snap[name], sort_keys=False))


@require_yaml
class OnboardCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.fa = FakeApply(root, hub=True)
        for tool in ("bash", "dirname", "env"):
            os.symlink(shutil.which(tool), cls.fa.fake["sysbin"] / tool)
        write_registry(cls.fa.snap, root / "reg")
        bash = shutil.which("bash")
        cls.argv0 = [bash, str(ROOT / "z0"), "onboard"]
        env = dict(cls.fa.env)
        env.update({"PATH": str(cls.fa.fake["sysbin"]), "Z0_DETECT_SYSROOT": str(cls.fa.fake["sysroot"]),
                    "Z0_DETECT_SYSTEM_DIRS": str(cls.fa.fake["sysbin"]), "Z0_DETECT_OFFLINE": "1",
                    "Z0_ONBOARD_REGISTRY": str(root / "reg")})
        cls.env = env
        # What stage 0 leaves behind: the z0 venv with PyYAML (here: this test's python).
        venv_bin = cls.fa.z0_home / "venv" / "bin"
        venv_bin.mkdir(parents=True)
        for name in ("python", "python3"):
            (venv_bin / name).write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
            (venv_bin / name).chmod(0o755)
        (cls.fa.z0_home / "venv" / ".z0-owned").write_text("stage0\n")
        (cls.fa.z0_home / "onboard" / "runs").mkdir(parents=True)
        cls.before = tree_bytes(cls.fa.home, skip=(cls.fa.z0_home / "onboard",))
        common = ["--auto", "--profile", "minimal", "--without", "oh-my-pi,dash,z0intelligence", "--llm", "none"]
        cls.no_yes = cls.z0(*common)
        cls.runs_after_no_yes = sorted(os.listdir(cls.fa.z0_home / "onboard" / "runs"))
        cls.node_after_no_yes = (cls.fa.z0_home / "toolchains").exists()
        cls.yes = cls.z0(*common, "--yes")
        cls.again = cls.z0("plan", "--stdout", *common, "--yes")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def z0(cls, *args):
        return subprocess.run([*cls.argv0, *args], env=cls.env, capture_output=True, text=True,
                              timeout=900, stdin=subprocess.DEVNULL)

    def runs(self):
        return sorted(os.listdir(self.fa.z0_home / "onboard" / "runs"))

    def receipt(self, run_id):
        return json.loads((self.fa.z0_home / "onboard" / "runs" / run_id / "receipt.json").read_text())

    def test_scenario5_no_tty_no_yes_applies_C0_only_and_exits_3(self):
        self.assertEqual(self.no_yes.returncode, 3, self.no_yes.stdout + self.no_yes.stderr)
        self.assertIn("need consent and there is no TTY", self.no_yes.stderr)
        self.assertFalse(self.node_after_no_yes)  # C1 toolchain never installed
        receipt = self.receipt(self.runs_after_no_yes[0])
        self.assertEqual(receipt["exit_code"], 3)
        status = {s["id"]: s["status"] for s in receipt["steps"]}
        self.assertEqual(status["toolchain.node"], "ask")
        self.assertEqual(status["z0evals.source"], "passed")
        self.assertEqual(receipt["acceptance"]["z0evals"]["tiers"], "passed")

    def test_scenario1_yes_is_green_including_the_hub(self):
        self.assertEqual(self.yes.returncode, 0, self.yes.stdout[-3000:] + self.yes.stderr[-2000:])
        receipt = self.receipt(self.runs()[-1])
        hub = receipt["acceptance"]["z0"]
        self.assertEqual(hub, {"registry_check": "passed", "plan_deterministic": "passed",
                               "init_dry_run": "passed", "memento_never_planned": "passed"})
        status = {s["id"]: s["status"] for s in receipt["steps"]}
        self.assertEqual(status["toolchain.node"], "passed")
        self.assertEqual(status["z0evals.source"], "already_satisfied")
        self.assertIn("report:", self.yes.stdout)

    def test_scenario3_rerun_plans_nothing_new(self):
        plan_obj = json.loads(self.again.stdout)
        todo = [e["step"]["id"] for e in plan_obj["steps"]
                if e["state"]["status"] == "todo" and e["step"]["kind"] != "check"]
        self.assertEqual(todo, [])

    def test_scenario4_rollback_both_runs_restores_the_tree(self):
        # Runs sort by stamp; roll back the newest first (as `current` does).
        first, last = self.runs()[0], self.runs()[-1]
        out = self.z0("rollback")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f"rolled back {last}", out.stdout)
        current = self.fa.z0_home / "onboard" / "current"
        self.assertEqual(os.readlink(current), f"runs/{first}")
        out = self.z0("rollback", first)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(tree_bytes(self.fa.home, skip=(self.fa.z0_home / "onboard",)), self.before)
        out = self.z0("rollback", first)  # twice is safe
        self.assertEqual(out.returncode, 0)
        self.assertIn("nothing to undo", out.stdout)

    def test_secrets_and_grok(self):
        for out in (self.no_yes, self.yes):
            self.assertNotIn(fakehost.CANARY, out.stdout + out.stderr)
        self.assertFalse((self.fa.root / "grok-was-executed").exists())


if __name__ == "__main__":
    unittest.main()
