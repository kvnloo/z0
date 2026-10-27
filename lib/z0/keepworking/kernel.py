"""Twin of bend/keepworking/MODEL.bend: the ONLY code that decides block/allow.

Each decide function is a small finite function over enums and bools. The twin test
runs every row of DOMAINS through this file and through the pinned Bend model.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(Enum):
    OPEN = "SOpen"
    PARTIAL = "SPartial"
    DONE = "SDone"
    BLOCKED = "SBlocked"
    UNKNOWN = "SUnknown"


class Evidence(Enum):
    NONE = "EvNone"
    WEAK = "EvWeak"
    OWNER_VISIBLE = "EvOwnerVisible"


class Blocker(Enum):
    NONE = "BkNone"
    AGENT_DOABLE = "BkAgentDoable"
    OWNER_ONLY = "BkOwnerOnly"


class Ledger(Enum):
    OK = "LOk"
    MISSING = "LMissing"
    INVALID = "LInvalid"


class Reason(Enum):
    UNBOUND = "RUnbound"
    WAIT_BACKGROUND = "RWaitBackground"
    ALL_CLEAR = "RAllClear"
    NO_PROGRESS = "RNoProgress"
    OPEN_ASKS = "ROpenAsks"
    LEDGER_BROKEN = "RLedgerBroken"


class Kind(Enum):
    ALLOW = "VAllow"
    BLOCK = "VBlock"


@dataclass(frozen=True)
class Verdict:
    kind: Kind
    reason: Reason

    @property
    def blocks(self) -> bool:
        return self.kind is Kind.BLOCK


def allow(reason: Reason) -> Verdict:
    return Verdict(Kind.ALLOW, reason)


def block(reason: Reason) -> Verdict:
    return Verdict(Kind.BLOCK, reason)


def entry_ok(status: Status, evidence: Evidence, blocker: Blocker, fresh: bool) -> bool:
    """E1-E3: done with owner-visible evidence, or blocked on a fresh owner-only reason."""
    if status is Status.DONE:
        return evidence is Evidence.OWNER_VISIBLE
    if status is Status.BLOCKED:
        return blocker is Blocker.OWNER_ONLY and fresh
    return False


def _forbid(reason: Reason, active: bool, progress: bool) -> Verdict:
    """G1: a continued turn that ran no tool may stop; otherwise block."""
    if active and not progress:
        return allow(Reason.NO_PROGRESS)
    return block(reason)


def decide_stop(bound: bool, waiting: bool, ledger: Ledger, all_ok: bool,
                active: bool, progress: bool) -> Verdict:
    if not bound:
        return allow(Reason.UNBOUND)
    if waiting:
        return allow(Reason.WAIT_BACKGROUND)
    if ledger is not Ledger.OK:
        return _forbid(Reason.LEDGER_BROKEN, active, progress)
    if all_ok:
        return allow(Reason.ALL_CLEAR)
    return _forbid(Reason.OPEN_ASKS, active, progress)


B = (False, True)
DOMAINS = {
    "entry_ok": (Status, Evidence, Blocker, B),
    "decide_stop": (B, B, Ledger, B, B, B),
}
DOMAIN_ROWS = sum(
    __import__("math").prod(len(axis) for axis in domain) for domain in DOMAINS.values())

_REASON_CODE = {r: i for i, r in enumerate(Reason)}


def code(value) -> int:
    """Same integer encoding as MODEL.bend code_verdict / code_bool."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Verdict):
        return (100 if value.blocks else 0) + _REASON_CODE[value.reason]
    raise TypeError(value)
