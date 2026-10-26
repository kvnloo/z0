"""Each mutant re-opens a known onboarding failure path and must be rejected (design §11).

Two lanes, both on scratch copies only:
- Bend: each MODEL.bend mutant must make the unchanged LAWS/PROOF print SOME PROOFS FAIL
  under `bend PROOF.bend --verdict`. A valid reference verdict is mandatory first, and a
  toolchain crash never counts as a rejection. Needs BEND and LEAN_BIN (Z0_REQUIRE_BEND=1
  turns a skip into a failure).
- Python: each kernel.py mutant, loaded as a throwaway module, must break at least one law
  in tests/onboard/kernel_laws.py. Always runs.
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

from tests.onboard import kernel_laws  # noqa: E402

DOMAIN = ROOT / "bend/onboard"
KERNEL = ROOT / "lib/z0/onboard/kernel.py"

# (label, anchor, replacement) on MODEL.bend.
BEND_MUTANTS = [
    ("other-host fallback",
     "    case HOther{}:\n      VRefuse{RHostMismatch{}}",
     "    case HOther{}:\n      VAllow{}"),
    ("exec through checkout",
     "    case RkCheckout{}:\n      VRefuse{RThroughCheckout{}}",
     "    case RkCheckout{}:\n      VAllow{}"),
    ("exec through build tree",
     "    case RkBuildTree{}:\n      VRefuse{RThroughCheckout{}}",
     "    case RkBuildTree{}:\n      VAllow{}"),
    ("open bind (wildcard)",
     "    case BWildcard{}:\n      VRefuse{ROpenBind{}}",
     "    case BWildcard{}:\n      VAllow{}"),
    ("open bind (lan)",
     "    case BLan{}:\n      VRefuse{ROpenBind{}}",
     "    case BLan{}:\n      VAllow{}"),
    ("stale tailnet ip bind",
     "        case IpStale{}:\n          VRefuse{RStaleIp{}}",
     "        case IpStale{}:\n          VAllow{}"),
    ("auto applies C2",
     "    case MAuto{}:\n      VAsk{RC2NeverAuto{}}",
     "    case MAuto{}:\n      granted_or(granted, RC2NeverAuto{})"),
    ("grant widening: --yes applies an ungranted C1 bundle",
     "    case SrcFlag{}:\n      granted_or(granted, RC1Ungranted{})",
     "    case SrcFlag{}:\n      VAllow{}"),
    ("grant widening: --yes grants C2 in guided",
     "        case SrcFlag{}:\n          VAsk{RC2Confirm{}}",
     "        case SrcFlag{}:\n          granted_or(granted, RC2Confirm{})"),
    ("grant widening: re-plan widens without re-confirm",
     "        case True{}:\n          RpReconfirm{}",
     "        case True{}:\n          RpShowDiff{}"),
    ("LLM escalation (C1)",
     "    case SrcLlm{}:\n      VAsk{RC1Ungranted{}}",
     "    case SrcLlm{}:\n      granted_or(granted, RC1Ungranted{})"),
    ("LLM escalation (C2 guided)",
     "        case SrcLlm{}:\n          VAsk{RC2Confirm{}}",
     "        case SrcLlm{}:\n          granted_or(granted, RC2Confirm{})"),
    ("grok allowed",
     "    case PvGrok{}:\n      VRefuse{RForbiddenProvider{}}",
     "    case PvGrok{}:\n      VAsk{RQuota{}}"),
    ("cursor allowed",
     "    case PvCursor{}:\n      VRefuse{RForbiddenProvider{}}",
     "    case PvCursor{}:\n      VAllow{}"),
    ("memento planned",
     "    case MtIdea{}:\n      VRefuse{RIdea{}}",
     "    case MtIdea{}:\n      component_gates(gate, rev, flavour, hw, py, ram)"),
    ("shadow auto-allowed",
     "    case VAllow{}:\n      VAsk{RShadow{}}",
     "    case VAllow{}:\n      VAllow{}"),
    ("legacy dash deployed",
     "    case FLegacy{}:\n      VRefuse{RLegacyFlavour{}}",
     "    case FLegacy{}:\n      VAllow{}"),
    ("dash rev not on origin deployed",
     "    case OriginNo{}:\n      VUnavailable{RRevNotOnOrigin{}}",
     "    case OriginNo{}:\n      component_gate(gate, flavour, hw, py, ram)"),
    ("unverified dash rev deployed",
     "    case GDash{}:\n      VUnavailable{RRevUnverified{}}",
     "    case GDash{}:\n      dash_flavour(flavour)"),
    ("unverified dash rev reported as not on origin",
     "    case GDash{}:\n      VUnavailable{RRevUnverified{}}",
     "    case GDash{}:\n      VUnavailable{RRevNotOnOrigin{}}"),
    ("z0int on intel mac",
     "    case HwIntelMac{}:\n      VRefuse{RIntelMac{}}",
     "    case HwIntelMac{}:\n      z0int_py(py, ram)"),
    ("cuda torch on cpu class",
     "    case HwCpu{}:\n      IxCpu{}",
     "    case HwCpu{}:\n      IxPypi{}"),
]

# (label, anchor, replacement) on kernel.py; the same failure paths in the twin.
PYTHON_MUTANTS = [
    ("other-host fallback",
     "    if match is HostMatch.OTHER:\n        return refuse(Reason.HOST_MISMATCH)",
     "    if match is HostMatch.OTHER:\n        return ALLOW"),
    ("exec through checkout",
     "    if root in (RootKind.CHECKOUT, RootKind.BUILD_TREE):\n"
     "        return refuse(Reason.THROUGH_CHECKOUT)",
     "    if root in (RootKind.CHECKOUT, RootKind.BUILD_TREE):\n        return ALLOW"),
    ("open bind",
     "    if bind in (BindClass.WILDCARD, BindClass.LAN):\n        return refuse(Reason.OPEN_BIND)",
     "    if bind in (BindClass.WILDCARD, BindClass.LAN):\n        return ALLOW"),
    ("auto applies C2",
     "    if mode is Mode.AUTO:\n        return ask(Reason.C2_NEVER_AUTO)",
     "    if mode is Mode.AUTO:\n        return _granted_or(granted, Reason.C2_NEVER_AUTO)"),
    ("grant widening: --yes applies an ungranted C1 bundle",
     "        return _granted_or(granted, Reason.C1_UNGRANTED)",
     "        return ALLOW"),
    ("grant widening: re-plan widens without re-confirm",
     "    return Replan.RECONFIRM if widens else Replan.SHOW_DIFF",
     "    return Replan.RECONFIRM if widens and not yes else Replan.SHOW_DIFF"),
    ("LLM escalation",
     "        if source is Source.LLM:\n            return ask(Reason.C1_UNGRANTED)\n",
     ""),
    ("rev not on origin deployed",
     "    if rev is RevOrigin.NO:\n        return unavailable(Reason.REV_NOT_ON_ORIGIN)\n",
     ""),
    ("unverified dash rev deployed",
     "    if rev is RevOrigin.UNKNOWN and gate is Gate.DASH:\n"
     "        return unavailable(Reason.REV_UNVERIFIED)\n",
     ""),
    ("unverified dash rev reported as not on origin",
     "        return unavailable(Reason.REV_UNVERIFIED)",
     "        return unavailable(Reason.REV_NOT_ON_ORIGIN)"),
    ("grok/cursor allowed",
     "FORBIDDEN_PROVIDERS = frozenset({Provider.GROK, Provider.CURSOR})",
     "FORBIDDEN_PROVIDERS = frozenset()"),
    ("grok id spelled differently",
     '    "grok": Provider.GROK,',
     '    "grok-cli": Provider.GROK,'),
]


def _load_mutant(source, folder):
    path = Path(folder) / "kernel_mutant.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(f"kernel_mutant_{abs(hash(source))}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _broken_laws(module):
    broken = []
    for law in kernel_laws.LAWS:
        try:
            law(module)
        except AssertionError:
            broken.append(law.__name__)
    return broken


class PythonMutants(unittest.TestCase):
    def test_reference_kernel_passes_every_law(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(_broken_laws(_load_mutant(KERNEL.read_text(), folder)), [])

    def test_every_mutant_is_rejected(self):
        source = KERNEL.read_text()
        with tempfile.TemporaryDirectory() as folder:
            for label, old, new in PYTHON_MUTANTS:
                with self.subTest(mutant=label):
                    self.assertEqual(source.count(old), 1, f"{label}: anchor changed; review kernel diff")
                    module = _load_mutant(source.replace(old, new), folder)
                    broken = _broken_laws(module)
                    self.assertTrue(broken, f"{label}: mutant survived every law")
                    print(f"z0 onboard: python mutant rejected: {label} ({', '.join(broken)})",
                          file=sys.stderr)


def _verify(bend, cwd, env):
    return subprocess.run([bend, "PROOF.bend", "--verdict"], cwd=cwd,
                          capture_output=True, text=True, env=env, timeout=1800)


class BendMutants(unittest.TestCase):
    def test_bend_mutants_fail_the_unchanged_laws(self):
        if not (os.environ.get("BEND") and os.environ.get("LEAN_BIN")):
            if os.environ.get("Z0_REQUIRE_BEND") == "1":
                self.fail("Z0_REQUIRE_BEND=1 but BEND/LEAN_BIN are not set")
            self.skipTest("BEND and LEAN_BIN not set")
        from tests.bend_verifier import verifier_environment
        with verifier_environment(DOMAIN) as (bend, env), tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            for filename in ("MODEL.bend", "LAWS.bend", "PROOF.bend"):
                shutil.copy2(DOMAIN / filename, scratch / filename)
            reference = _verify(bend, scratch, env)
            output = reference.stdout + reference.stderr
            self.assertTrue(reference.returncode == 0 and reference.stdout.strip() == "ALL PROOFS CHECK"
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
                    print(f"z0 onboard: bend mutant rejected: {label}", file=sys.stderr)
            (scratch / "MODEL.bend").write_text(source)


if __name__ == "__main__":
    unittest.main()
