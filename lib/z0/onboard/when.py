"""The `when:` matcher (design §2.5): structured {fact, op, value} data, never eval'd.

A fact is a dotted path into the plan's fact tree (host.json with '-' in ids written
as '_', plus `mode`, `profile` and `derived.*`). Every condition in a list must hold.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .util import version_tuple

_MISSING = object()
OPS = ("eq", "ne", "lt", "le", "gt", "ge", "in", "not_in", "exists", "missing")


def lookup(facts: dict, path: str) -> Any:
    node: Any = facts
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _ordered(have: Any, want: Any) -> Optional[int]:
    """-1/0/1 comparing versions (strings) or numbers; None when not comparable."""
    if isinstance(have, bool) or isinstance(want, bool):
        return None
    if isinstance(have, (int, float)) and isinstance(want, (int, float)):
        return (have > want) - (have < want)
    a, b = version_tuple(have, loose=True), version_tuple(want, loose=True)
    if a is None or b is None:
        return None
    width = max(len(a), len(b))
    a, b = a + (0,) * (width - len(a)), b + (0,) * (width - len(b))
    return (a > b) - (a < b)


def holds(cond: dict, facts: dict) -> bool:
    op = cond.get("op")
    have = lookup(facts, cond.get("fact", ""))
    want = cond.get("value")
    if op == "exists":
        return have is not _MISSING and have is not None
    if op == "missing":
        return have is _MISSING or have is None
    if have is _MISSING:
        return False
    if op == "eq":
        return have == want
    if op == "ne":
        return have != want
    if op == "in":
        return isinstance(want, list) and have in want
    if op == "not_in":
        return isinstance(want, list) and have not in want
    order = _ordered(have, want)
    if order is None:
        return False
    return {"lt": order < 0, "le": order <= 0, "gt": order > 0, "ge": order >= 0}.get(op, False)


def first_failure(conds: Optional[Iterable[dict]], facts: dict) -> Optional[dict]:
    """The first condition that does not hold, or None when all hold."""
    for cond in conds or ():
        if not holds(cond, facts):
            return cond
    return None


def describe(cond: dict) -> str:
    if cond.get("op") in ("exists", "missing"):
        return f"{cond.get('fact')} {cond.get('op')}"
    return f"{cond.get('fact')} {cond.get('op')} {cond.get('value')}"
