"""Twin parity: scripts/contrib_ready.py and bend/contrib_ready/MODEL.bend agree (§4.4).

The Bend run needs BEND and LEAN_BIN (see bend/contrib_ready/bootstrap.sh). Without
them the execution test is skipped, unless Z0_REQUIRE_BEND=1 (the CI `laws` job),
where a skip is a failure. The constructor-set checks and the Python laws never need
Bend.
"""
from __future__ import annotations

from enum import Enum
import os
import unittest

from tests.contrib_ready import laws, twin

cr = twin.cr
MODEL = twin.DOMAIN / "MODEL.bend"

# Python enum -> Bend type name in MODEL.bend.
TYPE_MAP = {"Cell": cr.Cell, "Blocker": cr.Blocker, "Status": cr.Status,
            "Outcome": cr.Outcome, "Req": cr.Req}


class ConstructorSets(unittest.TestCase):
    def test_every_bend_type_matches_its_python_enum(self):
        types = twin.model_types(MODEL.read_text())
        self.assertEqual(set(types) - {"Cells"}, set(TYPE_MAP),
                         "MODEL.bend type set drifted from scripts/contrib_ready.py")
        self.assertEqual(types["Cells"], ["KEnd", "KCell"])
        for bend_name, enum in TYPE_MAP.items():
            with self.subTest(type=bend_name):
                self.assertEqual(types[bend_name], [m.value for m in enum],
                                 "constructor order is the code order; keep them identical")

    def test_required_count_matches_the_model_constant(self):
        text = MODEL.read_text()
        self.assertIn("def required_count() -> Nat:\n  32n\n", text)
        self.assertEqual(cr.required_count(), len(cr.REQUIRED))

    def test_every_domain_argument_is_an_enum_or_bool(self):
        for name, domain in cr.DOMAINS.items():
            for axis in domain:
                self.assertTrue(axis == (False, True) or (isinstance(axis, type)
                                                          and issubclass(axis, Enum)), name)

    def test_generated_cases_cover_every_row(self):
        rows = list(twin.cases())
        finite = [r for r in rows if r[2][0] != "decide"]
        self.assertEqual(len(finite), cr.DOMAIN_ROWS)
        self.assertEqual(len({expr for expr, _, _ in rows}), len(rows))
        self.assertGreater(len(rows) - len(finite), 2500, "bounded matrices shrank")


class PythonLaws(unittest.TestCase):
    def test_every_law_holds_on_the_twin(self):
        for law in laws.LAWS:
            with self.subTest(law=law.__name__):
                law(cr)


class BendParity(unittest.TestCase):
    def test_bend_python_parity(self):
        if not twin.bend_available():
            if os.environ.get("Z0_REQUIRE_BEND") == "1":
                self.fail("Z0_REQUIRE_BEND=1 but BEND/LEAN_BIN are not set")
            self.skipTest("BEND and LEAN_BIN not set")
        from tests.bend_verifier import verifier_environment
        with verifier_environment(twin.DOMAIN) as (bend, env):
            count = twin.run_parity(bend, env)
        self.assertEqual(count, len(list(twin.cases())))


if __name__ == "__main__":
    unittest.main()
