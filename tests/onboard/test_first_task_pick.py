"""CW6 closed contributor question through the real bounded Z5 resolver."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.onboard.test_llm import FakeProvider, SNAP
from z0.onboard.llm import providers
from z0.onboard.llm.questions import question
from z0.onboard.llm.resolve import Context, resolve


def first_task_question():
    return {"id": "first-task", "kind": "first_task_pick", "candidates": ["task-a", "task-b"],
            "facts": {"profile": {"skills": ["python"], "interests": ["docs"],
                                   "contrib_done": 0, "tier": "T1"},
                      "tasks": [{"id": tid, "title": "Test task", "kind": "docs", "skills": ["python", "docs"],
                                 "difficulty": "S", "impact_note": "Improves coverage", "tier": "P1"}
                                for tid in ["task-a", "task-b"]]}}


class FirstTaskPickTests(unittest.TestCase):
    def setUp(self):
        self.q = question(first_task_question(), SNAP)
        self.provider = FakeProvider()
        self.ctx = Context(snap=copy.deepcopy(SNAP), env={}, providers=[self.provider], host_id="0" * 16)

    def run_pick(self, answer, path=None):
        self.provider.answer = answer if isinstance(answer, Exception) else json.dumps(answer)
        return resolve([self.q], "auto", {}, "local", path, context=self.ctx)["llm"][self.q.id]

    def assert_default(self, answer, reason):
        row = self.run_pick(answer)
        self.assertEqual(row["answer"], {"pick": "task-a", "reason_codes": []})
        self.assertEqual(row["reason"], reason)
        self.assertEqual(len(self.provider.calls), 1)

    def test_first_task_pick_non_candidate(self):
        self.assert_default({"pick": "invented", "reason_codes": ["tier:P1"]}, "out_of_set")

    def test_first_task_pick_invented_code(self):
        self.assert_default({"pick": "task-b", "reason_codes": ["write:text"]}, "verifier_failed")

    def test_first_task_pick_disagreeing_code(self):
        for code in ["tier:P0", "skill_match:rust", "interest:python", "first_task_size:L", "size:S"]:
            with self.subTest(code=code):
                self.provider.calls.clear()
                self.assert_default({"pick": "task-b", "reason_codes": [code]}, "verifier_failed")

    def test_first_task_pick_timeout(self):
        self.assert_default(TimeoutError("private error"), "timeout")

    def test_first_task_pick_valid_frozen_replay_zero_calls(self):
        answer = {"pick": "task-b", "reason_codes": ["tier:P1", "skill_match:python", "interest:docs", "first_task_size:S"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answers.yaml"
            row = self.run_pick(answer, path)
            self.assertTrue(row["accepted"])
            self.assertEqual(row["answer"], answer)
            before = path.read_bytes()
            self.provider.calls.clear()
            self.provider.probes = 0
            with patch.object(providers, "configured", side_effect=AssertionError("discovery")):
                replay = resolve([self.q], "auto", {}, "local", path, context=self.ctx)
            self.assertEqual(replay["llm"][self.q.id], row)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual((self.provider.calls, self.provider.probes), ([], 0))

    def test_first_task_pick_t3_aborts(self):
        for key, value in [("repo_names", ["private"]), ("instruction_text", "private"), ("tier", "T3")]:
            raw = first_task_question()
            raw["facts"]["profile"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                question(raw, SNAP)
        self.assertEqual((self.provider.calls, self.provider.probes), ([], 0))

    def test_first_task_pick_one_call_no_probes_and_shared_budget(self):
        self.assert_default({"need_probe": "path_exists"}, "response_schema")
        self.ctx.snap["onboarding"]["llm"]["budget"]["max_calls"] = 0
        self.provider.calls.clear()
        row = self.run_pick({"pick": "task-b", "reason_codes": ["tier:P1"]})
        self.assertEqual(row["reason"], "budget_exhausted")
        self.assertEqual(self.provider.calls, [])

    def test_first_task_pick_transport_uses_closed_schema(self):
        from z0.onboard.llm.privacy import prompt_for
        from z0.onboard.redact import Redactor
        prompt = prompt_for(self.q, Redactor())
        provider = providers.Provider("local", "loaded", endpoint="unused", protocol="ollama")
        with patch.object(providers, "http_json", return_value={"message": {"content": "{}"}}) as http:
            provider.send(prompt, 1)
        self.assertEqual(http.call_args.args[1]["format"], self.q.payload()["answer_schema"])
