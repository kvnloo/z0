"""scripts/contrib_ready.py as the operational gate: READY and exit 0 only on the
candidate pair with every REQUIRED receipt passing; everything else is a report."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.contrib_ready import laws, twin

cr = twin.cr
Z0, Z0INT = laws.Z0, laws.Z0INT


def _write(folder: Path, receipts) -> None:
    for index, receipt in enumerate(receipts):
        (folder / f"{index:02d}.json").write_text(json.dumps(receipt))


def _run(folder: Path, *extra, z0=Z0, z0int=Z0INT):
    return subprocess.run([sys.executable, str(twin.SCRIPT), "--z0", z0, "--z0int", z0int,
                           "--receipts", str(folder), *extra],
                          capture_output=True, text=True, timeout=60)


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "receipts"
        self.dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_ready_only_with_every_receipt_on_the_candidate_pair(self):
        _write(self.dir, laws._receipts(cr))
        before = sorted(p.name for p in self.dir.iterdir())
        out = _run(self.dir)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        lines = out.stdout.splitlines()
        self.assertEqual(lines[:4], ["READY", f"z0 {Z0}", f"z0int {Z0INT}", "cells 32/32"])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), before, "the gate wrote a file")

    def test_empty_store_is_not_ready(self):
        out = _run(self.dir)
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stdout.splitlines()[0], "NOT_READY")
        self.assertIn("cells 0/32", out.stdout)

    def test_missing_store_is_not_ready(self):
        out = _run(self.dir / "absent")
        self.assertEqual((out.returncode, out.stdout.splitlines()[0]), (1, "NOT_READY"))

    def test_each_missing_cell_is_not_ready_and_named(self):
        for drop in ("agent.codex.systems-rust.run3", "laws_ci", "G4", "onboard_container"):
            with self.subTest(drop=drop):
                for path in self.dir.iterdir():
                    path.unlink()
                _write(self.dir, laws._receipts(cr, skip=(drop,)))
                out = _run(self.dir)
                self.assertEqual(out.returncode, 1)
                self.assertIn(f"  {drop}: none", out.stdout)
                self.assertIn("cells 31/32", out.stdout)

    def test_stale_commit_passes_never_count(self):
        receipts = laws._receipts(cr)
        receipts[7] = dict(receipts[7], z0_sha="c" * 40)       # another z0 commit
        receipts[20] = dict(receipts[20], z0int_sha=Z0INT[:12])  # a short sha is not exact
        _write(self.dir, receipts)
        out = _run(self.dir)
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("pass_other_sha", out.stdout)
        self.assertIn("cells 30/32", out.stdout)

    def test_whole_store_from_another_pair_is_not_ready(self):
        _write(self.dir, laws._receipts(cr))
        out = _run(self.dir, z0="d" * 40)
        self.assertEqual((out.returncode, out.stdout.splitlines()[0]), (1, "NOT_READY"))

    def test_candidate_fail_beside_a_pass_is_not_ready(self):
        receipts = laws._receipts(cr) + [dict(laws._receipts(cr)[0], status="fail")]
        _write(self.dir, receipts)
        out = _run(self.dir)
        self.assertEqual(out.returncode, 1)
        self.assertIn("agent.claude.frontend.run1: fail", out.stdout)

    def test_blockers(self):
        _write(self.dir, laws._receipts(cr))
        blockers = Path(self.tmp.name) / "blockers.json"
        blockers.write_text(json.dumps([{"kind": "external", "reason": "api outage"}]))
        out = _run(self.dir, "--blockers", str(blockers))
        self.assertEqual((out.returncode, out.stdout.splitlines()[0]), (3, "BLOCKED_EXTERNAL"))
        blockers.write_text(json.dumps([{"kind": "owner"}]))
        out = _run(self.dir, "--blockers", str(blockers))
        self.assertEqual((out.returncode, out.stdout.splitlines()[0]), (1, "NOT_READY"))

    def test_malformed_receipts_are_ignored_with_a_warning(self):
        _write(self.dir, laws._receipts(cr)[1:])
        (self.dir / "zz-bad.json").write_text("{not json")
        (self.dir / "zz-other.json").write_text(json.dumps({"cell": "Z9", "status": "pass"}))
        out = _run(self.dir)
        self.assertEqual(out.returncode, 1)
        self.assertIn("warning: unreadable receipt ignored: zz-bad.json", out.stdout)
        self.assertIn("warning: receipt names no required cell, ignored: zz-other.json", out.stdout)

    def test_usage_errors(self):
        self.assertEqual(_run(self.dir, z0="abc1234").returncode, 2)
        self.assertEqual(_run(self.dir, z0int="").returncode, 2)

    def test_json_report(self):
        _write(self.dir, laws._receipts(cr, skip=("smoke",)))
        out = _run(self.dir, "--json")
        report = json.loads(out.stdout)
        self.assertEqual(report["status"], "NOT_READY")
        self.assertEqual(report["not_counted"], {"smoke": "none"})
        self.assertEqual((report["counted"], report["required"]), (31, 32))


if __name__ == "__main__":
    unittest.main()
