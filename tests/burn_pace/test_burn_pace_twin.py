"""Twin parity: lib/z0/burn_pace.py admit_cls/route_cls equal bend/burn_pace MODEL over every case.

TABLE.bend prints MODEL.admit for every (Fresh, Used, Pace, Who) and MODEL.route for both inputs.
The Bend run needs the pinned toolchain (`./z0 laws check` provides it); without it the execution
test is skipped unless Z0_REQUIRE_BEND=1. The classification tests always run.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
from z0 import burn_pace as g  # noqa: E402

DOMAIN = ROOT / "bend/burn_pace"
ORDER = [(f, u, p, w) for f in (g.FRESH, g.STALE) for u in (g.UNDER, g.AT_CAP)
         for p in (g.COOL, g.UNKNOWN, g.HOT) for w in (g.OWNER, g.BULK)]


def bend_table():
    from laws.verifier import verifier_environment
    with verifier_environment() as (bend, env), tempfile.TemporaryDirectory(dir=env["TMPDIR"]) as folder:
        for name in ("MODEL.bend", "TABLE.bend"):
            shutil.copy2(DOMAIN / name, Path(folder) / name)
        out = subprocess.run([str(bend), "TABLE.bend"], cwd=folder, env=env, capture_output=True,
                             text=True, timeout=120, check=False)
        line = next(x for x in out.stdout.splitlines() if x.startswith("["))
        return [x.strip() == "True{}" for x in line.strip("[]").split(",")]


class Parity(unittest.TestCase):
    def test_twin_matches_bend_table_exhaustively(self):
        if not os.environ.get("BEND") and os.environ.get("Z0_REQUIRE_BEND") != "1":
            self.skipTest("run with z0 laws check for pinned Bend parity")
        table = bend_table()
        self.assertEqual(len(table), len(ORDER) + 2)
        self.assertEqual([g.admit_cls(*k) for k in ORDER], table[:len(ORDER)])
        self.assertEqual([g.route_cls(True) == "paid", g.route_cls(False) == "paid"], table[len(ORDER):])


class Classify(unittest.TestCase):
    def test_readings_map_into_the_law_domain(self):
        now = datetime.now(timezone.utc).isoformat()
        rd = {"at": now, "lanes": {
            "a": {"weekly_used_pct": 100.0, "pace_ratio": None},
            "b": {"weekly_used_pct": 40.0, "pace_ratio": 0.99},
            "d": {"weekly_used_pct": 50.0, "pace_ratio": 1.2, "observed_pct_per_h": 0.6, "hours_to_reset": 100.0},
            "e": {"weekly_used_pct": 10.0, "pace_ratio": 0.9, "observed_pct_per_h": 0.5, "hours_to_reset": 140.0}}}
        self.assertEqual(g.classify("a", rd)[:3], (g.FRESH, g.AT_CAP, g.UNKNOWN))
        self.assertEqual(g.classify("b", rd)[:3], (g.FRESH, g.UNDER, g.COOL))
        self.assertEqual(g.classify("d", rd)[2], g.HOT)  # projects to 110% before reset, though under 1.5x
        self.assertEqual(g.classify("e", rd)[2], g.COOL)
        self.assertEqual(g.classify("zz", rd)[0], g.STALE)
        self.assertEqual(g.classify("b", {"at": "2020-01-01T00:00:00+00:00", "lanes": rd["lanes"]})[0], g.STALE)

    def test_owner_is_only_opus_in_an_owner_profile(self):
        lanes = {"owner_profiles": ["owner-chat"]}
        self.assertEqual(g.who_for("claude-opus-5-5", lanes, "owner-chat"), g.OWNER)
        self.assertEqual(g.who_for("claude-haiku-5-5", lanes, "owner-chat"), g.BULK)
        self.assertEqual(g.who_for("claude-opus-5-5", lanes, "lane-worker"), g.BULK)
        self.assertEqual(g.who_for("claude-opus-5-5", lanes, None), g.BULK)


if __name__ == "__main__":
    unittest.main()
