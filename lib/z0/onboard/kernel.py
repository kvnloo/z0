"""The onboard kernel: the ONLY code that decides refuse / ask / allow (design §11).

Every decision is a small finite function over enums and booleans. Its twin is
bend/onboard/MODEL.bend; tests/onboard/test_kernel_twin.py runs every row of every
domain (DOMAINS) through both and compares the lossless codes. Change the two
together, then run the laws (bend/onboard/PROOF.bend --verdict) and the twin parity.

Enum values are the Bend constructor names, in the Bend declaration order (that
order is the code order). The kernel is pure: no I/O, no environment, stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Mode(Enum):
    AUTO = "MAuto"
    GUIDED = "MGuided"


class ConsentClass(Enum):
    C0 = "C0"  # z0-private
    C1 = "C1"  # user-scoped, reversible, bundled
    C2 = "C2"  # never automatic


class Source(Enum):
    """Who granted: a per-step TTY yes, a flag (--yes/--accept), or an LLM answer."""
    TTY = "SrcTty"
    FLAG = "SrcFlag"
    LLM = "SrcLlm"


class HostMatch(Enum):
    FRESH = "HFresh"  # no recorded host_id
    SAME = "HSame"
    OTHER = "HOther"


class BindClass(Enum):
    LOOPBACK = "BLoopback"
    TAILNET_IPV4 = "BTailnet"
    WILDCARD = "BWildcard"
    LAN = "BLan"


class IpSource(Enum):
    CURRENT = "IpCurrent"  # from this run's detection
    STALE = "IpStale"      # recorded, or from another host
    NONE = "IpNone"


class RootKind(Enum):
    RELEASE = "RkRelease"
    OWNED_VENV = "RkOwnedVenv"
    TOOLCHAIN = "RkToolchain"
    CHECKOUT = "RkCheckout"     # has a .git ancestor
    BUILD_TREE = "RkBuildTree"  # z0-owned, but has .git
    OTHER = "RkOther"


class Provider(Enum):
    LOCAL = "PvLocal"
    CLAUDE = "PvClaude"
    CODEX = "PvCodex"
    OPENROUTER_FREE = "PvOpenRouterFree"
    VERCEL_FREE = "PvVercelFree"
    GROK = "PvGrok"
    CURSOR = "PvCursor"
    UNLISTED = "PvUnlisted"


class Gate(Enum):
    GENERIC = "GGeneric"
    DASH = "GDash"
    Z0INT = "GZ0int"


class Flavour(Enum):
    CURRENT = "FCurrent"
    LEGACY = "FLegacy"


class RevOrigin(Enum):
    """Evidence that a pinned rev is on origin: proven, disproven, or not checked."""
    YES = "OriginYes"
    NO = "OriginNo"
    UNKNOWN = "OriginUnknown"


class Maturity(Enum):
    STABLE = "MtStable"  # stable or canary
    SHADOW = "MtShadow"
    IDEA = "MtIdea"


class HwClass(Enum):
    NVIDIA = "HwNvidia"
    AMD = "HwAmd"
    APPLE = "HwApple"
    INTEL_MAC = "HwIntelMac"
    CPU = "HwCpu"


class PyWindow(Enum):
    """A python in [3.10, 3.14): present, makeable (uv), or impossible."""
    PRESENT = "PyPresent"
    MAKEABLE = "PyMakeable"
    IMPOSSIBLE = "PyImpossible"


class RamTier(Enum):
    LT4 = "RamLt4"
    R4_8 = "Ram4to8"
    R8_16 = "Ram8to16"
    GT16 = "RamGt16"


class DiskTier(Enum):
    LT3 = "DiskLt3"
    D3_10 = "Disk3to10"
    D10_40 = "Disk10to40"
    GT40 = "DiskGt40"


class Reason(Enum):
    HOST_MISMATCH = "RHostMismatch"
    C2_NEVER_AUTO = "RC2NeverAuto"
    C2_CONFIRM = "RC2Confirm"
    C1_UNGRANTED = "RC1Ungranted"
    OPEN_BIND = "ROpenBind"
    STALE_IP = "RStaleIp"
    NO_TAILNET = "RNoTailnet"
    THROUGH_CHECKOUT = "RThroughCheckout"
    OUTSIDE_ROOTS = "ROutsideRoots"
    FORBIDDEN_PROVIDER = "RForbiddenProvider"
    UNLISTED_PROVIDER = "RUnlistedProvider"
    QUOTA = "RQuota"
    IDEA = "RIdea"
    REV_NOT_ON_ORIGIN = "RRevNotOnOrigin"
    LEGACY_FLAVOUR = "RLegacyFlavour"
    INTEL_MAC = "RIntelMac"
    PYTHON_WINDOW = "RPythonWindow"
    RAM_LOW = "RRamLow"
    SHADOW = "RShadow"
    REV_UNVERIFIED = "RRevUnverified"
    ADOPTED_OTHER_SHA = "RAdoptedOtherSha"


class Kind(Enum):
    ALLOW = "VAllow"
    ASK = "VAsk"
    UNAVAILABLE = "VUnavailable"
    REFUSE = "VRefuse"


class Profile(Enum):
    PERSONAL = "PfPersonal"
    CORE = "PfCore"
    REFUSE = "PfRefuse"


class TorchIndex(Enum):
    CPU = "IxCpu"
    PYPI = "IxPypi"
    ROCM = "IxRocm"
    NONE = "IxNone"


class Replan(Enum):
    PROCEED = "RpProceed"
    SHOW_DIFF = "RpShowDiff"
    RECONFIRM = "RpReconfirm"


@dataclass(frozen=True)
class Verdict:
    kind: Kind
    reason: Optional[Reason] = None

    def __post_init__(self):
        if (self.kind is Kind.ALLOW) != (self.reason is None):
            raise ValueError("ALLOW carries no reason; every other verdict carries one")


ALLOW = Verdict(Kind.ALLOW)


def ask(reason: Reason) -> Verdict:
    return Verdict(Kind.ASK, reason)


def unavailable(reason: Reason) -> Verdict:
    return Verdict(Kind.UNAVAILABLE, reason)


def refuse(reason: Reason) -> Verdict:
    return Verdict(Kind.REFUSE, reason)


# --- H1 ------------------------------------------------------------------------

def decide_host(match: HostMatch) -> Verdict:
    """A record from another host refuses (exit 4); never fall back to its config."""
    if match is HostMatch.OTHER:
        return refuse(Reason.HOST_MISMATCH)
    return ALLOW


# --- consent (C1, C2, L-LLM) ---------------------------------------------------

def _granted_or(granted: bool, reason: Reason) -> Verdict:
    return ALLOW if granted else ask(reason)


def decide_consent(mode: Mode, cls: ConsentClass, granted: bool, source: Source) -> Verdict:
    """C0 applies; C1 needs its bundle granted by a person; C2 is never automatic.

    An LLM answer is never a grant (L-LLM). A flag (--yes) never grants C2.
    """
    if cls is ConsentClass.C0:
        return ALLOW
    if cls is ConsentClass.C1:
        if source is Source.LLM:
            return ask(Reason.C1_UNGRANTED)
        return _granted_or(granted, Reason.C1_UNGRANTED)
    if mode is Mode.AUTO:
        return ask(Reason.C2_NEVER_AUTO)
    if source is Source.TTY:
        return _granted_or(granted, Reason.C2_CONFIRM)
    return ask(Reason.C2_CONFIRM)


def decide_replan(drift: bool, widens: bool, yes: bool) -> Replan:
    """Freshness re-plan (§6.3): within grants show the diff; widening re-confirms.

    `yes` is deliberately ignored: --yes cannot widen a grant.
    """
    _ = yes
    if not drift:
        return Replan.PROCEED
    return Replan.RECONFIRM if widens else Replan.SHOW_DIFF


# --- S1, S2/H2 -----------------------------------------------------------------

def decide_bind(bind: BindClass, ip: IpSource) -> Verdict:
    if bind in (BindClass.WILDCARD, BindClass.LAN):
        return refuse(Reason.OPEN_BIND)
    if bind is BindClass.LOOPBACK:
        return ALLOW
    if ip is IpSource.CURRENT:
        return ALLOW
    if ip is IpSource.STALE:
        return refuse(Reason.STALE_IP)
    return unavailable(Reason.NO_TAILNET)


def decide_exec_root(root: RootKind) -> Verdict:
    """Units, shim, plugins and env files point only at releases, owned venvs, toolchains."""
    if root in (RootKind.CHECKOUT, RootKind.BUILD_TREE):
        return refuse(Reason.THROUGH_CHECKOUT)
    if root is RootKind.OTHER:
        return refuse(Reason.OUTSIDE_ROOTS)
    return ALLOW


# --- S3 ------------------------------------------------------------------------

def decide_adopt(unit_exists: bool, same_sha: bool) -> Verdict:
    """An existing unit with the same name is adopted, never duplicated (S3).

    No unit: ALLOW (create it). A unit at the pinned SHA: ALLOW (kept as it is; the plan
    marks the step already_satisfied). A unit at another SHA: redeploying it is C2, so
    ask; the consent decision for that C2 step follows (decide_consent).
    """
    if unit_exists and not same_sha:
        return ask(Reason.ADOPTED_OTHER_SHA)
    return ALLOW


# --- P1 ------------------------------------------------------------------------

FORBIDDEN_PROVIDERS = frozenset({Provider.GROK, Provider.CURSOR})
REMOTE_PROVIDERS = frozenset({Provider.CLAUDE, Provider.CODEX, Provider.OPENROUTER_FREE,
                              Provider.VERCEL_FREE})

_PROVIDER_IDS = {
    "local": Provider.LOCAL,
    "claude": Provider.CLAUDE,
    "claude-code": Provider.CLAUDE,
    "codex": Provider.CODEX,
    "openrouter-free": Provider.OPENROUTER_FREE,
    "vercel-free": Provider.VERCEL_FREE,
    "grok": Provider.GROK,
    "cursor": Provider.CURSOR,
    "cursor-agent": Provider.CURSOR,
}


def provider_from_id(raw: str) -> Provider:
    """Map a registry/harness id to a Provider. Unknown ids are UNLISTED (refused)."""
    return _PROVIDER_IDS.get(raw.strip().lower(), Provider.UNLISTED)


def decide_provider(provider: Provider) -> Verdict:
    """grok and cursor are refused in every role; remote providers need consent."""
    if provider in FORBIDDEN_PROVIDERS:
        return refuse(Reason.FORBIDDEN_PROVIDER)
    if provider in REMOTE_PROVIDERS:
        return ask(Reason.QUOTA)
    if provider is Provider.LOCAL:
        return ALLOW
    return refuse(Reason.UNLISTED_PROVIDER)


# --- components (M1, M2, D1, D2, Z1) -------------------------------------------

def _component_gates(gate, rev, flavour, hw, py, ram) -> Verdict:
    if rev is RevOrigin.NO:
        return unavailable(Reason.REV_NOT_ON_ORIGIN)
    if rev is RevOrigin.UNKNOWN and gate is Gate.DASH:
        return unavailable(Reason.REV_UNVERIFIED)
    if gate is Gate.DASH and flavour is Flavour.LEGACY:
        return refuse(Reason.LEGACY_FLAVOUR)
    if gate is Gate.Z0INT:
        if hw is HwClass.INTEL_MAC:
            return refuse(Reason.INTEL_MAC)
        if py is PyWindow.IMPOSSIBLE:
            return refuse(Reason.PYTHON_WINDOW)
        if ram in (RamTier.LT4, RamTier.R4_8):
            return unavailable(Reason.RAM_LOW)
    return ALLOW


def decide_component(gate: Gate, rev: RevOrigin, flavour: Flavour, maturity: Maturity,
                     hw: HwClass, py: PyWindow, ram: RamTier) -> Verdict:
    """rev: is every pin on origin? A dash rev that was never checked is unavailable
    with its own reason (rev_unverified); other gates proceed and the plan warns."""
    if maturity is Maturity.IDEA:
        return refuse(Reason.IDEA)
    verdict = _component_gates(gate, rev, flavour, hw, py, ram)
    if maturity is Maturity.SHADOW and verdict == ALLOW:
        return ask(Reason.SHADOW)
    return verdict


# --- §5.2 hardware decisions ---------------------------------------------------

def decide_profile(ram: RamTier, disk: DiskTier, hw: HwClass, py: PyWindow) -> Profile:
    """Auto default profile: personal, else core when disk >= 3 GiB, else refuse."""
    if disk is DiskTier.LT3:
        return Profile.REFUSE
    if (disk in (DiskTier.D10_40, DiskTier.GT40) and ram in (RamTier.R8_16, RamTier.GT16)
            and hw is not HwClass.INTEL_MAC and py is not PyWindow.IMPOSSIBLE):
        return Profile.PERSONAL
    return Profile.CORE


def decide_torch_index(hw: HwClass, cuda_ok: bool, rocm: bool, disk_low: bool) -> TorchIndex:
    """torch==2.10.0 index. cuda_ok: driver supports CUDA >= 12.8. disk_low: < 10 GiB."""
    if hw is HwClass.INTEL_MAC:
        return TorchIndex.NONE
    if hw is HwClass.CPU or disk_low:
        return TorchIndex.CPU
    if hw is HwClass.NVIDIA:
        return TorchIndex.PYPI if cuda_ok else TorchIndex.CPU
    if hw is HwClass.AMD:
        return TorchIndex.ROCM if rocm else TorchIndex.CPU
    return TorchIndex.PYPI


# --- fact -> enum helpers (pure) -----------------------------------------------

def host_match(recorded: Optional[str], current: Optional[str]) -> HostMatch:
    """A record exists but the current host_id is unknown: never a match."""
    if recorded is None:
        return HostMatch.FRESH
    return HostMatch.SAME if current is not None and recorded == current else HostMatch.OTHER


def ram_tier(gib: float) -> RamTier:
    if gib < 4:
        return RamTier.LT4
    if gib < 8:
        return RamTier.R4_8
    return RamTier.R8_16 if gib <= 16 else RamTier.GT16


def disk_tier(gib: float) -> DiskTier:
    if gib < 3:
        return DiskTier.LT3
    if gib < 10:
        return DiskTier.D3_10
    return DiskTier.D10_40 if gib <= 40 else DiskTier.GT40


# --- domains and lossless codes (twin parity) ----------------------------------

BOOL = (False, True)

DOMAINS = {
    "decide_host": (HostMatch,),
    "decide_consent": (Mode, ConsentClass, BOOL, Source),
    "decide_replan": (BOOL, BOOL, BOOL),
    "decide_bind": (BindClass, IpSource),
    "decide_exec_root": (RootKind,),
    "decide_adopt": (BOOL, BOOL),
    "decide_provider": (Provider,),
    "decide_component": (Gate, RevOrigin, Flavour, Maturity, HwClass, PyWindow, RamTier),
    "decide_profile": (RamTier, DiskTier, HwClass, PyWindow),
    "decide_torch_index": (HwClass, BOOL, BOOL, BOOL),
}
DOMAIN_ROWS = 3 + 36 + 8 + 12 + 6 + 4 + 8 + 3240 + 240 + 40

_KIND_CODE = {kind: index for index, kind in enumerate(Kind)}
_REASON_CODE = {reason: index + 1 for index, reason in enumerate(Reason)}


def code(result) -> int:
    """Lossless integer code, equal to MODEL.bend's code_* for the same value."""
    if isinstance(result, Verdict):
        return 100 * _KIND_CODE[result.kind] + (0 if result.reason is None
                                                else _REASON_CODE[result.reason])
    if isinstance(result, (Profile, TorchIndex, Replan)):
        return list(type(result)).index(result)
    raise TypeError(f"no code for {result!r}")
