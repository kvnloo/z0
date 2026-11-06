"""Each mutant re-opens a drain path and must be rejected.

Bend lane: each MODEL.bend mutant must make the unchanged LAWS/PROOF fail `bend PROOF.bend
--verdict` after a passing reference verdict (skipped without the pinned toolchain unless
Z0_REQUIRE_BEND=1). Python lane: each lib/z0/burn_pace.py mutant must break parity with the law
table the reference twin produces (always runs).
"""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
from z0 import burn_pace as ref  # noqa: E402

DOMAIN = ROOT / "bend/burn_pace"
BEND_MUTANTS = [
    ("hot pace ok for bulk", "    case PHot{}:\n      False{}", "    case PHot{}:\n      True{}"),
    ("at-cap admits", "        case UAtCap{}:\n          False{}", "        case UAtCap{}:\n          pace_ok_for(w, p)"),
    ("stale admits", "    case FStale{}:\n      False{}", "    case FStale{}:\n      True{}"),
    ("none admitted routes paid", "    case False{}:\n      RFree{}", "    case False{}:\n      RPaid{}"),
    ("owner loses opus when hot", "    case WOwner{}:\n      True{}", "    case WOwner{}:\n      pace_ok(p)"),
    ("bulk ignores pace", "    case WBulk{}:\n      pace_ok(p)", "    case WBulk{}:\n      True{}"),
    ("unknown pace denied", "    case PUnknown{}:\n      True{}", "    case PUnknown{}:\n      False{}"),
]
PY_MUTANTS = [
    ("bulk ignores pace", "(who == OWNER or pace in (COOL, UNKNOWN))", "True"),
    ("at cap admits", "fresh == FRESH and used == UNDER and", "fresh == FRESH and"),
    ("stale admits", "fresh == FRESH and used == UNDER", "used == UNDER"),
    ("owner loses opus", "(who == OWNER or pace in (COOL, UNKNOWN))", "pace in (COOL, UNKNOWN)"),
    ("none admitted routes paid", 'return "paid" if any_admitted else "free"', 'return "paid"'),
]
ORDER = [(f, u, p, w) for f in (ref.FRESH, ref.STALE) for u in (ref.UNDER, ref.AT_CAP)
         for p in (ref.COOL, ref.UNKNOWN, ref.HOT) for w in (ref.OWNER, ref.BULK)]


def table(mod):
    return [mod.admit_cls(*k) for k in ORDER] + [mod.route_cls(True), mod.route_cls(False)]


class PythonMutants(unittest.TestCase):
    def test_every_twin_mutant_breaks_parity(self):
        src = (ROOT / "lib/z0/burn_pace.py").read_text()
        want = table(ref)
        for label, a, b in PY_MUTANTS:
            with self.subTest(label):
                self.assertEqual(src.count(a), 1, label)
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / "m.py"
                    p.write_text(src.replace(a, b))
                    spec = importlib.util.spec_from_file_location(f"m_{abs(hash(label))}", p)
                    m = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(m)
                    self.assertNotEqual(table(m), want, f"mutant survived: {label}")


class BendMutants(unittest.TestCase):
    def test_every_model_mutant_is_rejected(self):
        if not os.environ.get("BEND") and os.environ.get("Z0_REQUIRE_BEND") != "1":
            self.skipTest("run with z0 laws check for pinned Bend")
        from laws.verifier import verifier_environment
        with verifier_environment() as (bend, env):
            def verdict(folder):
                r = subprocess.run([str(bend), "PROOF.bend", "--verdict"], cwd=folder, env=env,
                                   capture_output=True, text=True, timeout=180, check=False)
                return r.stdout + r.stderr
            with tempfile.TemporaryDirectory(dir=env["TMPDIR"]) as d:
                for n in ("MODEL.bend", "LAWS.bend", "PROOF.bend"):
                    shutil.copy2(DOMAIN / n, Path(d) / n)
                self.assertIn("ALL PROOFS CHECK", verdict(d), "reference verdict must pass first")
                model = (DOMAIN / "MODEL.bend").read_text()
                for label, a, b in BEND_MUTANTS:
                    with self.subTest(label):
                        self.assertEqual(model.count(a), 1, label)
                        (Path(d) / "MODEL.bend").write_text(model.replace(a, b))
                        self.assertIn("SOME PROOFS FAIL", verdict(d), f"mutant survived: {label}")
                (Path(d) / "MODEL.bend").write_text(model)


if __name__ == "__main__":
    unittest.main()
