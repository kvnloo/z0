"""Z5: real resolver/CLI with fake transports, stdlib unittest; never a network send."""
from __future__ import annotations

import copy
import dataclasses
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from tests.onboard import support
from z0.onboard.llm import providers
from z0.onboard.llm.privacy import prompt_for
from z0.onboard.llm.questions import KINDS, collect, question
from z0.onboard.llm.resolve import Context, ReplayError, digest, resolve, response
from z0.onboard.redact import Redactor

SNAP = {"onboarding": {"llm": {"providers": [{"id": "local", "order": 1}],
                                  "budget": {"max_calls": 8, "call_timeout_s": 30,
                                             "total_s": 180, "probe_rounds": 2}},
                        "probes": {"path_exists": {"kind": "exists"},
                                   "path_mode": {"kind": "stat"},
                                   "bin_shebang": {"kind": "shebang"}}},
        "harnesses": {"harnesses": {
            "claude-code": {"policy": {"exec_probe": "allowed", "configure": "allowed"}},
            "grok": {"policy": {"exec_probe": "never", "configure": "never"}},
            "cursor-agent": {"policy": {"exec_probe": "never", "configure": "never"}}}},
        "toolchains": {"tools": {"git": {"system_pkg": {"apt": "git", "brew": "git"}}}}}
CANARY = "LLM-CANARY-NOT-A-CREDENTIAL"


def fork(qid="fork", **kwargs):
    return question({"id": qid, "kind": "fork_match", "facts": {"pin_present": True, **kwargs},
                     "candidates": ["yes", "no"], "safe_default": "no"}, SNAP)


def harness(name="alias", candidates=None):
    return question({"id": "classify", "kind": "harness_classify", "facts": {"name": name},
                     "candidates": candidates or ["claude-code", "grok", "cursor-agent", "unsupported"]}, SNAP)


