"""Transient network errors and off-path failures (onboarding robustness).

Red/green for two bugs a cold agent cell hit (agent.claude.frontend.run2): one transient
`git clone` failure of a component off the first-task path ended the whole run with
exit 1, and the agent stopped to ask instead of picking a first task.

- Retry: network steps that are safe to repeat (clone, submodule/LFS pull, toolchain
  download) get a bounded backoff (2, 5, 10 s); a recovery is a report warning.
- Degraded: a failure off `onboarding.first_task_path` finishes the run with exit 5,
  `onboard/state` says ok + degraded, and the report lists it under "Failed". A failure
  on the path (z0intelligence, z0evals, the hub, a tool they need) still exits 1.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.onboard.fakeapply import FakeApply
from tests.onboard.support import ROOT, require_yaml, validator


def ctx_for(tmp: str, sleeps: list):
    from z0.onboard.actions.base import ActionCtx
    return ActionCtx(z0_home=tmp + "/.z0", home=tmp, run_id="r", run_dir=Path(tmp), journal=None,
                     plan={"steps": []}, snap={}, host={}, repo_root=str(ROOT), sleep=sleeps.append)


class Retrying(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sleeps: list = []
        self.ctx = ctx_for(self.tmp.name, self.sleeps)
        self.ctx.step_id = "x.source"

    def tearDown(self):
        self.tmp.cleanup()

    def flaky(self, failures: int):
        calls = []

        def attempt() -> bool:
            calls.append(1)
            return len(calls) > failures
        return attempt, calls

    def test_first_try_succeeds_without_sleeping(self):
        attempt, calls = self.flaky(0)
        self.assertTrue(self.ctx.retrying("git clone of u", attempt))
        self.assertEqual((len(calls), self.sleeps, self.ctx.warnings), (1, [], []))

    def test_recovers_after_backoff_and_warns(self):
        attempt, calls = self.flaky(2)
        self.assertTrue(self.ctx.retrying("git clone of u", attempt))
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.sleeps, [2.0, 5.0])
        self.assertEqual(len(self.ctx.warnings), 1)
        self.assertIn("succeeded after 2 retries", self.ctx.warnings[0])

    def test_is_bounded(self):
        attempt, calls = self.flaky(99)
        self.assertFalse(self.ctx.retrying("git clone of u", attempt))
        self.assertEqual(len(calls), 4)
        self.assertEqual(self.sleeps, [2.0, 5.0, 10.0])
        self.assertEqual(self.ctx.warnings, [])


class Download(unittest.TestCase):
    def test_transient_error_is_retried_and_4xx_is_not(self):
        import urllib.error
        from z0.onboard.actions.ensure_toolchain import _download
        with tempfile.TemporaryDirectory() as tmp:
            sleeps: list = []
            ctx = ctx_for(tmp, sleeps)
            dest = Path(tmp) / "download"
            tries = []

            def flaky(url, path):
                tries.append(url)
                if len(tries) == 1:
                    Path(path).write_bytes(b"partial")
                    raise urllib.error.URLError("connection reset")
                Path(path).write_bytes(b"whole")
            ctx.fetch = flaky
            _download(ctx, "https://example.invalid/a.tgz", str(dest))
            self.assertEqual((len(tries), sleeps, dest.read_bytes()), (2, [2.0], b"whole"))

            def gone(url, path):
                tries.append(url)
                raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
            ctx.fetch, tries[:] = gone, []
            with self.assertRaises(urllib.error.HTTPError):
                _download(ctx, "https://example.invalid/a.tgz", str(dest))
            self.assertEqual(len(tries), 1, "a 4xx is permanent: no retry")


class Classify(unittest.TestCase):
    def plan(self, *steps):
        return {"steps": [{"step": {"id": sid, "component": cid}, "state": {}} for sid, cid in steps]}

    def classify(self, plan, results, checks=(), crit=("z0intelligence", "z0evals"), users=None):
        from z0.onboard import degrade
        snap = {"onboarding": {"first_task_path": list(crit)}}
        return degrade.classify(plan, results, list(checks), snap, users or {})

    def test_off_path_component_failure_degrades(self):
        plan = self.plan(("tokenomics.source", "tokenomics"), ("z0evals.source", "z0evals"))
        crit, degraded = self.classify(plan, {"tokenomics.source": {"status": "failed"},
                                              "z0evals.source": {"status": "passed"}})
        self.assertEqual((crit, degraded), ([], ["tokenomics"]))

    def test_first_task_path_hub_and_unowned_failures_are_critical(self):
        plan = self.plan(("z0intelligence.source", "z0intelligence"), ("z0.hub", "z0"), ("loose", None))
        results = {sid: {"status": "failed"} for sid in ("z0intelligence.source", "z0.hub", "loose")}
        crit, degraded = self.classify(plan, results)
        self.assertEqual((sorted(crit), degraded), (["loose", "z0.hub", "z0intelligence.source"], []))

    def test_a_toolchain_degrades_only_when_no_path_component_needs_it(self):
        plan = self.plan(("toolchain.bun", None), ("toolchain.uv", None))
        results = {"toolchain.bun": {"status": "failed"}, "toolchain.uv": {"status": "failed"}}
        users = {"toolchain.bun": {"dash"}, "toolchain.uv": {"dash", "z0intelligence"}}
        crit, degraded = self.classify(plan, results, users=users)
        self.assertEqual((crit, degraded), (["toolchain.uv"], ["toolchain.bun"]))

    def test_failed_checks_follow_the_same_rule(self):
        checks = [{"component": "dash", "name": "selftest"}, {"component": "z0evals", "name": "tiers"}]
        crit, degraded = self.classify(self.plan(), {}, checks)
        self.assertEqual((crit, degraded), (["z0evals.tiers"], ["dash"]))

    def test_without_a_declared_path_every_failure_is_critical(self):
        plan = self.plan(("tokenomics.source", "tokenomics"))
        crit, degraded = self.classify(plan, {"tokenomics.source": {"status": "failed"}}, crit=())
        self.assertEqual((crit, degraded), (["tokenomics.source"], []))

    def test_the_registry_declares_the_first_task_path(self):
        require_yaml(self)
        from z0.onboard import degrade, regsnap
        self.assertEqual(degrade.first_task_path(regsnap.load()), {"z0intelligence", "z0evals"})


def failing_clone(times: int, log: list):
    """A runner whose first `times` `git clone` calls leave a partial tree and fail like a
    dropped connection; everything else runs for real."""
    from z0.onboard.actions.base import RunResult, subprocess_runner

    def runner(argv, cwd, env, timeout):
        if len(argv) > 1 and argv[1] == "clone" and len(log) < times:
            log.append(argv[-1])
            Path(argv[-1]).mkdir(parents=True, exist_ok=True)
            (Path(argv[-1]) / "half-written").write_text("x")
            return RunResult(128, "fatal: unable to access: Could not resolve host")
        return subprocess_runner(argv, cwd, env, timeout)
    return runner


class CloneRecoversOnRetry(unittest.TestCase):
    """GREEN: one transient clone failure no longer fails the run."""

    @classmethod
    def setUpClass(cls):
        require_yaml(cls)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fa = FakeApply(Path(cls.tmp.name))
        cls.clones: list = []
        cls.fa.runner = failing_clone(1, cls.clones)
        cls.run_dir, cls.result, cls.code, cls.receipt = cls.fa.onboard()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exit_0_after_one_backoff(self):
        self.assertEqual(self.code, 0, (self.run_dir / "report.md").read_text())
        self.assertEqual(len(self.clones), 1)
        self.assertEqual(self.fa.sleeps, [2.0])

    def test_the_partial_tree_is_gone_and_the_clone_is_whole(self):
        tree = self.fa.z0_home / "repos" / "z0evals"
        self.assertTrue((tree / ".git").is_dir())
        self.assertFalse((tree / "half-written").exists())
        self.assertFalse(Path(str(tree) + ".z0-partial").exists())

    def test_the_report_shows_the_recovery(self):
        self.assertIn("succeeded after 1 retry", (self.run_dir / "report.md").read_text())


class CloneOnThePathStillFails(unittest.TestCase):
    """RED stays red: a clone that never recovers, on the first-task path, exits 1."""

    def test_exit_1_after_bounded_retries(self):
        require_yaml(self)
        with tempfile.TemporaryDirectory() as tmp:
            fa = FakeApply(Path(tmp))
            clones: list = []
            fa.runner = failing_clone(99, clones)
            run, _result, code, receipt = fa.onboard()
            self.assertEqual(code, 1)
            self.assertEqual(fa.sleeps, [2.0, 5.0, 10.0])
            failed = {s["id"]: s.get("reason", "") for s in receipt["steps"] if s["status"] == "failed"}
            self.assertIn("z0evals.source", failed)
            self.assertIn("failed after 4 attempts", failed["z0evals.source"])
            self.assertNotIn("degraded", receipt)


class OffPathFailureDegrades(unittest.TestCase):
    """GREEN: a failure off the first-task path finishes the run with exit 5."""

    @classmethod
    def setUpClass(cls):
        require_yaml(cls)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fa = FakeApply(Path(cls.tmp.name))
        # In this fake host z0evals plays the off-path component (tokenomics in the
        # failed cell): the declared path is z0intelligence only.
        cls.fa.snap["onboarding"]["first_task_path"] = ["z0intelligence"]
        cls.fa.runner = failing_clone(99, [])
        cls.run_dir, cls.result, cls.code, cls.receipt = cls.fa.onboard()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exit_5_names_the_component(self):
        self.assertEqual(self.code, 5)
        self.assertEqual(self.receipt["exit_code"], 5)
        self.assertEqual(self.receipt["degraded"], ["z0evals"])

    def test_the_run_finished_past_the_failure(self):
        # the hub checks after the failed clone still ran and passed
        self.assertEqual(self.receipt["acceptance"]["z0"]["memento_never_planned"], "passed")

    def test_report_lists_it_under_failed_and_says_go_on(self):
        text = (self.run_dir / "report.md").read_text()
        self.assertIn("Degraded: z0evals failed", text)
        self.assertIn("Failed (fix, then re-run `./z0 onboard`):", text)
        self.assertIn("- z0evals.source:", text)

    def test_state_is_ok_and_degraded_for_z0int_contribute(self):
        from z0.onboard import handoff
        state = handoff.state_record(self.run_dir, self.receipt, str(ROOT))
        self.assertTrue(state["ok"])
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["degraded"], ["z0evals"])
        self.assertIn("z0evals.source", state["failed"])

    def test_receipt_matches_schema(self):
        check = validator("onboard-receipt")
        if check is None:
            self.skipTest("jsonschema not installed")
        self.assertEqual(sorted(e.message for e in check.iter_errors(self.receipt)), [])


class StateContract(unittest.TestCase):
    def test_exit_1_and_canary_are_never_ok(self):
        from z0.onboard import handoff
        base = {"steps": [{"id": "t.source", "status": "failed"}], "degraded": ["t"]}
        self.assertFalse(handoff.state_record(Path("/r"), {**base, "exit_code": 1}, str(ROOT))["ok"])
        canary = {**base, "exit_code": 5, "secrets_scan": {"canary_found": True}}
        self.assertFalse(handoff.state_record(Path("/r"), canary, str(ROOT))["ok"])


class AgentInstructions(unittest.TestCase):
    """The start-here protocol must treat exit 5 as continue-to-step-3."""

    def test_agents_md_says_exit_5_continues(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        start = text.split("## Start here", 1)[1].split("\n## ", 1)[0]
        self.assertIn("exit 5", start)
        self.assertRegex(start, r"exit 5[^.]*(continue|go on)")


if __name__ == "__main__":
    unittest.main()
