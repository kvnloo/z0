"""Python statements of the onboard laws (design §11), applied to any kernel module.

Each law takes the kernel module ``k`` and raises AssertionError when it is broken.
The same functions run against the real kernel (test_kernel.py) and against
textual mutants of it (test_kernel_mutation.py), so a mutant that survives every
law here is a hole in the law set, not in the kernel.
"""
from __future__ import annotations

import itertools

BOOLS = (False, True)


def _check(cond, message):
    if not cond:
        raise AssertionError(message)


def law_h1_host_match(k):
    """H1: another host's record refuses; no fallback to its config."""
    _check(k.decide_host(k.HostMatch.OTHER) == k.refuse(k.Reason.HOST_MISMATCH),
           "H1: other-host record must refuse")
    _check(k.decide_host(k.HostMatch.SAME) == k.ALLOW, "H1: same host allows")
    _check(k.decide_host(k.HostMatch.FRESH) == k.ALLOW, "H1: fresh host allows")


def law_c0_applies(k):
    for mode, granted, source in itertools.product(k.Mode, BOOLS, k.Source):
        _check(k.decide_consent(mode, k.ConsentClass.C0, granted, source) == k.ALLOW,
               f"C0 must apply: {mode} {granted} {source}")


def law_c1_auto_never_c2(k):
    """C1: auto ∧ C2 → ask, whatever was granted and by whom."""
    for granted, source in itertools.product(BOOLS, k.Source):
        _check(k.decide_consent(k.Mode.AUTO, k.ConsentClass.C2, granted, source)
               == k.ask(k.Reason.C2_NEVER_AUTO),
               f"C1 law: auto applied C2 ({granted}, {source})")


def law_c2_flag_never_grants_c2(k):
    """--yes (a flag) grants C1 bundles only; C2 needs a per-step TTY yes."""
    for mode, granted in itertools.product(k.Mode, BOOLS):
        _check(k.decide_consent(mode, k.ConsentClass.C2, granted, k.Source.FLAG).kind is k.Kind.ASK,
               f"--yes granted C2 in {mode}")


def law_c2_grant_bound(k):
    """C2: a C1 step runs only if its bundle is granted."""
    for mode, source in itertools.product(k.Mode, k.Source):
        _check(k.decide_consent(mode, k.ConsentClass.C1, False, source)
               == k.ask(k.Reason.C1_UNGRANTED),
               f"ungranted C1 ran: {mode} {source}")


def law_c2_replan_cannot_widen(k):
    """C2: a freshness re-plan that widens grants re-confirms, even under --yes."""
    for yes in BOOLS:
        _check(k.decide_replan(True, True, yes) is k.Replan.RECONFIRM,
               f"re-plan widened grants silently (yes={yes})")
        _check(k.decide_replan(False, False, yes) is k.Replan.PROCEED, "no drift proceeds")
        _check(k.decide_replan(True, False, yes) is k.Replan.SHOW_DIFF, "drift within grants shows diff")


def law_llm_no_escalation(k):
    """L-LLM: an LLM-sourced answer is never more permissive than no grant at all."""
    for mode, cls, granted in itertools.product(k.Mode, k.ConsentClass, BOOLS):
        _check(k.decide_consent(mode, cls, granted, k.Source.LLM)
               == k.decide_consent(mode, cls, False, k.Source.TTY),
               f"LLM escalated consent: {mode} {cls} {granted}")


def law_s1_never_through_checkout(k):
    for root in (k.RootKind.CHECKOUT, k.RootKind.BUILD_TREE):
        _check(k.decide_exec_root(root) == k.refuse(k.Reason.THROUGH_CHECKOUT),
               f"S1: live code from {root}")
    _check(k.decide_exec_root(k.RootKind.OTHER) == k.refuse(k.Reason.OUTSIDE_ROOTS),
           "S1: undeclared root must refuse")
    for root in (k.RootKind.RELEASE, k.RootKind.OWNED_VENV, k.RootKind.TOOLCHAIN):
        _check(k.decide_exec_root(root) == k.ALLOW, f"S1: {root} allowed")


