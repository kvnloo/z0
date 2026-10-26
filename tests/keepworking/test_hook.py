"""End-to-end: mock transcripts and ledgers through the real hook script (subprocess)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "lib/z0/keepworking/hook.py"
TODAY = __import__("datetime").date.today().isoformat()

DONE = {"id": "a-done", "ask": "ship x", "status": "done",
        "evidence": {"kind": "pr", "ref": "https://github.com/o/r/pull/1"}}
BLOCKED = {"id": "a-blocked", "ask": "sudo thing", "status": "blocked",
           "blocked_by": {"kind": "sudo", "detail": "needs root password"}, "checked": TODAY}
OPEN = {"id": "a-open", "ask": "make the phone app work", "status": "open",
        "next": "deploy the build to the S22"}


class Harness:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="z0-kw-hook-"))
        self.ledger = self.dir / "asks.yaml"
        self.transcript = self.dir / "t.jsonl"
        self.transcript.write_text("")
        (self.dir / "workspace").mkdir()
        self.env = dict(os.environ, Z0_ASKS_LEDGER=str(self.ledger), HOME=str(self.dir),
                        Z0_KEEPWORKING_STATE=str(self.dir / "state"))
        self.env.pop("CLAUDE_CODE_CHILD_SESSION", None)
        self.env.pop("Z0_KEEPWORKING", None)

    def write_ledger(self, asks, **cfg):
        cfg.setdefault("scope_cwd_prefixes", [str(self.dir)])
        self.ledger.write_text(json.dumps({"version": 1, "asks": asks, **cfg}))

    def tool_call(self):
        with self.transcript.open("a") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {}}]}}, separators=(",", ":")) + "\n")

    def run(self, active=False, bg=(), crons=(), env=None, cwd=None):
        event = {"session_id": "s1", "transcript_path": str(self.transcript),
                 "cwd": str(cwd or self.dir),
                 "hook_event_name": "Stop", "stop_hook_active": active,
                 "last_assistant_message": "done", "background_tasks": list(bg),
                 "session_crons": list(crons)}
        out = subprocess.run([sys.executable, "-I", str(HOOK)], input=json.dumps(event),
                             env={**self.env, **(env or {})}, capture_output=True, text=True,
                             timeout=30)
        self.last = out
        return json.loads(out.stdout) if out.stdout.strip() else None


class HookE2E(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def test_open_ask_blocks_with_next_action(self):
        self.h.write_ledger([DONE, BLOCKED, OPEN])
        out = self.h.run()
        self.assertEqual(out["decision"], "block")
        self.assertIn("a-open", out["reason"])
        self.assertIn("deploy the build to the S22", out["reason"])
        self.assertNotIn("a-done", out["reason"])

    def test_all_done_or_owner_blocked_allows(self):
        self.h.write_ledger([DONE, BLOCKED])
        self.assertIsNone(self.h.run())
        self.assertEqual(self.h.last.returncode, 0)

    def test_weak_evidence_blocks(self):
        weak = dict(DONE, evidence={"kind": "branch", "ref": "feat/x"})
        self.h.write_ledger([weak])
        self.assertIn("weak evidence", self.h.run()["reason"])

    def test_fake_pr_ref_is_weak(self):
        self.h.write_ledger([dict(DONE, evidence={"kind": "pr", "ref": "trust me"})])
        self.assertEqual(self.h.run()["decision"], "block")

    def test_device_receipt_needs_existing_file(self):
        receipt = self.h.dir / "receipt.txt"
        entry = dict(DONE, evidence={"kind": "device_receipt", "ref": str(receipt)})
        self.h.write_ledger([entry])
        self.assertEqual(self.h.run()["decision"], "block")
        receipt.write_text("installed on S22")
        self.assertIsNone(self.h.run())

    def test_agent_doable_or_stale_block_forbids(self):
        self.h.write_ledger([dict(BLOCKED, blocked_by={"kind": "tests", "detail": "flaky"})])
        self.assertEqual(self.h.run()["decision"], "block")
        self.h.write_ledger([dict(BLOCKED, checked="2020-01-01")])
        self.assertIn("stale", self.h.run()["reason"])

    def test_partial_and_unknown_forbid(self):
        for status in ("partial", "in-progress", ""):
            self.h.write_ledger([dict(OPEN, status=status)])
            self.assertEqual(self.h.run()["decision"], "block", status)

    def test_missing_and_invalid_ledger_block(self):
        # missing ledger: the default scope is ~/workspace
        self.h.run(cwd=self.h.dir / "workspace")
        self.assertIn("unusable", json.loads(self.h.last.stdout)["reason"])
        self.h.ledger.write_text("asks: [this is yaml not json")
        self.assertIn("unusable", self.h.run(cwd=self.h.dir / "workspace")["reason"])

    def test_loop_guard(self):
        self.h.write_ledger([OPEN])
        self.assertEqual(self.h.run()["decision"], "block")
        # continued turn, no tool ran since the block -> allowed
        self.assertIsNone(self.h.run(active=True))
        # continued turn that did work -> blocked again
        self.h.tool_call()
        self.assertEqual(self.h.run(active=True)["decision"], "block")
        self.assertIsNone(self.h.run(active=True))

    def test_background_work_allows(self):
        self.h.write_ledger([OPEN])
        task = {"id": "t1", "type": "shell", "status": "running", "description": "tests"}
        self.assertIsNone(self.h.run(bg=[task]))
        cron = {"id": "c1", "schedule": "*/5 * * * *", "recurring": True, "prompt": "check"}
        self.assertIsNone(self.h.run(crons=[cron]))

    def test_unbound_sessions_allowed(self):
        self.h.write_ledger([OPEN])
        self.assertIsNone(self.h.run(env={"Z0_KEEPWORKING": "off"}))
        self.assertIsNone(self.h.run(env={"CLAUDE_CODE_CHILD_SESSION": "1"}))
        self.h.write_ledger([OPEN], enforce="off")
        self.assertIsNone(self.h.run())
        self.h.write_ledger([OPEN], scope_cwd_prefixes=["/nonexistent-scope"])
        self.assertIsNone(self.h.run())

    def test_child_sessions_can_opt_in(self):
        self.h.write_ledger([OPEN], include_child_sessions=True)
        self.assertEqual(self.h.run(env={"CLAUDE_CODE_CHILD_SESSION": "1"})["decision"], "block")

    def test_crash_never_blocks(self):
        out = subprocess.run([sys.executable, "-I", str(HOOK)], input="{not json",
                             env=self.h.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.stdout, "")
        self.assertEqual(out.returncode, 1)

    def test_decisions_are_logged(self):
        self.h.write_ledger([OPEN])
        self.h.run()
        log = (self.h.dir / "state" / "decisions.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(log[-1])["verdict"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