class FakeProvider:
    def __init__(self, answer='{"answer":"yes"}', pid="local", available=True):
        self.id, self.model = pid, "test-model"
        self.answer, self.ready = answer, available
        self.calls, self.probes = [], 0

    def available(self, timeout=2):
        self.probes += 1
        return self.ready

    def send(self, prompt, timeout):
        self.calls.append((prompt, timeout))
        value = self.answer[len(self.calls) - 1] if isinstance(self.answer, list) else self.answer
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(prompt, timeout)
        return value


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "answers.yaml"
        self.provider = FakeProvider()
        self.ctx = Context(snap=copy.deepcopy(SNAP), env={}, providers=[self.provider],
                           host_id="0" * 16)

    def run_question(self, q=None, **kwargs):
        return resolve([q or fork()], kwargs.pop("mode", "auto"), kwargs.pop("grants", {}),
                       kwargs.pop("llm_flag", "local"), kwargs.pop("path", self.path),
                       context=kwargs.pop("context", self.ctx))["llm"][(q or fork()).id]

    def test_a_valid_candidate_accepted_and_frozen(self):
        row = self.run_question()
        self.assertEqual((row["answer"], row["source"], row["accepted"]), ("yes", "llm", True))
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["answers"]["llm"]["fork"], row)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(row["provider"], "local")
        self.assertEqual(len(row["prompt_sha256"]), 64)

    def test_b_out_of_set_uses_default(self):
        self.provider.answer = '{"answer":"invented"}'
        row = self.run_question()
        self.assertEqual((row["answer"], row["reason"]), ("no", "out_of_set"))

    def test_c_forbidden_providers_never_discovered_or_called(self):
        for pid in ("grok", "cursor", "cursor-agent", "unknown-provider"):
            with self.subTest(pid=pid):
                provider = FakeProvider(pid=pid)
                self.ctx.providers = [provider]
                row = self.run_question(path=None, llm_flag="auto",
                                        grants={"source": "flag", "llm_providers": [pid]})
                self.assertEqual(row["answer"], "no")
                self.assertEqual(row["reason"], "forbidden_provider")
                self.assertEqual((provider.probes, provider.calls), (0, []))

    def test_d_timeout_uses_default_and_does_not_log_error(self):
        self.provider.answer = TimeoutError(CANARY)
        row = self.run_question()
        self.assertEqual((row["answer"], row["reason"]), ("no", "timeout"))
        self.assertNotIn(CANARY, self.path.read_text())

    def test_e_consent_escalation_rejected_by_schema(self):
        for extra in ({"consent": "C2"}, {"confirmed_steps": ["unit"]}, {"state": "todo"},
                      {"provider": "grok"}, {"path": "~/unseen"}, {"grants": {"source": "tty"}}):
            with self.subTest(extra=extra):
                self.provider.answer = json.dumps({"answer": "yes", **extra})
                row = self.run_question(path=None)
                self.assertEqual(row["reason"], "response_schema")
                self.assertEqual(row["answer"], "no")

    def test_f_replay_zero_calls_and_identical_answers(self):
        first = resolve([fork()], "auto", {}, "local", self.path, context=self.ctx)
        original = self.path.read_bytes()
        self.ctx.providers = [FakeProvider(AssertionError("must not send"))]
        with patch.object(providers, "configured", side_effect=AssertionError("no discovery")):
            again = resolve([fork()], "auto", {}, "local", self.path, context=self.ctx)
        self.assertEqual(first, again)
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual(self.ctx.providers[0].calls, [])
        self.assertEqual(self.ctx.providers[0].probes, 0)

    def test_g_canary_aborts_before_even_provider_discovery(self):
        self.ctx.canaries = (CANARY,)
        row = self.run_question(harness(CANARY))
        self.assertEqual(row["reason"], "redaction_failed")
        self.assertEqual((self.provider.calls, self.provider.probes), ([], 0))
        self.assertNotIn(CANARY, self.path.read_text())

    def test_red_fixture_per_guardrail(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures/llm/red-guardrails.json").read_text())
        self.assertEqual({r["guardrail"] for r in fixtures}, set(range(1, 7)))
        for case in fixtures:
            with self.subTest(case=case["name"]):
                ctx = dataclasses.replace(self.ctx, snap=copy.deepcopy(SNAP))
                provider = FakeProvider(json.dumps(case.get("response")))
                ctx.providers = [provider]
                ctx.snap["onboarding"]["llm"]["budget"].update(case.get("budget", {}))
                if case.get("tamper"):
                    resolve([fork()], "auto", {}, "local", self.path, context=self.ctx)
                    saved = json.loads(self.path.read_text())
                    saved["answers"]["llm"]["fork"]["answer"] = "other"
                    self.path.write_text(json.dumps(saved))
                    with self.assertRaises(ReplayError):
                        resolve([fork()], "auto", {}, "local", self.path, context=ctx)
                    self.assertEqual(provider.calls, [])
                    self.path.unlink()
                    continue
                if case.get("canary"):
                    ctx.canaries = (CANARY,)
                row = self.run_question(harness(CANARY) if case.get("canary") else fork(),
                                        context=ctx, path=None)
                self.assertEqual(row["reason"], case["reason"])
                self.assertFalse(row["accepted"])

    def test_schema_rejects_non_json_duplicates_extra_fields_and_wrong_types(self):
        for raw in ('hello', '[]', 'null', '1', '{"answer":true}', '{"answer":{}}',
                    '{"answer":"yes","answer":"no"}',
                    '{"answer":"yes","need_probe":"path_exists"}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                response(raw)

    def test_verifier_is_required_even_for_candidate(self):
        q = question({"id": "fork", "kind": "fork_match", "facts": {"pin_present": False},
                      "candidates": ["yes", "no"]}, SNAP)
        row = self.run_question(q)
        self.assertEqual((row["answer"], row["reason"]), ("no", "verifier_failed"))

    def test_harness_policy_cannot_be_overridden(self):
        self.provider.answer = '{"answer":"grok"}'
        row = self.run_question(harness())
        self.assertEqual((row["answer"], row["reason"]), ("unsupported", "verifier_failed"))

    def test_budget_caps_calls_time_and_per_call_timeout(self):
        questions = [fork(str(i)) for i in range(12)]
        result = resolve(questions, "auto", {}, "local", None, context=self.ctx)
        self.assertEqual(len(self.provider.calls), 8)
        self.assertTrue(all(t <= 30 for _, t in self.provider.calls))
        self.assertEqual(sum(r["accepted"] for r in result["llm"].values()), 8)
        self.assertEqual(result["llm"]["8"]["reason"], "budget_exhausted")

    def test_total_budget_uses_monotonic_time_and_remaining_deadline(self):
        now = [0.0]
        def slow(prompt, timeout):
            now[0] += 29
            return '{"answer":"yes"}'
        self.provider.answer = slow
        self.ctx.clock = lambda: now[0]
        result = resolve([fork(str(i)) for i in range(10)], "auto", {}, "local", None, context=self.ctx)
        self.assertLessEqual(len(self.provider.calls), 7)
        self.assertLessEqual(self.provider.calls[-1][1], 6)
        self.assertEqual(result["llm"]["9"]["reason"], "budget_exhausted")

    def test_real_wall_clock_deadline_bounds_hung_fake(self):
        self.ctx.snap["onboarding"]["llm"]["budget"]["call_timeout_s"] = 0.02
        self.provider.answer = lambda prompt, timeout: time.sleep(1)
        before = time.monotonic()
        row = self.run_question()
        self.assertEqual(row["reason"], "timeout")
        self.assertLess(time.monotonic() - before, 0.5)

    def test_probe_catalog_and_two_round_limit(self):
        q = fork(probe_results={"path_exists": {"exists": True, "contents": CANARY}})
        self.provider.answer = ['{"need_probe":"path_exists"}'] * 3
        row = self.run_question(q)
        self.assertEqual(row["reason"], "probe_rounds")
        self.assertEqual(len(self.provider.calls), 3)
        self.assertNotIn(CANARY, self.provider.calls[-1][0])
        self.assertIn('"exists": true', self.provider.calls[-1][0])

    def test_probe_followup_can_answer(self):
        q = fork(probe_results={"path_exists": {"exists": True}})
        self.provider.answer = ['{"need_probe":"path_exists"}', '{"answer":"yes"}']
        row = self.run_question(q)
        self.assertTrue(row["accepted"])
        import hashlib
        self.assertEqual(row["prompt_sha256"], hashlib.sha256(self.provider.calls[-1][0].encode()).hexdigest())

    def test_content_probe_is_never_executed(self):
        self.provider.answer = '{"need_probe":"bin_shebang"}'
        with patch("builtins.open", side_effect=AssertionError("no file reads")):
            row = self.run_question(path=None)
        self.assertEqual(row["reason"], "probe_unavailable")

    def test_redacts_home_username_hostname_and_registered_secrets(self):
        # Pure synthetic fixture, not an owner's home or hostname.
        redactor = Redactor("/fixture-home", [CANARY])
        q = harness(f"/fixture-home/alice/example.invalid/{CANARY}")
        self.ctx.home, self.ctx.username, self.ctx.hostnames = "/fixture-home", "alice", ("example.invalid",)
        self.ctx.redactor = redactor
        self.provider.answer = '{"answer":"unsupported"}'
        row = self.run_question(q)
        prompt = self.provider.calls[0][0]
        self.assertTrue(row["accepted"])
        for private in ("/fixture-home", "alice", "example.invalid", CANARY):
            self.assertNotIn(private, prompt)
        self.assertIn("~", prompt)
        self.assertIn("host-", prompt)

    def test_failing_redactor_aborts_send(self):
        class Broken(Redactor):
            def __call__(self, text):
                return text
        self.ctx.redactor = Broken(values=[CANARY])
        row = self.run_question(harness(CANARY))
        self.assertEqual(row["reason"], "redaction_failed")
        self.assertEqual(self.provider.calls, [])

    def test_none_skips_context_providers_replay_and_freeze(self):
        with patch("z0.onboard.llm.resolve.default_context", side_effect=AssertionError("context")):
            self.assertEqual(resolve([fork()], "auto", {}, "none", self.path), {})
        self.assertFalse(self.path.exists())

    def test_remote_requires_named_human_grant_and_auto_flag(self):
        self.provider.id = "claude"
        for llm_flag, grants in (("local", {"source": "flag", "llm_providers": ["claude"]}),
                                 ("auto", {}), ("auto", {"source": "llm", "llm_providers": ["claude"]}),
                                 ("auto", {"source": "flag", "bundles": ["harness"]})):
            row = self.run_question(path=None, llm_flag=llm_flag, grants=grants)
            self.assertFalse(row["accepted"])
        self.assertEqual(self.provider.probes, 0)
        for source in ("flag", "tty"):
            row = self.run_question(path=None, llm_flag="auto",
                                    grants={"source": source, "llm_providers": ["claude"]})
            self.assertTrue(row["accepted"])

    def test_replay_refuses_foreign_host_changed_questions_and_changed_grants(self):
        self.run_question()
        for qs, mode, grants, ctx in (([fork("different")], "auto", {}, self.ctx),
                                      ([fork()], "guided", {}, self.ctx),
                                      ([fork()], "auto", {"source": "flag"}, self.ctx),
                                      ([fork()], "auto", {}, dataclasses.replace(self.ctx, host_id="1" * 16))):
            with self.subTest(qs=qs), self.assertRaises(ReplayError):
                resolve(qs, mode, grants, "local", self.path, context=ctx)
        self.assertEqual(len(self.provider.calls), 1)

    def test_replay_refuses_malformed_or_missing_decisions_without_calls(self):
        for text in ('not yaml', '{}', '{"answers":null}'):
            self.path.write_text(text)
            with self.assertRaises(ReplayError):
                self.run_question()
        self.assertEqual(self.provider.probes, 0)

    def test_failure_messages_and_unrecognized_facts_never_reach_prompt(self):
        q = fork(file_contents=CANARY, env={"PRIVATE": CANARY}, stderr=CANARY)
        self.run_question(q)
        self.assertNotIn(CANARY, self.provider.calls[0][0])

    def test_question_verifiers_all_seven_closed_kinds(self):
        cases = [
            ("harness_classify", {"name": "alias"}, ["claude-code", "grok"], "claude-code", "grok"),
            ("config_dir_pick", {"dirs": ["~/one"]}, ["~/one", "~/two"], "~/one", "~/two"),
            ("fork_match", {"pin_present": True}, ["yes", "no"], "yes", "maybe"),
            ("port_owner", {"release_root": "~/release", "executable": "~/release/bin/run"},
             ["adopt", "conflict"], "adopt", "anything"),
            ("gpu_vendor_resolve", {"driver_classes": ["nvidia"]}, ["cpu", "nvidia", "amd"], "nvidia", "amd"),
            ("pkg_hint", {"tool": "git"}, ["git", "not-a-package"], "git", "not-a-package"),
            ("failure_triage", {"remediations": ["retry", "wrong"], "conditions_hold": {"retry": True}},
             ["retry", "wrong"], "retry", "wrong"),
        ]
        # CW6's structured answer contract has its own exhaustive test module.
        self.assertEqual({c[0] for c in cases} | {"first_task_pick"}, set(KINDS))
        for kind, facts, candidates, good, bad in cases:
            q = question({"id": kind, "kind": kind, "facts": facts, "candidates": candidates}, SNAP)
            self.assertTrue(q.accepts(good), kind)
            self.assertFalse(q.accepts(bad), kind)

    def test_port_prefix_traversal_is_not_ownership(self):
        for exe in ("~/release-evil/bin", "~/release/../other/run"):
            q = question({"id": "port", "kind": "port_owner", "facts": {
                "release_root": "~/release", "executable": exe}, "candidates": ["adopt", "conflict"]}, SNAP)
            self.assertFalse(q.accepts("adopt"))

    def test_short_registered_secret_is_not_exempt_from_prompt_redaction(self):
        self.ctx.snap["onboarding"]["llm"]["providers"].append(
            {"id": "openrouter-free", "order": 2, "key_name": "TEST_API_KEY"})
        self.ctx.env = {"TEST_API_KEY": "q!9x"}
        self.provider.answer = '{"answer":"unsupported"}'
        self.run_question(harness("q!9x"))
        self.assertNotIn("q!9x", self.provider.calls[0][0])

    def test_environment_values_not_in_registry_are_still_scrubbed(self):
        self.ctx.env = {"UNREGISTERED_VALUE": CANARY}
        self.provider.answer = '{"answer":"unsupported"}'
        self.run_question(harness(CANARY))
        self.assertNotIn(CANARY, self.provider.calls[0][0])

    def test_escaped_and_unicode_environment_values_are_scrubbed_before_json(self):
        secret = 'fixture-"quoted"-secret-\\\\-é'
        self.ctx.env = {"OTHER_VALUE": secret}
        self.provider.answer = '{"answer":"unsupported"}'
        q = harness(secret)
        self.run_question(q)
        payload = json.loads(self.provider.calls[0][0].split("\n", 1)[1])
        self.assertNotEqual(payload["facts"]["name"], secret)
        self.assertEqual(payload["facts"]["name"], "[redacted]")

    def test_unicode_identity_is_redacted_before_serialization(self):
        self.ctx.home, self.ctx.username, self.ctx.hostnames = "/fixture-é", "usér", ("höst.invalid",)
        self.ctx.redactor = Redactor(self.ctx.home)
        self.provider.answer = '{"answer":"unsupported"}'
        self.run_question(harness("/fixture-é/usér/höst.invalid"))
        payload = json.loads(self.provider.calls[0][0].split("\n", 1)[1])
        self.assertNotIn("usér", payload["facts"]["name"])
        self.assertNotIn("höst.invalid", payload["facts"]["name"])
        self.assertTrue(payload["facts"]["name"].startswith("~/"))

    def test_projection_rejects_nested_payload_in_a_scalar_fact(self):
        q = question({"id": "nested", "kind": "harness_classify", "facts": {
            "name": {"file_contents": CANARY}, "shebang": [CANARY]},
            "candidates": ["unsupported"]}, SNAP)
        self.assertNotIn(CANARY, json.dumps(q.payload()))

    def test_provider_fallback_order_skips_unavailable_and_ungranted(self):
        local, remote = FakeProvider(available=False), FakeProvider(pid="claude")
        forbidden = FakeProvider(pid="grok")
        self.ctx.providers = [forbidden, local, remote]
        row = self.run_question(llm_flag="auto", grants={"source": "flag", "llm_providers": ["claude"]})
        self.assertEqual(row["provider"], "claude")
        self.assertEqual(forbidden.probes, 0)
        self.assertEqual(local.calls, [])
        self.assertEqual(len(remote.calls), 1)

    def test_replay_rechecks_policy_even_when_attacker_rehashes(self):
        self.provider.answer = TimeoutError()
        self.run_question()
        saved = json.loads(self.path.read_text())
        row = saved["answers"]["llm"]["fork"]
        row.update(provider="grok", model="test-model")
        saved["answers_sha256"] = digest(saved["answers"])
        self.path.write_text(json.dumps(saved))
        with self.assertRaises(ReplayError):
            self.run_question()
        self.assertEqual(len(self.provider.calls), 1)


class ProviderTests(unittest.TestCase):
    def test_registry_order_and_model_defaults(self):
        snap = {"onboarding": {"llm": {"claude_model": "configured-haiku", "codex_model": "configured-sol",
                "providers": [{"id": "codex", "order": 3}, {"id": "local", "order": 1},
                              {"id": "claude", "order": 2}]}}}
        out = providers.configured(snap, {})
        self.assertEqual([p.id for p in out], ["local", "claude", "codex"])
        self.assertEqual([p.model for p in out][1:], ["configured-haiku", "configured-sol"])

    def test_claude_argv_tools_mcp_turns_and_stdin(self):
        provider = providers.Provider("claude", "haiku", env={})
        provider.executable = "/fixture-bin/claude"
        def run(argv, **kwargs):
            self.assertEqual(argv[:7], ["/fixture-bin/claude", "-p", "--output-format", "json", "--model", "haiku",
                                       "--strict-mcp-config"])
            self.assertEqual(argv[argv.index("--tools") + 1], "")
            self.assertEqual(argv[argv.index("--max-turns") + 1], "1")
            self.assertIn("--safe-mode", argv)
            self.assertIn("--no-session-persistence", argv)
            self.assertEqual(argv[argv.index("--setting-sources") + 1], "")
            self.assertEqual(json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text()), {"mcpServers": {}})
            self.assertEqual(kwargs["input"], "redacted prompt")
            self.assertNotIn("redacted prompt", argv)
            return subprocess.CompletedProcess(argv, 0, '{"result":"{\\"answer\\":\\"yes\\"}"}', CANARY)
        with patch.object(providers.subprocess, "run", side_effect=run):
            self.assertEqual(provider.send("redacted prompt", 3), '{"answer":"yes"}')

    def test_codex_readonly_schema_and_stdin(self):
        provider = providers.Provider("codex", "gpt-6.1-sol", env={})
        provider.executable = "/fixture-bin/codex"
        def run(argv, **kwargs):
            self.assertEqual(argv[1:7], ["exec", "--sandbox", "read-only", "--skip-git-repo-check", "-m", "gpt-6.1-sol"])
            schema = json.loads(Path(argv[argv.index("--output-schema") + 1]).read_text())
            self.assertEqual(schema, providers.ANSWER_SCHEMA)
            Path(argv[argv.index("--output-last-message") + 1]).write_text('{"answer":"yes"}')
            self.assertEqual(argv[-1], "-")
            for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules"):
                self.assertIn(flag, argv)
            disabled = {argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "--disable"}
            self.assertTrue({"shell_tool", "unified_exec", "hooks", "plugins", "multi_agent"} <= disabled)
            return subprocess.CompletedProcess(argv, 0, CANARY, CANARY)
        with patch.object(providers.subprocess, "run", side_effect=run):
            self.assertEqual(provider.send("safe", 3), '{"answer":"yes"}')

    def test_gateway_key_only_in_header_and_no_paid_model_fallback(self):
        provider = providers.Provider("openrouter-free", "openrouter/free", {"key_name": "TEST_API_KEY"},
                                      {"TEST_API_KEY": CANARY})
        self.assertTrue(provider.available())
        def http(url, body, timeout, headers):
            self.assertEqual(headers["Authorization"], "Bearer " + CANARY)
            self.assertNotIn(CANARY, url + json.dumps(body))
            return {"choices": [{"message": {"content": '{"answer":"yes"}'}}]}
        with patch.object(providers, "http_json", side_effect=http):
            self.assertEqual(provider.send("safe", 3), '{"answer":"yes"}')
        provider.model = "paid-model"
        self.assertFalse(provider.available())
        provider.env = {}
        self.assertFalse(provider.available())
        self.assertNotIn(CANARY, repr(provider))

    def test_local_detection_reads_process_names_not_secret_bearing_argv(self):
        result = subprocess.CompletedProcess([], 0, "llama-server\nollama\n", "")
        with patch.object(providers.subprocess, "run", return_value=result) as run:
            endpoints = providers.local_endpoints({})
        self.assertEqual(run.call_args.args[0], ["ps", "-axo", "comm="])
        self.assertEqual(len(endpoints), 2)
        self.assertTrue(all(url.startswith("http://127.0.0.1:") for url, _ in endpoints))

    def test_local_not_running_is_not_started(self):
        provider = providers.Provider("local", "", env={})
        with patch.object(providers, "local_endpoints", return_value=[]), \
                patch.object(providers, "http_json", side_effect=AssertionError("no network")):
            self.assertFalse(provider.available())

    def test_local_discovery_only_smokes_detected_loopback(self):
        provider = providers.Provider("local", "", env={})
        with patch.object(providers, "local_endpoints", return_value=[("http://127.0.0.1:8080", "llama")]), \
                patch.object(providers, "http_json", return_value={"data": [{"id": "detected"}]}) as http:
            self.assertTrue(provider.available())
            self.assertEqual(provider.model, "detected")
            self.assertEqual(http.call_count, 1)

    def test_ollama_detects_loaded_models_only(self):
        provider = providers.Provider("local", "", env={})
        def http(url, body, timeout):
            # An installed but unloaded model must not be started by classification.
            return {"models": [] if url.endswith("/api/ps") else [{"name": "unloaded"}]}
        with patch.object(providers, "local_endpoints", return_value=[("http://127.0.0.1:11434", "ollama")]), \
                patch.object(providers, "http_json", side_effect=http):
            self.assertFalse(provider.available())
            self.assertEqual(provider.endpoint, "")

    def test_ollama_uses_an_already_loaded_model(self):
        provider = providers.Provider("local", "", env={})
        with patch.object(providers, "local_endpoints", return_value=[("http://127.0.0.1:11434", "ollama")]), \
                patch.object(providers, "http_json", return_value={"models": [{"name": "loaded"}]}):
            self.assertTrue(provider.available())
            self.assertEqual(provider.model, "loaded")

    def test_redirects_are_never_followed(self):
        self.assertIsNone(providers.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid"))


@support.require_yaml
class PlanIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.snap = support.snapshot()
        self.host = support.fixture("laptop-cpu-15g")
        self.host["unknowns"] = [{"id": "fork", "kind": "fork_match", "facts": {"pin_present": True},
                                  "candidates": ["yes", "no"], "safe_default": "no"}]
        self.provider = FakeProvider()
        self.ctx = Context(snap=self.snap, env={}, providers=[self.provider], host_id=self.host["host_id"])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_replay_same_real_plan_hash_and_no_calls(self):
        from z0.onboard.plan import collect_questions, plan
        path = Path(self.tmp.name) / "answers.yaml"
        qs = collect_questions(self.host, self.snap)
        first = resolve(qs, "auto", {}, "local", path, context=self.ctx)
        p1 = plan(self.host, self.snap, answers=first)
        second = resolve(qs, "auto", {}, "local", path, context=self.ctx)
        p2 = plan(self.host, self.snap, answers=second)
        self.assertEqual(p1, p2)
        self.assertEqual(len(self.provider.calls), 1)
        validator = support.validator("onboard-plan")
        if validator:
            self.assertEqual(list(validator.iter_errors(p1)), [])

    def test_answers_do_not_change_any_step_state_path_or_consent(self):
        from z0.onboard.plan import collect_questions, plan
        before = plan(self.host, self.snap)
        answers = resolve(collect_questions(self.host, self.snap), "auto", {}, "local", None, context=self.ctx)
        answers["confirmed_steps"] = [s["step"]["id"] for s in before["steps"]]
        after = plan(self.host, self.snap, answers=answers)
        for key in ("steps", "grants", "components", "prepared_path", "asks"):
            self.assertEqual(before[key], after[key], key)

    def test_none_cli_does_not_invoke_resolver(self):
        from z0.onboard import cli
        args = cli.build_parser().parse_args(["plan", "--llm=none"])
        args.mode = "auto"
        base = cli._make_plan(self.host, self.snap, args, None)
        with patch("z0.onboard.llm.resolve.resolve", side_effect=AssertionError("resolver disabled")):
            self.assertEqual(cli._resolve_plan(self.host, self.snap, args, None, base), base)

    def test_cli_freezes_answers_in_run_and_replays_exact_hash(self):
        from z0.onboard import cli
        args = cli.build_parser().parse_args(["plan"])
        args.mode = "auto"
        base = cli._make_plan(self.host, self.snap, args, None)
        with patch("z0.onboard.llm.providers.configured", return_value=[self.provider]), \
                patch.dict(os.environ, {"Z0_HOME": self.tmp.name}):
            planned = cli._resolve_plan(self.host, self.snap, args, None, base)
            run = cli.write_run_dir(self.host, planned, self.snap)
            self.assertTrue((run / "answers.yaml").is_file())
            args.answers = str(run / "answers.yaml")
            self.provider.calls.clear()
            again = cli._resolve_plan(self.host, self.snap, args, None, base)
        self.assertEqual(planned, again)
        self.assertEqual(self.provider.calls, [])

    def test_remote_confirmation_is_listed_and_decline_keeps_grants(self):
        from z0.onboard import cli
        args = cli.build_parser().parse_args(["--auto", "--llm=auto"])
        base = cli._make_plan(self.host, self.snap, args, None)
        captured = []
        def confirm(lines):
            captured.extend(lines)
            return True
        with patch.object(cli, "_tty", return_value=True), patch.object(cli, "_confirm", side_effect=confirm), \
                patch.object(cli, "_llm_offers", return_value=["claude"]):
            planned, _, _ = cli._consent(args, self.host, self.snap, None, base)
        self.assertIn("  LLM: up to 8 calls via claude (your quota)", captured)
        self.assertEqual(planned["grants"]["llm_providers"], ["claude"])
        with patch.object(cli, "_tty", return_value=False), patch.object(cli, "_llm_offers", return_value=["claude"]):
            planned, _, _ = cli._consent(args, self.host, self.snap, None, base)
        self.assertNotIn("llm_providers", planned["grants"])

    def test_missing_cli_replay_path_never_creates_a_file_or_calls(self):
        from z0.onboard import cli
        from z0.onboard.plan import PlanError
        missing = Path(self.tmp.name) / "missing.yaml"
        args = cli.build_parser().parse_args(["plan", "--stdout", "--answers", str(missing)])
        args.mode = "auto"
        base = cli._make_plan(self.host, self.snap, args, None)
        with self.assertRaises(PlanError):
            cli._resolve_plan(self.host, self.snap, args, None, base, pure=True)
        self.assertFalse(missing.exists())
        self.assertEqual(self.provider.calls, [])

    def test_freshness_replan_reuses_answers_and_defaults_on_new_facts(self):
        from z0.onboard import cli
        from z0.onboard.apply import request_from_plan
        from z0.onboard.plan import collect_questions, plan
        grants = {"source": "none", "bundles": []}
        answers = resolve(collect_questions(self.host, self.snap), "auto", grants, "local", None, context=self.ctx)
        first = plan(self.host, self.snap, answers=answers)
        request = request_from_plan(first, self.snap)
        replan = cli.replan_from(self.snap)
        self.assertEqual(replan(self.host, request), first)
        changed = copy.deepcopy(self.host)
        changed["unknowns"][0]["facts"]["pin_present"] = False
        again = replan(changed, request)
        self.assertEqual(again["llm_decisions"][0]["answer"], "no")
        self.assertEqual(again["llm_decisions"][0]["reason"], "facts_changed")
        self.assertEqual(len(self.provider.calls), 1)

    def test_verify_receipt_and_report_use_actual_plan_decisions(self):
        from tests.onboard.fakeapply import FakeApply
        from z0.onboard.apply import apply_run
        from z0.onboard.plan import collect_questions, plan
        from z0.onboard.verify import verify_run
        fake = FakeApply(Path(self.tmp.name))
        host = fake.detect()
        host["unknowns"] = self.host["unknowns"]
        ctx = Context(snap=fake.snap, env={}, providers=[self.provider], host_id=host["host_id"])
        answers = resolve(collect_questions(host, fake.snap), "auto", {}, "local", None, context=ctx)
        request = fake.request()
        request.pop("llm")
        planned = plan(host, fake.snap, llm="local", answers=answers, **request)
        run = fake.write_run(host, planned)
        deps = fake.deps(detect=False)
        applied = apply_run(run, deps)
        code, receipt = verify_run(run, deps, prior=applied.results, host=host, apply_code=applied.code)
        self.assertEqual(receipt["llm_decisions"], planned["llm_decisions"])
        self.assertIn("fork [fork_match]: yes", (run / "report.md").read_text())
        self.assertEqual(json.loads((run / "receipt.json").read_text())["llm_decisions"], planned["llm_decisions"])
        self.assertEqual(code, 0)

    def test_report_lists_decisions_and_reasons(self):
        from z0.onboard.plan import collect_questions, plan
        from z0.onboard.report import render
        answers = resolve(collect_questions(self.host, self.snap), "auto", {}, "local", None, context=self.ctx)
        planned = plan(self.host, self.snap, answers=answers)
        receipt = {"run_id": "fixture", "exit_code": 0, "asks": [], "steps": [], "installed": [],
                   "acceptance": {}, "harnesses": {}, "llm_decisions": planned["llm_decisions"],
                   "secrets_scan": {"canary_found": False}}
        text = render(planned, receipt, [], [])
        self.assertIn("fork [fork_match]: yes", text)
        self.assertIn("verified", text)
        self.assertNotIn("arrives in work package Z5", text)


if __name__ == "__main__":
    unittest.main()