def law_s2_closed_bind(k):
    for ip in k.IpSource:
        for bind in (k.BindClass.WILDCARD, k.BindClass.LAN):
            _check(k.decide_bind(bind, ip) == k.refuse(k.Reason.OPEN_BIND),
                   f"S2: open bind {bind} allowed with {ip}")
        _check(k.decide_bind(k.BindClass.LOOPBACK, ip) == k.ALLOW, "S2: loopback allowed")
    _check(k.decide_bind(k.BindClass.TAILNET_IPV4, k.IpSource.CURRENT) == k.ALLOW,
           "S2: current tailnet ip allowed")
    _check(k.decide_bind(k.BindClass.TAILNET_IPV4, k.IpSource.STALE) == k.refuse(k.Reason.STALE_IP),
           "H2: stale tailnet ip must refuse")
    _check(k.decide_bind(k.BindClass.TAILNET_IPV4, k.IpSource.NONE)
           == k.unavailable(k.Reason.NO_TAILNET),
           "no tailnet: unavailable, not refused")


def law_s3_adopt_before_create(k):
    """S3: an existing unit is adopted or asked, never redeployed silently."""
    _check(k.decide_adopt(True, False) == k.ask(k.Reason.ADOPTED_OTHER_SHA),
           "S3: an adopted unit at another SHA must be asked (C2 redeploy)")
    _check(k.decide_adopt(True, True) == k.ALLOW, "S3: an adopted unit at the pin is kept")
    for same in BOOLS:
        _check(k.decide_adopt(False, same) == k.ALLOW, "S3: no unit, create it")


def law_p1_forbidden_provider(k):
    for provider in (k.Provider.GROK, k.Provider.CURSOR):
        _check(k.decide_provider(provider) == k.refuse(k.Reason.FORBIDDEN_PROVIDER),
               f"P1: {provider} not refused")
    _check(k.decide_provider(k.Provider.UNLISTED) == k.refuse(k.Reason.UNLISTED_PROVIDER),
           "unlisted provider must refuse")
    _check(k.decide_provider(k.Provider.LOCAL) == k.ALLOW, "local provider allowed")
    for provider in (k.Provider.CLAUDE, k.Provider.CODEX, k.Provider.OPENROUTER_FREE,
                     k.Provider.VERCEL_FREE):
        _check(k.decide_provider(provider) == k.ask(k.Reason.QUOTA),
               f"{provider} spends the user's account: must be confirmed")
    for raw in ("grok", "Grok", "cursor", "cursor-agent", " CURSOR-AGENT "):
        _check(k.decide_provider(k.provider_from_id(raw)) == k.refuse(k.Reason.FORBIDDEN_PROVIDER),
               f"P1: id {raw!r} not refused")


def _component_domain(k):
    return itertools.product(k.Gate, k.RevOrigin, k.Flavour, k.Maturity, k.HwClass, k.PyWindow,
                             k.RamTier)


def law_m1_m2_maturity(k):
    for gate, rev, flavour, maturity, hw, py, ram in _component_domain(k):
        verdict = k.decide_component(gate, rev, flavour, maturity, hw, py, ram)
        if maturity is k.Maturity.IDEA:
            _check(verdict == k.refuse(k.Reason.IDEA), "M1: memento-class component planned")
        if maturity is k.Maturity.SHADOW:
            _check(verdict.kind is not k.Kind.ALLOW, "M2: shadow component auto-allowed")


def law_d1_d2_dash_gates(k):
    for gate, rev, flavour, maturity, hw, py, ram in _component_domain(k):
        if maturity is k.Maturity.IDEA:
            continue
        verdict = k.decide_component(gate, rev, flavour, maturity, hw, py, ram)
        if rev is k.RevOrigin.NO:
            _check(verdict == k.unavailable(k.Reason.REV_NOT_ON_ORIGIN),
                   "D1: rev not on origin must be unavailable")
        elif rev is k.RevOrigin.UNKNOWN and gate is k.Gate.DASH:
            _check(verdict == k.unavailable(k.Reason.REV_UNVERIFIED),
                   "D1: an unverified dash rev must be unavailable (rev_unverified)")
        elif gate is k.Gate.DASH and flavour is k.Flavour.LEGACY:
            _check(verdict == k.refuse(k.Reason.LEGACY_FLAVOUR), "D2: legacy dash must refuse")


def law_z1_z0int(k):
    for _gate, _rev, flavour, maturity, hw, py, ram in _component_domain(k):
        if maturity is k.Maturity.IDEA:
            continue
        verdict = k.decide_component(k.Gate.Z0INT, k.RevOrigin.YES, flavour, maturity, hw, py, ram)
        if hw is k.HwClass.INTEL_MAC:
            _check(verdict == k.refuse(k.Reason.INTEL_MAC), "Z1: intel_mac must refuse")
        elif py is k.PyWindow.IMPOSSIBLE:
            _check(verdict == k.refuse(k.Reason.PYTHON_WINDOW), "Z1: python window must refuse")
        elif ram in (k.RamTier.LT4, k.RamTier.R4_8):
            _check(verdict == k.unavailable(k.Reason.RAM_LOW), "z0int needs ram >= 8")


