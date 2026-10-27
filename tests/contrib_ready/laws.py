"""Python statements of the contrib_ready laws (spec §4.4), applied to any twin module.

Each law takes the module ``m`` (scripts/contrib_ready.py, or a textual mutant of it)
and raises AssertionError when it is broken. test_twin.py runs them against the real
twin; test_mutation.py runs them against mutants, so a mutant that survives every
law here is a hole in the law set, not in the twin.
"""
from __future__ import annotations

import itertools

from tests.contrib_ready import twin

BOOLS = (False, True)
Z0 = "a" * 40
Z0INT = "b" * 40

# R4: the REQUIRED set as the spec writes it. Changing it is an owner decision.
SPEC_REQUIRED = (
    [f"agent.{h}.{p}.run{r}" for h in ("claude", "codex")
     for p in ("frontend", "ml-research", "systems-rust") for r in (1, 2, 3)]
    + ["onboard_container", "smoke", "E1", "E2", "G1", "G2", "G3", "G4", "G5", "P1", "P2",
       "C1", "W1", "laws_ci"])


def _check(cond, message):
    if not cond:
        raise AssertionError(message)


def _receipts(m, z0=Z0, z0int=Z0INT, status="pass", skip=()):
    return [{"cell": m.CELL_ID[req], "z0_sha": z0, "z0int_sha": z0int, "status": status}
            for req in m.REQUIRED if m.CELL_ID[req] not in skip]


def law_r1_uncounted_cell_never_ready(m):
    """R1: any cell that does not count, anywhere, under any blocker: never SReady."""
    for _, cells in twin.matrices(m):
        if all(m.counts(cell) for _, cell in cells):
            continue
        for blocker in m.Blocker:
            _check(not m.is_ready(m.decide(cells, blocker)), "R1: an uncounted cell gave READY")
    for cell in m.Cell:
        _check(m.counts(cell) == (cell is m.Cell.PASS_CANDIDATE), f"R1/R2: counts({cell})")


def law_r2_other_sha_is_missing(m):
    """R2: CPassOtherSha counts as CNone, at every position and under every merge."""
    passing = m.required_all(m.Cell.PASS_CANDIDATE)
    for i, blocker in itertools.product(range(len(passing)), m.Blocker):
        req = passing[i][0]
        stale = passing[:i] + [(req, m.Cell.PASS_OTHER_SHA)] + passing[i + 1:]
        missing = passing[:i] + [(req, m.Cell.NONE)] + passing[i + 1:]
        _check(m.decide(stale, blocker) == m.decide(missing, blocker), f"R2 at {i}")
    for cell in m.Cell:
        _check(m.counts(m.merge_cell(m.Cell.PASS_OTHER_SHA, cell)) == m.counts(cell),
               "R2: a stale pass added a count (left)")
        _check(m.counts(m.merge_cell(cell, m.Cell.PASS_OTHER_SHA)) == m.counts(cell),
               "R2: a stale pass added a count (right)")
        _check(m.merge_cell(m.Cell.NONE, cell) == cell, "merge: a missing receipt changed a cell")
        _check(m.merge_cell(m.Cell.FAIL, cell) == m.Cell.FAIL, "a candidate fail was hidden (left)")
        _check(m.merge_cell(cell, m.Cell.FAIL) == m.Cell.FAIL, "a candidate fail was hidden (right)")


def law_r3_blockers(m):
    """R3: a blocker gives SBlocked*, never SReady; a reasonless one gives SNotReady."""
    for _, cells in itertools.chain([("full", m.required_all(m.Cell.PASS_CANDIDATE))],
                                    twin.matrices(m)):
        _check(m.decide(cells, m.Blocker.OWNER) == m.Status.BLOCKED_OWNER, "R3: owner")
        _check(m.decide(cells, m.Blocker.EXTERNAL) == m.Status.BLOCKED_EXTERNAL, "R3: external")
        _check(m.decide(cells, m.Blocker.NO_REASON) == m.Status.NOT_READY, "R3: no reason")
    for a in m.Blocker:
        _check(m.merge_blocker(m.Blocker.OWNER, a) == m.Blocker.OWNER, "owner dominates (left)")
        _check(m.merge_blocker(a, m.Blocker.OWNER) == m.Blocker.OWNER, "owner dominates (right)")
        _check(m.merge_blocker(m.Blocker.NONE, a) == a, "no blocker is the identity")
    full = _receipts(m)
    for records in ([{"kind": "owner"}], [{"kind": "owner", "reason": " "}],
                    [{"kind": "someone", "reason": "x"}], ["owner"], [None]):
        _check(m.decide_ready(m.REQUIRED, full, records, Z0, Z0INT) == m.Status.NOT_READY,
               f"R3: a reasonless blocker record must give NOT_READY: {records!r}")
    _check(m.decide_ready(m.REQUIRED, full, [{"kind": "owner", "reason": "hold"}], Z0, Z0INT)
           == m.Status.BLOCKED_OWNER, "R3: owner record")


