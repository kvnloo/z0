"""Each mutant re-opens a "ready too early" path and must be rejected (spec §4.4).

Two lanes, both on scratch copies only:
- Bend: each MODEL.bend mutant must make the unchanged LAWS/PROOF print SOME PROOFS
  FAIL under `bend PROOF.bend --verdict`. A valid reference verdict is mandatory
  first, and a toolchain crash never counts as a rejection. Needs BEND and LEAN_BIN
  (Z0_REQUIRE_BEND=1 turns a skip into a failure).
- Python: each scripts/contrib_ready.py mutant, loaded as a throwaway module, must
  break at least one law in tests/contrib_ready/laws.py. Always runs.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.contrib_ready import laws, twin

# (label, anchor, replacement) on MODEL.bend.
BEND_MUTANTS = [
    ("stale pass counts",
     "    case CPassOtherSha{}:\n      False{}\n    case CPassCandidate{}:\n      True{}",
     "    case CPassOtherSha{}:\n      True{}\n    case CPassCandidate{}:\n      True{}"),
    ("half pair counts (z0int sha ignored)",
     "          CPassCandidate{}\n        case False{}:\n          CPassOtherSha{}",
     "          CPassCandidate{}\n        case False{}:\n          CPassCandidate{}"),
    ("missing receipt counts",
     "    case OMissing{}:\n      CNone{}",
     "    case OMissing{}:\n      CPassCandidate{}"),
    ("stale pass upgrades a missing cell on merge",
     "    case CNone{}:\n      CPassOtherSha{}",
     "    case CNone{}:\n      CPassCandidate{}"),
    ("candidate fail hidden by a pass",
     "    case CFail{}:\n      CFail{}\n    case CPassOtherSha{}:\n      CPassCandidate{}",
     "    case CFail{}:\n      CPassCandidate{}\n    case CPassOtherSha{}:\n      CPassCandidate{}"),
    ("one cell skipped by all_count",
     "      Bool.and(counts(c), all_count(rest))",
     "      all_count(rest)"),
    ("shape ignored (missing cells pass)",
     "  Bool.and(all_count(cs), shape_ok(cs, 0n))",
     "  all_count(cs)"),
    ("REQUIRED shrunk to 31",
     "def required_count() -> Nat:\n  32n",
     "def required_count() -> Nat:\n  31n"),
    ("owner blocker gives ready",
     "    case BOwner{}:\n      SBlockedOwner{}",
     "    case BOwner{}:\n      ready_if(ok)"),
    ("reasonless blocker gives ready",
     "    case BNoReason{}:\n      SNotReady{}",
     "    case BNoReason{}:\n      ready_if(ok)"),
]

# (label, anchor, replacement) on scripts/contrib_ready.py; the same paths in the twin.
PYTHON_MUTANTS = [
    ("stale pass counts",
     "    return cell is Cell.PASS_CANDIDATE",
     "    return cell in (Cell.PASS_CANDIDATE, Cell.PASS_OTHER_SHA)"),
    ("half pair counts",
     "    same = z0_same and z0int_same",
     "    same = z0_same or z0int_same"),
    ("pass on any pair counts",
     "    return Cell.PASS_CANDIDATE if same else Cell.PASS_OTHER_SHA",
     "    return Cell.PASS_CANDIDATE"),
    ("unknown receipt status counts as pass",
     '.get(status, Outcome.FAIL)',
     '.get(status, Outcome.PASS)'),
    ("candidate fail hidden by a pass",
     "Cell.PASS_CANDIDATE: 2, Cell.FAIL: 3}",
     "Cell.PASS_CANDIDATE: 3, Cell.FAIL: 2}"),
    ("shape ignored",
     "    return all_count(cells) and shape_ok(cells)",
     "    return all_count(cells)"),
    ("subset of REQUIRED accepted",
     "    return codes == list(range(start, required_count()))",
     "    return set(codes) <= set(range(start, required_count()))"),
    ("REQUIRED shrunk",
     '("W1", "QW1"), ("LAWS_CI", "QLawsCi")])',
     '("W1", "QW1")])'),
    ("owner blocker ignored",
     "    if blocker is Blocker.OWNER:\n        return Status.BLOCKED_OWNER",
     "    if blocker is Blocker.OWNER:\n        return ready_if(ok)"),
    ("reasonless blocker ignored",
     "    return Status.NOT_READY\n\n\ndef decide(",
     "    return ready_if(ok)\n\n\ndef decide("),
    ("reasonless blocker record dropped",
     "    if not isinstance(reason, str) or not reason.strip():\n        return Blocker.NO_REASON",
     "    if not isinstance(reason, str) or not reason.strip():\n        return Blocker.NONE"),
    ("short sha announced",
     'SHA = re.compile(r"[0-9a-f]{40}")',
     'SHA = re.compile(r"[0-9a-f]{7,40}")'),
]


def _broken_laws(module):
    broken = []
    for law in laws.LAWS:
        try:
            law(module)
        except AssertionError:
            broken.append(law.__name__)
    return broken


class PythonMutants(unittest.TestCase):
    def test_reference_twin_passes_every_law(self):
        self.assertEqual(_broken_laws(twin.load(twin.SCRIPT.read_text())), [])

    def test_every_mutant_is_rejected(self):
        source = twin.SCRIPT.read_text()
        for label, old, new in PYTHON_MUTANTS:
            with self.subTest(mutant=label):
                self.assertEqual(source.count(old), 1, f"{label}: anchor changed; review twin diff")
                broken = _broken_laws(twin.load(source.replace(old, new)))
                self.assertTrue(broken, f"{label}: mutant survived every law")
                print(f"z0 contrib_ready: python mutant rejected: {label} ({', '.join(broken)})",
                      file=sys.stderr)


def _verify(bend, cwd, env):
    return subprocess.run([bend, "PROOF.bend", "--verdict"], cwd=cwd,
                          capture_output=True, text=True, env=env, timeout=1800)


class BendMutants(unittest.TestCase):
    def test_bend_mutants_fail_the_unchanged_laws(self):
        if not twin.bend_available():
            if os.environ.get("Z0_REQUIRE_BEND") == "1":
                self.fail("Z0_REQUIRE_BEND=1 but BEND/LEAN_BIN are not set")
            self.skipTest("BEND and LEAN_BIN not set")
        from tests.bend_verifier import verifier_environment
        with verifier_environment(twin.DOMAIN) as (bend, env), \
                tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            for filename in ("MODEL.bend", "LAWS.bend", "PROOF.bend"):
                shutil.copy2(twin.DOMAIN / filename, scratch / filename)
            reference = _verify(bend, scratch, env)
            output = reference.stdout + reference.stderr
            self.assertTrue(reference.returncode == 0 and "ALL PROOFS CHECK" in output.splitlines()
                            and "SOME PROOFS FAIL" not in output.splitlines(),
                            "reference proof failed: " + output[-2000:])
            source = (scratch / "MODEL.bend").read_text()
            for label, old, broken in BEND_MUTANTS:
                with self.subTest(mutant=label):
                    self.assertEqual(source.count(old), 1, f"{label}: anchor changed; review model diff")
                    (scratch / "MODEL.bend").write_text(source.replace(old, broken))
                    mutant = _verify(bend, scratch, env)
                    lines = (mutant.stdout + mutant.stderr).splitlines()
                    # A compiler/toolchain crash is not evidence of a rejected law.
                    self.assertTrue(mutant.returncode != 0 and "SOME PROOFS FAIL" in lines
                                    and "ALL PROOFS CHECK" not in lines,
                                    f"{label}: no explicit failed-proof verdict: "
                                    + (mutant.stdout + mutant.stderr)[-2000:])
                    print(f"z0 contrib_ready: bend mutant rejected: {label}", file=sys.stderr)
            (scratch / "MODEL.bend").write_text(source)


if __name__ == "__main__":
    unittest.main()