def law_component_allow_exact(k):
    """Allow happens exactly when no gate fires (the table is not silently permissive)."""
    for gate, rev, flavour, maturity, hw, py, ram in _component_domain(k):
        verdict = k.decide_component(gate, rev, flavour, maturity, hw, py, ram)
        blocked = (maturity is not k.Maturity.STABLE or rev is k.RevOrigin.NO
                   or (rev is k.RevOrigin.UNKNOWN and gate is k.Gate.DASH)
                   or (gate is k.Gate.DASH and flavour is k.Flavour.LEGACY)
                   or (gate is k.Gate.Z0INT and (hw is k.HwClass.INTEL_MAC
                                                  or py is k.PyWindow.IMPOSSIBLE
                                                  or ram in (k.RamTier.LT4, k.RamTier.R4_8))))
        _check((verdict == k.ALLOW) is (not blocked),
               f"component allow mismatch: {gate} {rev} {flavour} {maturity} {hw} {py} {ram}")


def law_z2_torch_index(k):
    for hw, cuda, rocm, disk_low in itertools.product(k.HwClass, BOOLS, BOOLS, BOOLS):
        index = k.decide_torch_index(hw, cuda, rocm, disk_low)
        if hw is k.HwClass.INTEL_MAC:
            _check(index is k.TorchIndex.NONE, "Z1: no torch wheel on intel_mac")
        elif hw is k.HwClass.CPU or disk_low:
            _check(index is k.TorchIndex.CPU, f"Z2: {hw} disk_low={disk_low} must use cpu index")
        elif hw is k.HwClass.NVIDIA:
            _check(index is (k.TorchIndex.PYPI if cuda else k.TorchIndex.CPU), "nvidia index")
        elif hw is k.HwClass.AMD:
            _check(index is (k.TorchIndex.ROCM if rocm else k.TorchIndex.CPU), "amd index")
        elif hw is k.HwClass.APPLE:
            _check(index is k.TorchIndex.PYPI, "apple uses PyPI")


def law_profile(k):
    for ram, disk, hw, py in itertools.product(k.RamTier, k.DiskTier, k.HwClass, k.PyWindow):
        profile = k.decide_profile(ram, disk, hw, py)
        personal = (ram in (k.RamTier.R8_16, k.RamTier.GT16)
                    and disk in (k.DiskTier.D10_40, k.DiskTier.GT40)
                    and hw is not k.HwClass.INTEL_MAC and py is not k.PyWindow.IMPOSSIBLE)
        if personal:
            want = k.Profile.PERSONAL
        elif disk is not k.DiskTier.LT3:
            want = k.Profile.CORE
        else:
            want = k.Profile.REFUSE
        _check(profile is want, f"profile {ram} {disk} {hw} {py}: {profile} != {want}")


def law_tiers(k):
    _check(k.ram_tier(3.9) is k.RamTier.LT4, "ram <4")
    _check(k.ram_tier(4) is k.RamTier.R4_8, "ram 4")
    _check(k.ram_tier(7.99) is k.RamTier.R4_8, "ram <8")
    _check(k.ram_tier(8) is k.RamTier.R8_16, "ram 8")
    _check(k.ram_tier(16) is k.RamTier.R8_16, "ram 16")
    _check(k.ram_tier(16.5) is k.RamTier.GT16, "ram >16")
    _check(k.disk_tier(2.9) is k.DiskTier.LT3, "disk <3")
    _check(k.disk_tier(3) is k.DiskTier.D3_10, "disk 3")
    _check(k.disk_tier(10) is k.DiskTier.D10_40, "disk 10")
    _check(k.disk_tier(40) is k.DiskTier.D10_40, "disk 40")
    _check(k.disk_tier(41) is k.DiskTier.GT40, "disk >40")
    _check(k.host_match(None, "abc") is k.HostMatch.FRESH, "no record is fresh")
    _check(k.host_match("abc", "abc") is k.HostMatch.SAME, "same id")
    _check(k.host_match("abd", "abc") is k.HostMatch.OTHER, "other id")
    _check(k.host_match("abc", None) is k.HostMatch.OTHER, "unknown current host never matches")


LAWS = [value for name, value in sorted(globals().items()) if name.startswith("law_")]
