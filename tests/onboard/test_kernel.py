"""Pure kernel tests: every law over every domain row, no Bend needed (design §10 layer 1)."""
from __future__ import annotations

import ast
import itertools
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from z0.onboard import kernel as k  # noqa: E402

from tests.onboard import kernel_laws  # noqa: E402


class KernelLaws(unittest.TestCase):
    def test_every_law_holds(self):
        self.assertGreaterEqual(len(kernel_laws.LAWS), 15)
        for law in kernel_laws.LAWS:
            with self.subTest(law=law.__name__):
                law(k)


class KernelTotality(unittest.TestCase):
    """Every decide_* answers a well-formed value on every row of its domain."""

    def test_domains_are_total_and_codes_unique(self):
        for name, domain in k.DOMAINS.items():
            fn = getattr(k, name)
            rows = list(itertools.product(*domain))
            self.assertTrue(rows, name)
            for row in rows:
                result = fn(*row)
                code = k.code(result)
                self.assertIsInstance(code, int, (name, row))
        self.assertEqual(sum(len(list(itertools.product(*d))) for d in k.DOMAINS.values()),
                         k.DOMAIN_ROWS)

    def test_verdict_codes_are_lossless(self):
        seen = {}
        for kind in k.Kind:
            for reason in [None, *k.Reason]:
                if (kind is k.Kind.ALLOW) != (reason is None):
                    continue
                code = k.code(k.Verdict(kind, reason))
                self.assertNotIn(code, seen, (kind, reason, seen.get(code)))
                seen[code] = (kind, reason)

    def test_verdict_shape_is_enforced(self):
        with self.assertRaises(ValueError):
            k.Verdict(k.Kind.ALLOW, k.Reason.QUOTA)
        with self.assertRaises(ValueError):
            k.Verdict(k.Kind.REFUSE, None)

    def test_largest_domain_matches_design(self):
        # §11 sized it at 2,160 rows with a boolean rev; the rev axis is now
        # yes/no/unknown (rev_unverified), so 3·3·2·3·5·3·4 = 3,240.
        self.assertEqual(len(list(itertools.product(*k.DOMAINS["decide_component"]))), 3240)


class KernelIsOnlyDecider(unittest.TestCase):
    """§11: lib/z0/onboard/kernel.py is the only code that builds a verdict."""

    def test_no_other_module_constructs_verdicts(self):
        onboard = ROOT / "lib/z0/onboard"
        offenders = []
        for path in onboard.rglob("*.py"):
            if path.name == "kernel.py":
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                    if name in {"Verdict", "refuse", "ask", "unavailable"}:
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_kernel_is_pure(self):
        source = (ROOT / "lib/z0/onboard/kernel.py").read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "dataclasses", "enum", "typing"})


if __name__ == "__main__":
    unittest.main()
