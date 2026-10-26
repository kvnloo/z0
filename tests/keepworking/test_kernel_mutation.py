"""Mutation tests: every seeded weakening of the law must be killed.

Python mutants are killed by the exhaustive law restatement (laws_py). Bend mutants
are killed by `bend PROOF.bend --verdict` (needs BEND/LEAN_BIN; one isolated compile
is reused for all mutants).
"""
from __future__ import annotations

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

from z0.keepworking import kernel as k  # noqa: E402

from tests.keepworking import bend_twin, laws_py  # noqa: E402

KERNEL = ROOT / "lib/z0/keepworking/kernel.py"
DOMAIN = ROOT / "bend/keepworking"

PYTHON_MUTANTS = [
    ("partial counts as done",
     "    return False\n\n\ndef _forbid",
     "    return status is Status.PARTIAL\n\n\ndef _forbid"),
    ("weak evidence accepted",
     "        return evidence is Evidence.OWNER_VISIBLE",
     "        return evidence is not Evidence.NONE"),
    ("agent-doable block accepted",
     "        return blocker is Blocker.OWNER_ONLY and fresh",
     "        return blocker is not Blocker.NONE and fresh"),
    ("stale block accepted",
     "        return blocker is Blocker.OWNER_ONLY and fresh",
     "        return blocker is Blocker.OWNER_ONLY"),
    ("loop guard ignores progress",
     "    if active and not progress:",
     "    if active:"),
    ("broken ledger allows",
     "        return _forbid(Reason.LEDGER_BROKEN, active, progress)",
     "        return allow(Reason.ALL_CLEAR)"),
    ("open asks allowed",
     "    return _forbid(Reason.OPEN_ASKS, active, progress)",
     "    return allow(Reason.ALL_CLEAR)"),
    ("waiting ignored",
     "    if waiting:\n        return allow(Reason.WAIT_BACKGROUND)\n",
     ""),
]

BEND_MUTANTS = [
    ("partial counts as done",
     "    case SPartial{}:\n      False{}", "    case SPartial{}:\n      True{}"),
    ("unknown counts as done",
     "    case SUnknown{}:\n      False{}", "    case SUnknown{}:\n      True{}"),
    ("weak evidence accepted",
     "        case EvWeak{}:\n          False{}", "        case EvWeak{}:\n          True{}"),
    ("agent-doable block accepted",
     "        case BkAgentDoable{}:\n          False{}", "        case BkAgentDoable{}:\n          fresh"),
    ("stale block accepted",
     "        case BkOwnerOnly{}:\n          fresh", "        case BkOwnerOnly{}:\n          True{}"),
    ("loop guard ignores progress",
     "        case True{}:\n          VBlock{reason}", "        case True{}:\n          VAllow{RNoProgress{}}"),
    ("missing ledger allows",
     "    case LMissing{}:\n      forbid(RLedgerBroken{}, active, progress)",
     "    case LMissing{}:\n      VAllow{RAllClear{}}"),
    ("open asks allowed",
     "        case False{}:\n          forbid(ROpenAsks{}, active, progress)",
     "        case False{}:\n          VAllow{RAllClear{}}"),
    ("waiting ignored",
     "        case True{}:\n          VAllow{RWaitBackground{}}",
     "        case True{}:\n          ledger_verdict(ledger, all_ok, active, progress)"),
]


def load_mutant(source: str):
    folder = Path(tempfile.mkdtemp(prefix="z0-kw-mut-"))
    try:
        path = folder / "kernel_mutant.py"
        path.write_text(source)
        spec = importlib.util.spec_from_file_location("kernel_mutant", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["kernel_mutant"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        shutil.rmtree(folder, ignore_errors=True)


class PythonMutants(unittest.TestCase):
    def test_original_satisfies_every_law(self):
        self.assertEqual(laws_py.violations(k), set())

    def test_every_mutant_is_killed(self):
        source = KERNEL.read_text()
        for label, anchor, replacement in PYTHON_MUTANTS:
            with self.subTest(mutant=label):
                self.assertEqual(source.count(anchor), 1, f"anchor drifted: {label}")
                mutant = load_mutant(source.replace(anchor, replacement))
                self.assertTrue(laws_py.violations(mutant), f"mutant survived: {label}")


class BendMutants(unittest.TestCase):
    def test_every_mutant_breaks_a_proof(self):
        if not bend_twin.bend_available():
            if os.environ.get("Z0_REQUIRE_BEND") == "1":
                self.fail("Z0_REQUIRE_BEND=1 but BEND/LEAN_BIN are not set")
            self.skipTest("BEND and LEAN_BIN not set")
        from tests.bend_verifier import verifier_environment
        model = (DOMAIN / "MODEL.bend").read_text()
        with verifier_environment(DOMAIN) as (bend, env), \
                tempfile.TemporaryDirectory(prefix="z0-kw-bendmut-") as folder:
            work = Path(folder)
            for name in ("LAWS.bend", "PROOF.bend"):
                shutil.copy2(DOMAIN / name, work / name)

            def verdict(text):
                (work / "MODEL.bend").write_text(text)
                return subprocess.run([bend, "PROOF.bend", "--verdict"], cwd=work, env=env,
                                      capture_output=True, text=True, timeout=1800)
            base = verdict(model)
            self.assertIn("ALL PROOFS CHECK", base.stdout, base.stdout + base.stderr)
            for label, anchor, replacement in BEND_MUTANTS:
                with self.subTest(mutant=label):
                    self.assertEqual(model.count(anchor), 1, f"anchor drifted: {label}")
                    out = verdict(model.replace(anchor, replacement))
                    self.assertNotIn("ALL PROOFS CHECK", out.stdout, f"mutant survived: {label}")


if __name__ == "__main__":
    unittest.main()
