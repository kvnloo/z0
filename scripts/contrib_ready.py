#!/usr/bin/env python3
"""contrib_ready: may the "ready to send" message go out? (contributor spec §4.4)

Usage:
  python scripts/contrib_ready.py --z0 <sha> --z0int <sha> --receipts <dir>
                                  [--blockers <file.json>] [--json]

This is the operational twin of bend/contrib_ready/MODEL.bend. Every decision below
is a small finite function whose enum values are the Bend constructor names, in the
Bend declaration order (that order is the code order). tests/contrib_ready/ runs
every row of every finite domain, and a bounded set of whole matrices, through both.
Change the two together, then run `bend PROOF.bend --verdict` and the twin tests.

Operational rule: the "ready to send" message is allowed only when this script prints
READY and exits 0. The message quotes that output and both shas. Any other output is
a status report, not an announcement.

Receipts: every `*.json` file directly in --receipts is one receipt:
  {"cell": "<REQUIRED id>", "z0_sha": "<40 hex>", "z0int_sha": "<40 hex>",
   "status": "pass" | "fail", ...}
A receipt counts only when both shas are exactly the candidate pair (R5): a prefix,
another commit or a missing sha makes it stale, and a stale pass never counts (R2).
A malformed receipt is ignored (with a warning): it can never make a cell pass.

Blockers (--blockers): a JSON list of {"kind": "owner" | "external", "reason": "..."}.
A record without a reason, or of another kind, is not a blocker (R3): NOT_READY.

Exit codes: 0 READY, 1 NOT_READY, 3 BLOCKED_OWNER or BLOCKED_EXTERNAL, 2 usage.
Stdlib only (Python 3.10+). It reads the receipt files and writes nothing.
"""
from __future__ import annotations

import argparse
from enum import Enum
import json
from pathlib import Path
import re
import sys

BOOLS = (False, True)
SHA = re.compile(r"[0-9a-f]{40}")


class Cell(Enum):
    NONE = "CNone"
    FAIL = "CFail"
    PASS_OTHER_SHA = "CPassOtherSha"
    PASS_CANDIDATE = "CPassCandidate"


class Blocker(Enum):
    NONE = "BNone"
    NO_REASON = "BNoReason"
    OWNER = "BOwner"
    EXTERNAL = "BExternal"


class Status(Enum):
    NOT_READY = "SNotReady"
    READY = "SReady"
    BLOCKED_OWNER = "SBlockedOwner"
    BLOCKED_EXTERNAL = "SBlockedExternal"


class Outcome(Enum):
    MISSING = "OMissing"
    FAIL = "OFail"
    PASS = "OPass"


def _agent_reqs():
    for harness in ("Claude", "Codex"):
        for profile in ("Frontend", "MlResearch", "SystemsRust"):
            for run in (1, 2, 3):
                yield f"{harness.upper()}_{profile.upper()}_RUN{run}", f"Q{harness}{profile}Run{run}"


# R4: the REQUIRED set, in MODEL order. Changing it changes MODEL.bend too.
Req = Enum("Req", [*_agent_reqs(),
                   ("ONBOARD_CONTAINER", "QOnboardContainer"), ("SMOKE", "QSmoke"),
                   ("E1", "QE1"), ("E2", "QE2"), ("G1", "QG1"), ("G2", "QG2"), ("G3", "QG3"),
                   ("G4", "QG4"), ("G5", "QG5"), ("P1", "QP1"), ("P2", "QP2"), ("C1", "QC1"),
                   ("W1", "QW1"), ("LAWS_CI", "QLawsCi")])


def _cell_id(req: Req) -> str:
    """The receipt `cell` id of a required cell."""
    match = re.fullmatch(r"(CLAUDE|CODEX)_(FRONTEND|MLRESEARCH|SYSTEMSRUST)_RUN(\d)", req.name)
    if match:
        profile = {"FRONTEND": "frontend", "MLRESEARCH": "ml-research",
                   "SYSTEMSRUST": "systems-rust"}[match.group(2)]
        return f"agent.{match.group(1).lower()}.{profile}.run{match.group(3)}"
    return {"ONBOARD_CONTAINER": "onboard_container", "SMOKE": "smoke",
            "LAWS_CI": "laws_ci"}.get(req.name, req.name)


CELL_ID = {req: _cell_id(req) for req in Req}
REQ_BY_ID = {cell_id: req for req, cell_id in CELL_ID.items()}
REQUIRED = tuple(Req)
REQUIRED_COUNT = 32


def required_count() -> int:
    return REQUIRED_COUNT


def req_code(req: Req) -> int:
    return list(Req).index(req)


