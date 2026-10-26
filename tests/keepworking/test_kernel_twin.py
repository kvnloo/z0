"""Twin parity: kernel.py and bend/keepworking/MODEL.bend agree on every row.

The Bend run needs BEND and LEAN_BIN (bend/keepworking/bootstrap.sh). Without them it
is skipped, unless Z0_REQUIRE_BEND=1, where a skip is a failure.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from z0.keepworking import kernel as k  # noqa: E402

from tests.keepworking import bend_twin  # noqa: E402

DOMAIN = ROOT / "bend/keepworking"
TYPE_MAP = {"Status": k.Status, "Evidence": k.Evidence, "Blocker": k.Blocker,
            "Ledger": k.Ledger, "Reason": k.Reason, "Verdict": k.Kind}


def need_bend(test):
    if not bend_twin.bend_available():
        if os.environ.get("Z0_REQUIRE_BEND") == "1":
            test.fail("Z0_REQUIRE_BEND=1 but BEND/LEAN_BIN are not set")
        test.skipTest("BEND and LEAN_BIN not set")


class ConstructorSets(unittest.TestCase):
    def test_every_bend_type_matches_its_python_enum(self):
        types = bend_twin.model_types((DOMAIN / "MODEL.bend").read_text())
        self.assertEqual(set(types), set(TYPE_MAP))
        for name, enum in TYPE_MAP.items():
            self.assertEqual(types[name], [m.value for m in enum], name)

    def test_generated_cases_cover_every_row(self):
        rows = list(bend_twin.cases())
        self.assertEqual(len(rows), k.DOMAIN_ROWS)
        self.assertEqual(len({e for e, _, _ in rows}), len(rows))


class BendLaws(unittest.TestCase):
    def test_proofs_check(self):
        need_bend(self)
        from tests.bend_verifier import verifier_environment
        with verifier_environment(DOMAIN) as (bend, env):
            out = subprocess.run([bend, "PROOF.bend", "--verdict"], cwd=DOMAIN, env=env,
                                 capture_output=True, text=True, timeout=1800)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("ALL PROOFS CHECK", out.stdout)

    def test_exhaustive_bend_python_parity(self):
        need_bend(self)
        from tests.bend_verifier import verifier_environment
        with verifier_environment(DOMAIN) as (bend, env):
            self.assertEqual(bend_twin.run_parity(bend, env), k.DOMAIN_ROWS)


if __name__ == "__main__":
    unittest.main()
