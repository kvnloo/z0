"""Read the ask ledger and classify each entry into the kernel's finite domain.

The ledger is JSON (a subset of YAML 1.2) so the hook needs only the stdlib.
Classification is observation, not proof: the kernel and its Bend twin decide.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import os
from pathlib import Path
import re

from .kernel import Blocker, Evidence, Ledger, Status, entry_ok

DEFAULT_LEDGER = Path(os.path.expanduser("~/workspace/.z0/asks.yaml"))

STATUS = {"open": Status.OPEN, "partial": Status.PARTIAL, "done": Status.DONE,
          "blocked": Status.BLOCKED}
# Owner-visible evidence kinds and the shape their ref must have.
OWNER_VISIBLE = {
    "deployed_sha": re.compile(r"^[0-9a-f]{7,40}$"),
    "pr": re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/pull/\d+$"),
    "device_receipt": None,  # ref must name an existing file
}
WEAK = {"branch", "spec", "tests", "plan", "doc", "design", "other"}
OWNER_ONLY = {"sudo", "login", "merge_review", "physical", "owner_decision", "payment"}


@dataclass(frozen=True)
class Entry:
    id: str
    ask: str
    status: Status
    evidence: Evidence
    blocker: Blocker
    fresh: bool
    next: str
    why: str

    @property
    def ok(self) -> bool:
        return entry_ok(self.status, self.evidence, self.blocker, self.fresh)


@dataclass(frozen=True)
class Loaded:
    state: Ledger
    config: dict
    entries: tuple
    error: str = ""

    @property
    def all_ok(self) -> bool:
        return all(e.ok for e in self.entries)

    @property
    def open_entries(self):
        return [e for e in self.entries if not e.ok]


def classify_evidence(raw) -> Evidence:
    if not isinstance(raw, dict):
        return Evidence.NONE
    kind, ref = raw.get("kind"), str(raw.get("ref") or "").strip()
    if not ref:
        return Evidence.NONE
    if kind in OWNER_VISIBLE:
        shape = OWNER_VISIBLE[kind]
        if shape is None:
            return Evidence.OWNER_VISIBLE if Path(os.path.expanduser(ref)).is_file() else Evidence.WEAK
        return Evidence.OWNER_VISIBLE if shape.match(ref) else Evidence.WEAK
    return Evidence.WEAK


def classify_blocker(raw) -> Blocker:
    if not isinstance(raw, dict) or not str(raw.get("detail") or "").strip():
        return Blocker.NONE
    return Blocker.OWNER_ONLY if raw.get("kind") in OWNER_ONLY else Blocker.AGENT_DOABLE


def is_fresh(checked, stale_days: int, today: dt.date) -> bool:
    try:
        day = dt.date.fromisoformat(str(checked))
    except ValueError:
        return False
    return 0 <= (today - day).days <= stale_days


def _why(status, evidence, blocker, fresh) -> str:
    if status is Status.DONE:
        return {Evidence.NONE: "done without evidence",
                Evidence.WEAK: "done with weak evidence (needs deployed sha, device receipt or PR)"
                }.get(evidence, "")
    if status is Status.BLOCKED:
        if blocker is not Blocker.OWNER_ONLY:
            return "blocked without an owner-only reason"
        return "" if fresh else "blocked entry is stale; re-check it"
    return status.name.lower()


def load(path: Path = DEFAULT_LEDGER, today: dt.date | None = None) -> Loaded:
    today = today or dt.date.today()
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return Loaded(Ledger.MISSING, {}, (), f"ledger not found: {path}")
    except OSError as exc:
        return Loaded(Ledger.INVALID, {}, (), f"ledger unreadable: {exc}")
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or not isinstance(data.get("asks"), list):
            raise ValueError("ledger needs an object with an 'asks' list")
        stale_days = int(data.get("stale_days", 7))
        entries, seen = [], set()
        for raw in data["asks"]:
            if not isinstance(raw, dict) or not raw.get("id") or not raw.get("ask"):
                raise ValueError(f"entry without id/ask: {str(raw)[:80]}")
            if raw["id"] in seen:
                raise ValueError(f"duplicate id: {raw['id']}")
            seen.add(raw["id"])
            status = STATUS.get(str(raw.get("status", "")).lower(), Status.UNKNOWN)
            evidence = classify_evidence(raw.get("evidence"))
            blocker = classify_blocker(raw.get("blocked_by"))
            fresh = is_fresh(raw.get("checked"), stale_days, today)
            entries.append(Entry(str(raw["id"]), str(raw["ask"]), status, evidence, blocker,
                                 fresh, str(raw.get("next") or ""),
                                 _why(status, evidence, blocker, fresh)))
    except (ValueError, TypeError) as exc:
        return Loaded(Ledger.INVALID, {}, (), f"ledger invalid: {exc}")
    return Loaded(Ledger.OK, data, tuple(entries))