# --- the finite decisions (MODEL.bend) -----------------------------------------------
def counts(cell: Cell) -> bool:
    """R2: only a pass on the candidate pair counts."""
    return cell is Cell.PASS_CANDIDATE


def classify(outcome: Outcome, z0_same: bool, z0int_same: bool) -> Cell:
    """R5: a receipt counts only when BOTH shas are the candidate pair."""
    if outcome is Outcome.MISSING:
        return Cell.NONE
    same = z0_same and z0int_same
    if outcome is Outcome.FAIL:
        return Cell.FAIL if same else Cell.NONE
    return Cell.PASS_CANDIDATE if same else Cell.PASS_OTHER_SHA


_CELL_RANK = {Cell.NONE: 0, Cell.PASS_OTHER_SHA: 1, Cell.PASS_CANDIDATE: 2, Cell.FAIL: 3}


def merge_cell(a: Cell, b: Cell) -> Cell:
    """Several receipts for one cell: a candidate fail wins, then a candidate pass."""
    return a if _CELL_RANK[a] >= _CELL_RANK[b] else b


_BLOCKER_RANK = {Blocker.NONE: 0, Blocker.NO_REASON: 1, Blocker.EXTERNAL: 2, Blocker.OWNER: 3}


def merge_blocker(a: Blocker, b: Blocker) -> Blocker:
    """Several blocker records: owner, then external, then a reasonless record."""
    return a if _BLOCKER_RANK[a] >= _BLOCKER_RANK[b] else b


def all_count(cells) -> bool:
    return all(counts(cell) for _, cell in cells)


def shape_ok(cells, start: int = 0) -> bool:
    """R4: the entries are exactly REQUIRED, in order."""
    codes = [req_code(req) for req, _ in cells]
    return codes == list(range(start, required_count()))


def complete(cells) -> bool:
    return all_count(cells) and shape_ok(cells)


def ready_if(ok: bool) -> Status:
    return Status.READY if ok else Status.NOT_READY


def decide_with(blocker: Blocker, ok: bool) -> Status:
    """R3: a blocker can give SBlocked*, never SReady; BNoReason gives SNotReady."""
    if blocker is Blocker.NONE:
        return ready_if(ok)
    if blocker is Blocker.OWNER:
        return Status.BLOCKED_OWNER
    if blocker is Blocker.EXTERNAL:
        return Status.BLOCKED_EXTERNAL
    return Status.NOT_READY


def decide(cells, blocker: Blocker) -> Status:
    return decide_with(blocker, complete(cells))


def is_ready(status: Status) -> bool:
    return status is Status.READY


def required_all(cell: Cell) -> list:
    return [(req, cell) for req in REQUIRED]


# Every finite domain, for the exhaustive twin parity (tests/contrib_ready/).
DOMAINS = {
    "counts": (Cell,),
    "classify": (Outcome, BOOLS, BOOLS),
    "merge_cell": (Cell, Cell),
    "merge_blocker": (Blocker, Blocker),
    "decide_with": (Blocker, BOOLS),
    "req_code": (Req,),
    "is_ready": (Status,),
}
DOMAIN_ROWS = 4 + 12 + 16 + 16 + 8 + 32 + 4


def code(result) -> int:
    """Lossless code of a result, the same number MODEL.bend's code_* prints."""
    if isinstance(result, bool):
        return int(result)
    if isinstance(result, int):
        return result
    return list(type(result)).index(result)


# --- receipts and blockers (observation, not proven) ---------------------------------
def receipt_cell(receipt, z0_sha: str, z0int_sha: str):
    """(Req, Cell) for one receipt, or None when it names no required cell."""
    if not isinstance(receipt, dict):
        return None
    req = REQ_BY_ID.get(receipt.get("cell"))
    if req is None:
        return None
    status = receipt.get("status")
    outcome = {"pass": Outcome.PASS, "fail": Outcome.FAIL}.get(status, Outcome.FAIL)
    return req, classify(outcome, receipt.get("z0_sha") == z0_sha,
                         receipt.get("z0int_sha") == z0int_sha)


def matrix_cells(matrix, receipts, z0_sha: str, z0int_sha: str) -> list:
    """One (req, cell) per entry of `matrix`, merging every receipt of that cell."""
    found = {}
    for receipt in receipts:
        hit = receipt_cell(receipt, z0_sha, z0int_sha)
        if hit is not None:
            req, cell = hit
            found[req] = merge_cell(found.get(req, Cell.NONE), cell)
    return [(req, found.get(req, Cell.NONE)) for req in matrix]


