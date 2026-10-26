"""LAWS.bend restated over kernel.py, exhaustively. Returns the violated law names."""
from __future__ import annotations

import itertools

B = (False, True)


def violations(k):
    S, E, Bk, L, R = k.Status, k.Evidence, k.Blocker, k.Ledger, k.Reason
    bad = set()
    for s, ev, bk, f in itertools.product(S, E, Bk, B):
        ok = k.entry_ok(s, ev, bk, f)
        if s in (S.OPEN, S.PARTIAL, S.UNKNOWN) and ok:
            bad.add("E1 open/partial/unknown permits")
        if s is S.DONE and ok != (ev is E.OWNER_VISIBLE):
            bad.add("E2 done evidence")
        if s is S.BLOCKED and ok != (bk is Bk.OWNER_ONLY and f):
            bad.add("E3 blocked reason/freshness")
    for bound, w, l, ok, a, p in itertools.product(B, B, L, B, B, B):
        v = k.decide_stop(bound, w, l, ok, a, p)
        if not bound:
            if v != k.allow(R.UNBOUND):
                bad.add("B1 unbound blocks")
            continue
        if w:
            if v != k.allow(R.WAIT_BACKGROUND):
                bad.add("W1 waiting")
            continue
        if a and not p:
            if v.blocks:
                bad.add("G1 loop guard")
            continue
        if l is not L.OK:
            if v != k.block(R.LEDGER_BROKEN):
                bad.add("S3 broken ledger")
        elif ok:
            if v != k.allow(R.ALL_CLEAR):
                bad.add("S2 all clear")
        elif v != k.block(R.OPEN_ASKS):
            bad.add("S1 open asks")
    return bad