def law_r4_required_is_the_constant(m):
    """R4: REQUIRED is the spec's 32 cells; any other shape is never READY."""
    _check([m.CELL_ID[req] for req in m.REQUIRED] == SPEC_REQUIRED, "R4: REQUIRED drifted")
    _check(m.required_count() == 32 == len(m.REQUIRED), "R4: count")
    _check([m.req_code(req) for req in m.REQUIRED] == list(range(32)), "R4: order")
    for label, cells in twin.matrices(m):
        if label.split()[0] in ("drop", "duplicate", "prefix", "swap", "extra", "reversed"):
            _check(not m.shape_ok(cells), f"R4: shape {label} accepted")
            _check(not m.is_ready(m.decide(cells, m.Blocker.NONE)), f"R4: {label} was READY")
    full = _receipts(m)
    for drop in SPEC_REQUIRED:
        status = m.decide_ready(m.REQUIRED, _receipts(m, skip=(drop,)), [], Z0, Z0INT)
        _check(status == m.Status.NOT_READY, f"R4: missing receipt for {drop} was {status}")
    _check(m.decide_ready(m.REQUIRED[:-1], full, [], Z0, Z0INT) == m.Status.NOT_READY,
           "R4: a shorter matrix was READY")


def law_r5_candidate_pair(m):
    """R5: a receipt counts only when both shas are exactly the candidate pair."""
    for outcome, z, i in itertools.product(m.Outcome, BOOLS, BOOLS):
        cell = m.classify(outcome, z, i)
        _check(m.counts(cell) == (outcome is m.Outcome.PASS and z and i), f"R5: {outcome} {z} {i}")
        if outcome is m.Outcome.MISSING:
            _check(cell is m.Cell.NONE, "R5: a missing receipt is CNone")
    stale_pairs = [("c" * 40, Z0INT), (Z0, "c" * 40), (Z0[:12], Z0INT), (Z0.upper(), Z0INT),
                   (None, Z0INT), (Z0, None)]
    for z0, z0int in stale_pairs:
        receipts = _receipts(m)
        receipts[0] = dict(receipts[0], z0_sha=z0, z0int_sha=z0int)
        status = m.decide_ready(m.REQUIRED, receipts, [], Z0, Z0INT)
        _check(status == m.Status.NOT_READY, f"R5: a receipt on ({z0!r}, {z0int!r}) counted")
        everything_stale = _receipts(m, z0=z0, z0int=z0int)
        _check(m.decide_ready(m.REQUIRED, everything_stale, [], Z0, Z0INT) == m.Status.NOT_READY,
               "R5: a whole stale matrix counted")
    for status in ("skipped", "PASS", "", None, "passed"):
        receipts = _receipts(m)
        receipts[3] = dict(receipts[3], status=status)
        _check(m.decide_ready(m.REQUIRED, receipts, [], Z0, Z0INT) == m.Status.NOT_READY,
               f"R5: a receipt with status {status!r} counted as a pass")
    failed = _receipts(m) + [dict(_receipts(m)[5], status="fail")]
    _check(m.decide_ready(m.REQUIRED, failed, [], Z0, Z0INT) == m.Status.NOT_READY,
           "a candidate fail beside a candidate pass was hidden")
    stale_fail = _receipts(m) + [dict(_receipts(m)[5], status="fail", z0_sha="c" * 40)]
    _check(m.decide_ready(m.REQUIRED, stale_fail, [], Z0, Z0INT) == m.Status.READY,
           "a fail on another pair blocked a candidate pass")


def law_ready_iff_complete(m):
    """Without a blocker, READY is exactly: every cell counts and the shape is REQUIRED."""
    for _, cells in twin.matrices(m):
        _check(m.is_ready(m.decide(cells, m.Blocker.NONE)) == m.complete(cells), "ready iff complete")
    _check(m.decide(m.required_all(m.Cell.PASS_CANDIDATE), m.Blocker.NONE) == m.Status.READY,
           "non-vacuity: the full candidate matrix is READY")
    _check(m.decide_ready(m.REQUIRED, _receipts(m), [], Z0, Z0INT) == m.Status.READY,
           "non-vacuity: full receipts on the candidate pair are READY")


def law_may_announce(m):
    """The message is allowed only for READY on a full 40-hex candidate pair."""
    for status in m.Status:
        _check(m.may_announce(status, Z0, Z0INT) == (status is m.Status.READY), f"announce {status}")
    for z0, z0int in ((Z0[:7], Z0INT), (Z0, ""), ("g" * 40, Z0INT), (None, Z0INT)):
        _check(not m.may_announce(m.Status.READY, z0, z0int), f"announce on ({z0!r}, {z0int!r})")


LAWS = [law_r1_uncounted_cell_never_ready, law_r2_other_sha_is_missing, law_r3_blockers,
        law_r4_required_is_the_constant, law_r5_candidate_pair, law_ready_iff_complete,
        law_may_announce]