def blocker_of(record) -> Blocker:
    if not isinstance(record, dict):
        return Blocker.NO_REASON
    reason = record.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return Blocker.NO_REASON
    return {"owner": Blocker.OWNER, "external": Blocker.EXTERNAL}.get(record.get("kind"),
                                                                      Blocker.NO_REASON)


def blockers_of(records) -> Blocker:
    result = Blocker.NONE
    for record in records or []:
        result = merge_blocker(result, blocker_of(record))
    return result


def decide_ready(matrix, receipts, blockers, z0_sha: str, z0int_sha: str) -> Status:
    """The status for the candidate pair. `matrix` is REQUIRED unless a test passes
    another one: anything but REQUIRED is never READY (R4)."""
    return decide(matrix_cells(matrix, receipts, z0_sha, z0int_sha), blockers_of(blockers))


def may_announce(status: Status, z0_sha: str, z0int_sha: str) -> bool:
    """The "ready to send" message is allowed only for READY on a full candidate pair."""
    return (is_ready(status) and isinstance(z0_sha, str) and isinstance(z0int_sha, str)
            and SHA.fullmatch(z0_sha) is not None and SHA.fullmatch(z0int_sha) is not None)


def read_receipts(folder) -> tuple:
    """(receipts, warnings) from the `*.json` files directly in `folder`."""
    receipts, warnings = [], []
    folder = Path(folder)
    if not folder.is_dir():
        return receipts, [f"receipt dir not found: {folder.name}"]
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            warnings.append(f"unreadable receipt ignored: {path.name}")
            continue
        if not isinstance(data, dict) or data.get("cell") not in REQ_BY_ID:
            warnings.append(f"receipt names no required cell, ignored: {path.name}")
            continue
        if data.get("status") not in ("pass", "fail"):
            warnings.append(f"receipt status is not pass/fail, counted as fail: {path.name}")
        receipts.append(data)
    return receipts, warnings


STATUS_TEXT = {Status.READY: "READY", Status.NOT_READY: "NOT_READY",
               Status.BLOCKED_OWNER: "BLOCKED_OWNER", Status.BLOCKED_EXTERNAL: "BLOCKED_EXTERNAL"}
EXIT = {Status.READY: 0, Status.NOT_READY: 1, Status.BLOCKED_OWNER: 3, Status.BLOCKED_EXTERNAL: 3}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="contrib_ready", description=__doc__.split("\n")[0])
    parser.add_argument("--z0", required=True, help="candidate z0 commit (40 hex)")
    parser.add_argument("--z0int", required=True, help="candidate z0intelligence commit (40 hex)")
    parser.add_argument("--receipts", required=True, help="receipt dir for this pair")
    parser.add_argument("--blockers", help="JSON list of blocker records")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    args = parser.parse_args(argv)
    z0_sha, z0int_sha = args.z0.lower(), args.z0int.lower()
    if not (SHA.fullmatch(z0_sha) and SHA.fullmatch(z0int_sha)):
        print("contrib_ready: --z0 and --z0int must be full 40-hex commit shas", file=sys.stderr)
        return 2
    receipts, warnings = read_receipts(args.receipts)
    blockers = []
    if args.blockers:
        try:
            blockers = json.loads(Path(args.blockers).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("contrib_ready: --blockers is not readable JSON", file=sys.stderr)
            return 2
        if not isinstance(blockers, list):
            blockers = [blockers]
    cells = matrix_cells(REQUIRED, receipts, z0_sha, z0int_sha)
    status = decide(cells, blockers_of(blockers))
    if is_ready(status) and not may_announce(status, z0_sha, z0int_sha):
        status = Status.NOT_READY  # unreachable: the shas were checked above
    not_counted = {CELL_ID[req]: cell.name.lower() for req, cell in cells if not counts(cell)}
    if args.json:
        print(json.dumps({"status": STATUS_TEXT[status], "z0_sha": z0_sha, "z0int_sha": z0int_sha,
                          "counted": REQUIRED_COUNT - len(not_counted),
                          "required": REQUIRED_COUNT, "not_counted": not_counted,
                          "warnings": warnings}, indent=2, sort_keys=True))
    else:
        print(STATUS_TEXT[status])
        print(f"z0 {z0_sha}")
        print(f"z0int {z0int_sha}")
        print(f"cells {REQUIRED_COUNT - len(not_counted)}/{REQUIRED_COUNT}")
        for cell_id, why in not_counted.items():
            print(f"  {cell_id}: {why}")
        for warning in warnings:
            print(f"warning: {warning}")
    return EXIT[status]


if __name__ == "__main__":
    sys.exit(main())
