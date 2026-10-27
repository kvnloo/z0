"""CW7 hand-off files (contributor spec §1.2 S1, §3.2): `$Z0_HOME/onboard/state` and
`$Z0_HOME/onboard/profile.json`, both 0600, never carrying a held secret (X1)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

import tests.onboard.support  # noqa: F401 - puts lib/ on sys.path


def receipt(code=0, failed=(), canary=False):
    steps = [{"id": "a", "status": "passed"}] + [{"id": f, "status": "failed"} for f in failed]
    return {"exit_code": code, "plan_hash": "ab" * 32, "steps": steps, "acceptance": {"z0": {"x": "passed"}},
            "asks": [{"id": "dash.apk"}], "secrets_scan": {"canary_found": canary}}


class State(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.run = self.home / "onboard" / "runs" / "20261026T000000Z-abababab"
        self.run.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rec, redactor=None):
        from z0.onboard import handoff
        return handoff.write_state(str(self.home), self.run, rec, str(self.home), redactor)

    def test_ok_on_exit_0_and_on_exit_3_with_only_asks(self):
        self.assertEqual(self.write(receipt(0))["status"], "success")
        rec = self.write(receipt(3))
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["status"], "partial")
        path = self.home / "onboard" / "state"
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(json.loads(path.read_text())["run_id"], self.run.name)

    def test_not_ok_on_failure_or_canary(self):
        self.assertFalse(self.write(receipt(1, failed=["b"]))["ok"])
        self.assertFalse(self.write(receipt(3, failed=["b"]))["ok"])
        self.assertFalse(self.write(receipt(0, canary=True))["ok"])

    def test_rollback_marks_state(self):
        from z0.onboard import handoff
        self.write(receipt(0))
        handoff.mark_rolled_back(str(self.home), "another-run")
        self.assertTrue(json.loads((self.home / "onboard" / "state").read_text())["ok"])
        handoff.mark_rolled_back(str(self.home), self.run.name)
        data = json.loads((self.home / "onboard" / "state").read_text())
        self.assertEqual((data["ok"], data["status"]), (False, "rolled_back"))

    def test_X1_secret_never_written(self):
        from z0.onboard.redact import Redactor
        red = Redactor(str(self.home), ["sekret-value-1234567890"])
        rec = receipt(0)
        rec["acceptance"]["z0"]["x"] = "sekret-value-1234567890"
        with self.assertRaises(ValueError):
            self.write(rec, red)
        self.assertFalse((self.home / "onboard" / "state").exists())


if __name__ == "__main__":
    unittest.main()
