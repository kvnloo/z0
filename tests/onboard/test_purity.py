"""Law P0, dry-run purity (§1.3), through the real `./z0` launcher on a fake host.

- `detect` writes nothing anywhere.
- `plan --stdout` (PyYAML importable) writes nothing anywhere.
- `plan` writes only $Z0_HOME/onboard/runs/<id>/ (dir 0700, files 0600).
- None of them writes into the z0 checkout (no bytecode caches either).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from tests.onboard import fakehost
from tests.onboard.support import ROOT, require_yaml


def repo_state() -> dict:
    return fakehost.tree_state(ROOT, skip={str(ROOT / ".git")})


@require_yaml
class DryRunPurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fake = fakehost.build(Path(cls.tmp.name))
        launcher_bin = Path(cls.tmp.name) / "launcher-bin"
        launcher_bin.mkdir()
        for tool in ("dirname",):
            os.symlink(subprocess.run(["sh", "-c", f"command -v {tool}"], capture_output=True,
                                      text=True).stdout.strip(), launcher_bin / tool)
        wrapper = launcher_bin / "python3"  # this python (it has PyYAML); a wrapper keeps its venv
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        wrapper.chmod(0o755)
        env = dict(cls.fake["env"])
        env.update({"PATH": f"{launcher_bin}:{cls.fake['userbin']}",
                    "Z0_HOME": str(cls.fake["home"] / ".z0"),
                    "Z0_DETECT_SYSROOT": str(cls.fake["sysroot"]),
                    "Z0_DETECT_SYSTEM_DIRS": str(cls.fake["sysbin"]),
                    "Z0_DETECT_OFFLINE": "1"})
        cls.env = env

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_z0(self, *args):
        bash = subprocess.run(["sh", "-c", "command -v bash"], capture_output=True, text=True).stdout.strip()
        return subprocess.run([bash, str(ROOT / "z0"), "onboard", *args], env=self.env,
                              capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)

    def home(self):
        return fakehost.tree_state(self.fake["home"])

    def test_detect_writes_nothing(self):
        before_home, before_repo = self.home(), repo_state()
        out = self.run_z0("detect")
        self.assertEqual(out.returncode, 0, out.stderr)
        host = json.loads(out.stdout)
        self.assertEqual(host["os"]["distro"], "arch")
        self.assertNotIn(fakehost.CANARY, out.stdout + out.stderr)
        self.assertEqual(self.home(), before_home)
        self.assertEqual(repo_state(), before_repo)

    def test_plan_stdout_writes_nothing(self):
        before_home, before_repo = self.home(), repo_state()
        out = self.run_z0("plan", "--auto", "--stdout")
        self.assertIn(out.returncode, (0, 4), out.stderr)
        plan = json.loads(out.stdout)
        self.assertEqual(plan["mode"], "auto")
        self.assertNotIn(fakehost.CANARY, out.stdout + out.stderr)
        self.assertEqual(self.home(), before_home)
        self.assertEqual(repo_state(), before_repo)
        self.assertFalse((self.fake["home"] / ".z0").exists())

    def test_plan_writes_only_its_run_dir(self):
        before_home, before_repo = self.home(), repo_state()
        out = self.run_z0("plan", "--auto")
        self.assertIn(out.returncode, (0, 4), out.stderr)
        after = self.home()
        runs = self.fake["home"] / ".z0/onboard/runs"
        changed = {p for p in after if before_home.get(p) != after[p]}
        allowed_parents = {str(self.fake["home"] / ".z0"), str(self.fake["home"] / ".z0/onboard"),
                           str(runs)}
        for path in changed:
            self.assertTrue(path.startswith(str(runs) + os.sep) or path in allowed_parents, path)
        run_dirs = list(runs.iterdir())
        self.assertEqual(len(run_dirs), 1)
        self.assertEqual(stat.S_IMODE(run_dirs[0].stat().st_mode), 0o700)
        names = sorted(p.name for p in run_dirs[0].iterdir())
        self.assertEqual(names, ["host.json", "plan.diff.txt", "plan.json"])
        for path in run_dirs[0].iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)
        self.assertNotIn(fakehost.CANARY, (run_dirs[0] / "host.json").read_text())
        self.assertEqual(repo_state(), before_repo)
        for path in sorted(run_dirs[0].iterdir()):
            path.unlink()
        run_dirs[0].rmdir()

    def test_determinism_check(self):
        out = self.run_z0("plan", "--stdout", "--check-deterministic")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(out.stdout.startswith("deterministic "))

    def test_H1_recorded_host_json_from_another_host_is_refused(self):
        other = Path(self.tmp.name) / "other-host.json"
        other.write_text((Path(__file__).parent / "fixtures/hosts/mbp-cpu-15g.json").read_text())
        out = self.run_z0("plan", "--stdout", "--host", str(other))
        self.assertEqual(out.returncode, 4, out.stderr)
        plan = json.loads(out.stdout)
        self.assertEqual({e["state"]["status"] for e in plan["steps"]}, {"refused"})

    def test_later_subcommands_refuse_cleanly(self):
        before_home = self.home()
        out = self.run_z0("pair", "dash")
        self.assertEqual(out.returncode, 2)
        self.assertIn("Z4", out.stderr)
        self.assertEqual(self.home(), before_home)

    def test_apply_of_an_unknown_run_is_a_usage_error_and_writes_nothing(self):
        before_home = self.home()
        for args in (("apply", "x"), ("apply", "../x"), ("verify", "x"), ("rollback", "x")):
            out = self.run_z0(*args)
            self.assertEqual(out.returncode, 2, (args, out.stderr))
            self.assertIn("run", out.stderr)
        self.assertEqual(self.home(), before_home)


if __name__ == "__main__":
    unittest.main()
