"""Tests for `z0 exp`: map validity, fingerprints, dedup and result validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from z0 import experiments as X  # noqa: E402

DATA = X.load_map()


def _exp(exp_id: str = "zi-distill-program") -> dict:
    return {**X.get(DATA, exp_id), "runner": {"status": "exists", "command": "python run.py"}}


def _row(arm: str, **kw) -> dict:
    r = {"schema": X.RESULT_SCHEMA, "exp_id": "zi-distill-program", "epoch": 1, "arm": arm,
         "data_tier": "public", "data_manifest_sha256": "fixture", "hardware_class": "hwA",
         "repo_sha": "a" * 40, "n": 100, "metric": {"name": "session_macro_top1", "value": 0.7},
         "verdict": "NULL", "command": "python run.py"}
    r.update(kw)
    return r


def test_map_loads_and_every_entry_renders():
    for e in DATA["experiments"]:
        body = X.render_issue(DATA, e["id"])
        assert f"start experiment {e['id']}" in body
        assert "z0-exp-result" in body


def test_fingerprint_is_stable_and_cell_sensitive():
    a = X.fingerprint("x", 1, "arm", "public", "d", "hw")
    assert a == X.fingerprint("x", 1, "arm", "public", "d", "hw")
    assert a != X.fingerprint("x", 2, "arm", "public", "d", "hw")  # epoch bump = new cell
    assert a != X.fingerprint("x", 1, "arm", "public", "d", "hw2")


def test_controls_come_first_then_candidates():
    exp = _exp()
    act = X.next_action(exp, [], "public", "hwA", "fixture")
    assert act["kind"] == "run" and act["arm"] == "majority"
    ledger = [_row(a["id"]) for a in exp["arms"] if a.get("control")]
    act = X.next_action(exp, ledger, "public", "hwA", "fixture")
    assert act["arm"] == "llm-program"


def test_measured_cell_is_not_offered_again_but_replication_is_capped():
    exp = _exp()
    ledger = [_row("majority")]
    ids = [a["id"] for a in X.untried_arms(exp, ledger, "public", "hwA", "fixture")]
    assert "majority" not in ids  # same hardware: done
    ids = [a["id"] for a in X.untried_arms(exp, ledger, "public", "hwB", "fixture")]
    assert "majority" in ids  # other hardware: replication welcome
    ledger = [_row("majority", hardware_class=f"hw{i}") for i in range(X.PUBLIC_REPLICATIONS)]
    ids = [a["id"] for a in X.untried_arms(exp, ledger, "public", "hwZ", "fixture")]
    assert "majority" not in ids


def test_stale_epoch_and_invalid_rows_do_not_count():
    exp = _exp()
    ledger = [_row("majority", epoch=0), _row("recency", verdict="INVALID")]
    ids = [a["id"] for a in X.untried_arms(exp, ledger, "public", "hwA", "fixture")]
    assert "majority" in ids and "recency" in ids


def test_missing_runner_means_build():
    act = X.next_action(X.get(DATA, "zi-residual-tiny"), [], "public", "hw", "fixture")
    assert act["kind"] == "build"


def test_validate_rejects_keep_without_controls_and_owner_tier():
    exp = _exp()
    assert X.validate_result(_row("llm-program"), exp) == []
    errs = X.validate_result(_row("llm-program", verdict="KEEP"), exp)
    assert any("controls" in e for e in errs)
    errs = X.validate_result(_row("llm-program", data_tier="owner"), exp)
    assert errs
    errs = X.validate_result(_row("not-an-arm"), exp)
    assert any("not in the map" in e for e in errs)


def test_comment_marker_round_trips():
    r = _row("recency", fingerprint="f" * 16)
    rows = X.parse_markers(["noise", X.render_comment(r)])
    assert rows == [json.loads(json.dumps(r, sort_keys=True))]
