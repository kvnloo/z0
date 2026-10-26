"""Twin parity: kernel.py and bend/onboard/MODEL.bend agree on every domain row (§11).

The Bend run needs BEND and LEAN_BIN (see bend/onboard/bootstrap.sh). Without them the
execution test is skipped, unless Z0_REQUIRE_BEND=1 (the CI `laws` job), where a skip
is a failure. The constructor-set check below never needs Bend.
"""
from __future__ import annotations

from enum import Enum
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from z0.onboard import kernel as k  # noqa: E402

from tests.onboard import bend_twin  # noqa: E402

MODEL = ROOT / "bend/onboard/MODEL.bend"

# Python enum -> Bend type name in MODEL.bend.
TYPE_MAP = {
    "Mode": k.Mode, "ConsentClass": k.ConsentClass, "Source": k.Source,
    "HostMatch": k.HostMatch, "BindClass": k.BindClass, "IpSource": k.IpSource,
    "RootKind": k.RootKind, "Provider": k.Provider, "Gate": k.Gate, "Flavour": k.Flavour,
    "RevOrigin": k.RevOrigin,
    "Maturity": k.Maturity, "HwClass": k.HwClass, "PyWindow": k.PyWindow,
    "RamTier": k.RamTier, "DiskTier": k.DiskTier, "Reason": k.Reason, "Verdict": k.Kind,
    "Profile": k.Profile, "TorchIndex": k.TorchIndex, "Replan": k.Replan,
}


class ConstructorSets(unittest.TestCase):
    def test_every_bend_type_matches_its_python_enum(self):
        types = bend_twin.model_types(MODEL.read_text())
        self.assertEqual(set(types), set(TYPE_MAP), "MODEL.bend type set drifted from kernel.py")
        for bend_name, enum in TYPE_MAP.items():
            with self.subTest(type=bend_name):
                self.assertEqual(types[bend_name], [m.value for m in enum],
                                 "constructor order is the code order; keep them identical")

    def test_every_domain_argument_is_an_enum_or_bool(self):
        for name, domain in k.DOMAINS.items():
            for axis in domain:
                self.assertTrue(axis == (False, True) or (isinstance(axis, type)
                                                          and issubclass(axis, Enum)), name)

    def test_generated_cases_cover_every_row(self):
        rows = list(bend_twin.cases())
        self.assertEqual(len(rows), k.DOMAIN_ROWS)
        self.assertEqual(len({expr for expr, _, _ in rows}), len(rows))


class BendParity(unittest.TestCase):
    def test_exhaustive_bend_python_parity(self):
        if not bend_twin.bend_available():
            if os.environ.get("Z0_REQUIRE_BEND") == "1":
                self.fail("Z0_REQUIRE_BEND=1 but BEND/LEAN_BIN are not set")
            self.skipTest("BEND and LEAN_BIN not set")
        from tests.bend_verifier import verifier_environment
        with verifier_environment(bend_twin.DOMAIN) as (bend, env):
            count = bend_twin.run_parity(bend, env)
        self.assertEqual(count, k.DOMAIN_ROWS)


if __name__ == "__main__":
    unittest.main()
