"""Tests for `z0 exp`: map validity, fingerprints, dedup and result validation."""

from __future__ import annotations

import json
import sys
import tempfile
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


def test_compaction_carryover_runs_with_python3():
    act = X.next_action(X.get(DATA, "hz-compaction-carryover"), [], "public", "hw", "fixture")
    assert act["kind"] == "run" and act["arm"] == "head-tail"
    assert act["command"].startswith("cd ~/.z0/repos/z0intelligence && python3 "
                                      "experiments/hz-compaction-carryover/run.py --arm head-tail ")


def test_open_arm_family_means_build_your_arm_not_run_a_placeholder():
    exp = X.get(DATA, "hz-compaction-carryover")
    ledger = [_row(a, exp_id=exp["id"]) for a in ("head-tail", "pinned-manifest")]
    act = X.next_action(exp, ledger, "public", "hwA", "fixture")
    assert act["kind"] == "build" and act["arm"] == "compactor-<name>"
    assert "<" not in act["command"] and "<" not in act["then"]  # `<name>` is a shell redirect
    assert "commit" in act["why"] and "compactor-" in act["why"]
    exp = X.get(DATA, "zi-context-superopt")  # its own runner command makes the family member
    act = X.next_action(exp, [_row("default-policy", exp_id=exp["id"])], "public", "hwA", "fixture")
    assert act["kind"] == "run" and "<" not in act["command"]


def test_launcher_falls_back_to_the_z0_venv_when_python3_lacks_yaml():
    import os
    import subprocess
    import tempfile
    launcher = str(Path(__file__).resolve().parents[1] / "z0")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "block").mkdir()
        (t / "block" / "yaml.py").write_text("raise ImportError('no yaml here')\n")
        for path, pre in ((t / "bin" / "python3", f"PYTHONPATH={t / 'block'}:$PYTHONPATH "),
                          (t / ".z0" / "venv" / "bin" / "python", "")):
            path.parent.mkdir(parents=True)
            path.write_text(f'#!/bin/sh\n{pre}exec "{sys.executable}" "$@"\n')
            path.chmod(0o755)
        env = {"HOME": str(t), "PATH": f"{t / 'bin'}:/usr/bin:/bin"}
        out = subprocess.run([launcher, "exp", "list"], env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0 and "hz-compaction-carryover" in out.stdout, out.stderr
        os.unlink(t / ".z0" / "venv" / "bin" / "python")
        out = subprocess.run([launcher, "exp", "list"], env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 1 and "PyYAML required" in out.stderr


def test_validate_rejects_keep_without_controls_and_owner_tier():
    exp = _exp()
    assert X.validate_result(_row("llm-program"), exp) == []
    errs = X.validate_result(_row("llm-program", verdict="KEEP"), exp)
    assert any("controls" in e for e in errs)
    errs = X.validate_result(_row("llm-program", data_tier="owner"), exp)
    assert errs
    errs = X.validate_result(_row("not-an-arm"), exp)
    assert any("not in the map" in e for e in errs)
    errs = X.validate_result(_row("llm-program", repo_sha="a" * 40 + "+dirty"), exp)  # kvnloo/z0intelligence#372
    assert any("uncommitted" in e for e in errs)


def test_comment_marker_round_trips():
    r = _row("recency", fingerprint="f" * 16)
    rows = X.parse_markers(["noise", X.render_comment(r)])
    assert rows == [json.loads(json.dumps(r, sort_keys=True))]


def test_verify_marker_marks_only_the_matching_fingerprint():
    exp = _exp()
    v = {"schema": X.VERIFY_SCHEMA, "exp_id": "zi-distill-program",
         "fingerprint": "f" * 16, "by": "kvnloo", "note": "reproduced on hwB"}
    body = X.verify_comment(exp, v)
    rows = X.parse_verify_markers(["noise", body, X.render_comment(_row("x", fingerprint="0" * 16))])
    assert rows == [json.loads(json.dumps(v, sort_keys=True))]
    marked = X.apply_verify([_row("recency", fingerprint="f" * 16),
                             _row("bigram", fingerprint="e" * 16)], rows)
    assert marked[0]["verified"] is True and marked[0]["verified_by"] == "kvnloo"
    assert marked[0]["verified_note"] == "reproduced on hwB"
    assert "verified" not in marked[1]


def test_ledger_files_carry_issue_and_rank_best_first():
    exp_id = "zi-distill-program"
    rows = [
        _row("majority", fingerprint="1" * 16,
             metric={"name": "session_macro_top1", "value": 0.5}),
        _row("recency", fingerprint="2" * 16,
             metric={"name": "session_macro_top1", "value": 0.7, "ci95": [0.6, 0.8]}),
        _row("bigram", fingerprint="3" * 16, verdict="INVALID",
             metric={"name": "session_macro_top1", "value": 0.99}),
    ]
    files = X.build_ledger_files(DATA, {exp_id: rows})
    parsed = [json.loads(line) for line in
              files["generated/experiments-ledger.jsonl"].splitlines()]
    assert len(parsed) == 3
    assert all(r["issue"] == "kvnloo/z0intelligence#309" for r in parsed)
    md = files[f"generated/experiments/{exp_id}.md"]
    # 'up' metric: best value first, INVALID last despite the highest value
    assert md.index("`recency`") < md.index("`majority`") < md.index("`bigram`")
    assert "0.7" in md and "0.6 to 0.8" in md
    assert f"generated/experiments/{exp_id}.md" in files


def test_fetch_ledger_reads_the_committed_ledger_without_gh():
    row = _row("majority", fingerprint="a" * 16)
    row["issue"] = "kvnloo/z0intelligence#309"
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "ledger.jsonl"
        p.write_text(json.dumps(row) + "\n")
        rows = X.fetch_ledger(_exp(), refresh=False, ledger_path=p)
    assert any(r.get("fingerprint") == "a" * 16 for r in rows)


def test_dedupe_keeps_the_verified_enriched_row():
    row = _row("majority", fingerprint="a" * 16)
    enriched = dict(row, issue="kvnloo/z0intelligence#309", verified=True)
    rows = X._dedupe_rows([enriched, row])
    assert len(rows) == 1 and rows[0]["verified"] is True


def load_tests(loader, tests, pattern):  # CI runs `unittest discover`, which skips bare functions
    import unittest
    return unittest.TestSuite(unittest.FunctionTestCase(f) for n, f in sorted(globals().items())
                              if n.startswith("test_"))
