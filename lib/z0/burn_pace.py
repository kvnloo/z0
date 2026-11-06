"""Pace-aware admission for subscription pool rows (twin of bend/burn_pace, laws.toml domain burn_pace).

Deployed to ~/.local/lib/z0/burn_pace/current/burn_pace.py; Hermes agent/burn_pace_gate.py loads it.

burn-pace (~/.local/bin/burn-pace) appends one JSON reading per probe to
~/.z0int/state/posture/burn-pace.jsonl. ~/.config/burn-gate/pool-lanes.json maps
pool row labels to burn-pace lanes per provider, e.g. {"anthropic": {"acct-a": "lane-a"}}.

For a mapped row: deny it when the weekly window is >= USED_STOP or the pace ratio is
>= RATIO_STOP, and order the rows that remain by pace ratio, coolest first. A row with
no mapping, or a provider with no mapping, passes through unchanged. If the reading is
stale or missing, every mapped row is denied (fail closed). Owner override:
HERMES_BURN_GATE_OVERRIDE=1.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STALE_S = 30 * 60
USED_STOP = 95.0
RATIO_STOP = 1.5
_CACHE_S = 60.0
_cache: dict = {"at": 0.0, "key": None, "val": None}


def _paths():
    home = Path(os.environ.get("BURN_GATE_HOME") or Path.home())
    return home / ".z0int/state/posture/burn-pace.jsonl", home / ".config/burn-gate/pool-lanes.json"


def _last_reading(samples):
    try:
        with samples.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(f.tell() - 65536, 0))
            lines = f.read().decode(errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def _load():
    samples, lanes_path = _paths()
    try:
        key = (str(samples), samples.stat().st_mtime, lanes_path.stat().st_mtime)
    except OSError:
        key = None
    now = time.monotonic()
    if _cache["key"] == key and now - _cache["at"] < _CACHE_S:
        return _cache["val"]
    try:
        lanes = json.loads(lanes_path.read_text())
    except (OSError, ValueError):
        lanes = {}
    val = (lanes, _last_reading(samples))
    _cache.update(at=now, key=key, val=val)
    return val


# Finite classes proven in bend/burn_pace (MODEL.bend admit/route, LAWS.bend). The numeric
# readings are classified here; the decision itself is admit_cls, which must match the law
# table exactly (tests/agent/test_burn_pace_law_parity.py runs Bend's TABLE.bend against it).
FRESH, STALE = "fresh", "stale"
UNDER, AT_CAP = "under", "at_cap"
COOL, UNKNOWN, HOT = "cool", "unknown", "hot"


OWNER, BULK = "owner", "bulk"


def admit_cls(fresh: str, used: str, pace: str, who: str) -> bool:
    return fresh == FRESH and used == UNDER and (who == OWNER or pace in (COOL, UNKNOWN))


def who_for(model, lanes, profile=None) -> str:
    """OWNER only for the owner's own conversation: an Opus request in an owner profile
    (pool-lanes.json "owner_profiles"). The consumer supplies *profile*; unknown -> BULK."""
    if not model or "opus" not in str(model).lower() or not profile:
        return BULK
    return OWNER if profile in set(lanes.get("owner_profiles") or ()) else BULK


def route_cls(any_admitted: bool) -> str:
    return "paid" if any_admitted else "free"


def classify(lane: str, reading) -> tuple[str, str, str, str]:
    """(fresh, used, pace, reason) for *lane* in *reading*."""
    try:
        age = time.time() - datetime.fromisoformat(reading["at"]).timestamp()
    except (TypeError, KeyError, ValueError):
        return STALE, AT_CAP, UNKNOWN, "no burn-pace reading"
    if age > STALE_S:
        return STALE, AT_CAP, UNKNOWN, f"burn-pace reading {int(age // 60)} min old"
    row = (reading.get("lanes") or {}).get(lane) or {}
    used, ratio = row.get("weekly_used_pct"), row.get("pace_ratio")
    if used is None:
        return STALE, AT_CAP, UNKNOWN, f"lane {lane} missing from burn-pace"
    u = AT_CAP if used >= USED_STOP else UNDER
    rate, hours = row.get("observed_pct_per_h"), row.get("hours_to_reset")
    if rate is not None and hours is not None:
        # HOT = at the observed burn rate this row runs out before its weekly reset.
        pace = HOT if used + rate * hours >= USED_STOP else COOL
    else:
        pace = UNKNOWN if ratio is None else (HOT if ratio >= RATIO_STOP else COOL)
    return FRESH, u, pace, f"lane {lane} {used}% used (resets in {row.get('hours_to_reset')}h), pace {ratio}"


def verdict(lane: str, reading, who: str = BULK) -> tuple[bool, float, str]:
    """(allowed, pace_ratio_for_sorting, reason)."""
    fresh, used, pace, why = classify(lane, reading)
    ratio = ((reading or {}).get("lanes") or {}).get(lane, {}).get("pace_ratio") if fresh == FRESH else None
    return admit_cls(fresh, used, pace, who), ratio if ratio is not None else 0.0, f"{why} [{who}]"


def _override_file_active() -> bool:
    """Owner override without a restart: ~/.config/burn-gate/override holding a future epoch."""
    try:
        return float((_paths()[1].parent / "override").read_text().split()[0]) > time.time()
    except (OSError, ValueError, IndexError):
        return False


def admit(provider: str, entries: list, model=None, profile=None) -> list:
    """Filter and order *entries* (PooledCredential-like, with .label) for *provider*."""
    if not entries or os.environ.get("HERMES_BURN_GATE_OVERRIDE") == "1" or _override_file_active():
        return entries
    lanes, reading = _load()
    mapping = lanes.get(provider) if isinstance(lanes, dict) else None
    if not mapping:
        return entries
    who = who_for(model, lanes, profile)
    kept, denied = [], []
    for idx, entry in enumerate(entries):
        lane = mapping.get(getattr(entry, "label", None) or "")
        if not lane:
            kept.append((1.0, idx, entry))
            continue
        ok, ratio, why = verdict(lane, reading, who)
        if ok:
            kept.append((ratio, idx, entry))
        else:
            denied.append(f"{entry.label}: {why}")
    if denied:
        logger.warning("burn-pace gate (%s) skipped %s", provider, "; ".join(denied))
    if not kept:
        logger.error("burn-pace gate (%s): every subscription row is over pace; refusing to drain one "
                     "(override: HERMES_BURN_GATE_OVERRIDE=1)", provider)
    return [e for _r, _i, e in sorted(kept, key=lambda t: (t[0], t[1]))]
