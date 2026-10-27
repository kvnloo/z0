"""Golden plans (design §10 layer 1): host fixtures x modes -> expected/*.plan.json.

Byte-for-byte, plus the plan hash. A golden changes only on purpose:
    Z0_UPDATE_GOLDEN=1 python -m unittest tests.onboard.test_plan_golden
    python -m tests.onboard.test_plan_golden --update-golden
"""
from __future__ import annotations

import json
import os
import sys
import unittest

from tests.onboard import support
from tests.onboard.support import EXPECTED, GOLDEN_CASES, require_yaml

UPDATE = os.environ.get("Z0_UPDATE_GOLDEN") == "1"


@require_yaml
class GoldenPlans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from z0.onboard.plan import plan, plan_hash
        cls.plan, cls.plan_hash = staticmethod(plan), staticmethod(plan_hash)

    def make(self, fixture, kwargs):
        return self.plan(support.fixture(fixture), support.snapshot(), **kwargs)

    def test_fixtures_cover_the_required_hosts(self):
        names = set(support.fixture_names())
        for required in ("desktop-nvidia-32g", "laptop-cpu-15g", "apple-m-32g", "tiny-4g-vps", "offline"):
            self.assertIn(required, names)

    def test_golden_plans(self):
        if UPDATE:
            EXPECTED.mkdir(parents=True, exist_ok=True)
        for stem, fixture, kwargs in GOLDEN_CASES:
            with self.subTest(case=stem):
                plan_obj = self.make(fixture, kwargs)
                text = support.render(plan_obj)
                path = EXPECTED / f"{stem}.plan.json"
                if UPDATE:
                    path.write_text(text, encoding="utf-8")
                    continue
                self.assertTrue(path.is_file(), f"missing golden {path.name}: run with --update-golden")
                self.assertEqual(text, path.read_text(encoding="utf-8"),
                                 f"{stem} drifted; review, then --update-golden")
                self.assertEqual(plan_obj["plan_hash"], self.plan_hash(plan_obj))

    def test_no_stale_goldens(self):
        stems = {stem for stem, _, _ in GOLDEN_CASES}
        for path in EXPECTED.glob("*.plan.json"):
            self.assertIn(path.name[:-len(".plan.json")], stems, f"stale golden {path.name}")

    def test_plan_is_deterministic(self):
        for stem, fixture, kwargs in GOLDEN_CASES:
            with self.subTest(case=stem):
                first = self.make(fixture, kwargs)
                again = self.plan(json.loads(json.dumps(support.fixture(fixture))),
                                  support.snapshot(), **kwargs)
                self.assertEqual(support.render(first), support.render(again))

    def test_hash_covers_every_field(self):
        plan_obj = self.make("laptop-cpu-15g", {})
        tampered = json.loads(json.dumps(plan_obj))
        tampered["steps"][0]["state"]["status"] = "already_satisfied"
        self.assertNotEqual(self.plan_hash(tampered), plan_obj["plan_hash"])

    def test_schemas_accept_fixtures_and_plans(self):
        hosts, plans = support.validator("host-profile"), support.validator("onboard-plan")
        if hosts is None:
            self.skipTest("jsonschema not installed (optional)")
        for name in support.fixture_names():
            with self.subTest(host=name):
                self.assertEqual([e.message for e in hosts.iter_errors(support.fixture(name))], [])
        for stem, fixture, kwargs in GOLDEN_CASES:
            with self.subTest(plan=stem):
                errors = [e.message for e in plans.iter_errors(self.make(fixture, kwargs))]
                self.assertEqual(errors, [])
        policy = support.validator("onboarding")
        self.assertEqual([e.message for e in policy.iter_errors(support.snapshot()["onboarding"])], [])


if __name__ == "__main__":
    if "--update-golden" in sys.argv:
        sys.argv.remove("--update-golden")
        os.environ["Z0_UPDATE_GOLDEN"] = "1"
        UPDATE = True
    unittest.main()
