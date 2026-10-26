"""APPLY / VERIFY / ROLLBACK on a fake host (design §10 layer 2, §11 laws).

Each law has a green case (the engine keeps it) and a red case (an input that would
violate it is caught): I1 idempotence, R1/R2 rollback ownership, S1 never through a
checkout, C1/C2 consent (the kernel re-decides every step), L-LLM, P1 (grok never
runs), X1 (no secret output), H1 (other host), freshness re-plan, and the lock.
Nothing here touches the real host: HOME, Z0_HOME, the z0evals origin and every
program the steps run live in a temp dir.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from tests.onboard import fakehost
from tests.onboard.fakeapply import FakeApply, tree_bytes
from tests.onboard.support import require_yaml, validator

TOOLCHAINS = {"bundles": ["toolchains"], "source": "flag"}


def todo(plan_obj):
    from z0.onboard.plan import todo_ids
    return todo_ids(plan_obj)


def grep_tree(root: Path, needle: bytes) -> list:
    hits = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            try:
                if needle in Path(path).read_bytes():
                    hits.append(path)
            except OSError:
                pass
    return hits


@require_yaml
class RealPipPath(unittest.TestCase):
    """The registry's own z0evals steps (python3 -m venv, .venv/bin/pip install -r),
    offline, on a fresh fake host: clone, venv, install, tier 0 and tier 1 pass, the
    web tier is unavailable offline, and a second plan has no todo (I1)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fa = FakeApply(Path(cls.tmp.name), fast=False)
        cls.run_dir, cls.result, cls.code, cls.receipt = cls.fa.onboard()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_z0evals_end_to_end(self):
        self.assertEqual(self.code, 0, json.dumps(self.receipt["steps"], indent=1))
        acc = self.receipt["acceptance"]["z0evals"]
        self.assertEqual((acc["tier0"], acc["tier1"], acc["tier2"]), ("passed", "passed", "unavailable"))
        self.assertEqual(acc["tiers"], "passed")
        self.assertEqual(acc["venv"], "passed")
        clone = self.fa.z0_home / "repos" / "z0evals"
        self.assertTrue((clone / ".venv" / "bin" / "python").exists())
        self.assertTrue((clone / ".venv" / ".z0" / f"requirements-{self.fa.sha}").is_file())
        self.assertEqual(self.result.results["z0evals.deps"]["status"], "passed")

    def test_I1_second_plan_has_no_todo(self):
        host = self.fa.detect()
        again = self.fa.plan(host, self.fa.request())
        self.assertEqual(todo(again), [])
        self.assertEqual(host["workspace"]["host_match"], "same")


@require_yaml
class CloneFlow(unittest.TestCase):
    """A fresh host, z0evals cloned (fast venv), offline; no C1 grant."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fa = FakeApply(Path(cls.tmp.name))
        cls.before = tree_bytes(cls.fa.home)
        cls.run_dir, cls.result, cls.code, cls.receipt = cls.fa.onboard()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exit_and_acceptance(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(self.receipt["acceptance"]["z0evals"]["tiers"], "passed")
        self.assertEqual(self.receipt["acceptance"]["z0"]["memento_never_planned"], "passed")

    def test_receipt_matches_schema(self):
        check = validator("onboard-receipt")
        if check is None:
            self.skipTest("jsonschema not installed")
        errors = sorted(e.message for e in check.iter_errors(self.receipt))
        self.assertEqual(errors, [])

    def test_run_dir_is_private(self):
        self.assertEqual(os.stat(self.run_dir).st_mode & 0o777, 0o700)
        for name in ("journal.jsonl", "receipt.json", "report.md"):
            self.assertEqual(os.stat(self.run_dir / name).st_mode & 0o777, 0o600, name)

    def test_journal_records_every_effect_in_plan_form(self):
        from z0.onboard import journal
        effects = journal.effects(journal.read(self.run_dir / "journal.jsonl"))
        paths = [e["effect"]["path"] for e in effects]
        self.assertIn("$Z0_HOME/repos/z0evals", paths)
        self.assertIn("$Z0_HOME/workspace.yaml", paths)
        self.assertIn("$Z0_HOME/onboard/current", paths)
        home = str(self.fa.home)
        text = (self.run_dir / "journal.jsonl").read_text()
        self.assertNotIn(home, text, "an absolute home path reached the journal")
        for effect in effects:
            if effect["effect"]["kind"] == "file":
                self.assertRegex(effect["effect"]["sha256"], r"^[0-9a-f]{64}$")

    def test_workspace_yaml(self):
        import yaml
        data = yaml.safe_load((self.fa.z0_home / "workspace.yaml").read_text())
        self.assertEqual(data["host_id"], self.result.plan["host_id"])
        self.assertEqual(data["components"]["z0evals"]["ref"], self.fa.sha)
        self.assertTrue(data["components"]["z0evals"]["path"].startswith("~/"))

    def test_current_points_at_an_applied_run(self):
        from z0.onboard import journal
        link = self.fa.z0_home / "onboard" / "current"
        target = os.readlink(link)
        self.assertTrue(target.startswith("runs/"), target)  # relative: no absolute path
        effects = journal.effects(journal.read(self.run_dir / "journal.jsonl"))
        self.assertIn({"kind": "symlink", "path": "$Z0_HOME/onboard/current", "prior": None,
                       "target": f"runs/{self.run_dir.name}"}, [e["effect"] for e in effects])

    def test_I1_second_plan_has_no_todo_and_second_apply_has_no_effects(self):
        from z0.onboard import journal
        from z0.onboard.apply import apply_run
        host = self.fa.detect()
        again = self.fa.plan(host, self.fa.request())
        self.assertEqual(todo(again), [])
        run2 = self.fa.write_run(host, again)
        result = apply_run(run2, self.fa.deps(detect=False))
        self.assertEqual(result.code, 0)
        effects = journal.effects(journal.read(run2 / "journal.jsonl"))
        # Only the `current` link moves to the new run; nothing else is made again.
        self.assertEqual([e["effect"]["path"] for e in effects], ["$Z0_HOME/onboard/current"])

    def test_P1_grok_never_ran_and_is_off_the_step_PATH(self):
        self.assertFalse((self.fa.root / "grok-was-executed").exists())
        self.assertNotIn("grok", self.fa.calls())
        ctx = self.result.ctx
        dirs = ctx.path_dirs()
        self.assertNotIn(str(self.fa.home / ".local" / "bin"), dirs)
        self.assertIn(str(self.fa.z0_home / "bin" / "links"), dirs)
        links = os.listdir(self.fa.z0_home / "bin" / "links")
        self.assertNotIn("grok", links)
        self.assertIn("claude", links)

    def test_X1_canary_appears_nowhere(self):
        self.assertFalse(self.receipt["secrets_scan"]["canary_found"])
        self.assertEqual(grep_tree(self.fa.z0_home, fakehost.CANARY.encode()), [])

    def test_never_read_or_touched_private_dirs(self):
        self.assertEqual(self.receipt["acceptance"]["z0evals"]["no_private_paths"], "passed")
        self.assertEqual((self.fa.home / ".hermes" / "config.yaml").read_text(), fakehost.CANARY)

    def test_report_opens_with_what_you_need_to_do(self):
        text = (self.run_dir / "report.md").read_text()
        order = [text.index(h) for h in ("## What you need to do", "## Installed", "## Unavailable",
                                         "## Harnesses", "## LLM decisions", "## Upstream gaps")]
        self.assertEqual(order, sorted(order))
        self.assertIn("toolchain.node", text)  # the ungranted C1 toolchain is an ask

    def test_C1_ungranted_toolchain_was_not_installed(self):
        self.assertEqual(self.result.results["toolchain.node"]["status"], "ask")
        self.assertFalse((self.fa.z0_home / "toolchains").exists())


@require_yaml
class Rollback(unittest.TestCase):
    """R1/R2: rollback restores a byte-equal tree outside runs/ and cache/; it deletes
    only owned artifacts whose hash is unchanged, and it is safe to run twice."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fa = FakeApply(Path(self.tmp.name), online=True)

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self):
        skip = (self.fa.z0_home / "onboard",)
        return tree_bytes(self.fa.home, skip=skip)

    def test_R2_rollback_restores_a_byte_equal_tree_and_is_idempotent(self):
        from z0.onboard.rollback import rollback_run
        (self.fa.z0_home / "onboard" / "runs").mkdir(parents=True)
        (self.fa.z0_home / "workspace.yaml").write_text("version: 1\nprofile: core\ncomponents: {}\n")
        before = self.snapshot()
        run, result, code, _ = self.fa.onboard(TOOLCHAINS)
        self.assertEqual(code, 0)
        self.assertEqual(result.results["z0evals.web.build"]["status"], "passed")
        self.assertNotEqual(self.snapshot(), before)
        counts = rollback_run(run, str(self.fa.z0_home), str(self.fa.home), out=lambda *_: None)
        self.assertNotIn("error", counts)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.fa.z0_home / "onboard" / "current").exists())
        again = rollback_run(run, str(self.fa.z0_home), str(self.fa.home), out=lambda *_: None)
        self.assertEqual(again, {})
        self.assertEqual(self.snapshot(), before)

    def test_R1_changed_files_and_foreign_dirs_are_kept(self):
        from z0.onboard.rollback import rollback_run
        run, _, code, _ = self.fa.onboard(TOOLCHAINS)
        self.assertEqual(code, 0)
        clone = self.fa.z0_home / "repos" / "z0evals"
        # red: the user edited a file the run wrote, inside the owned clone
        (clone / "web" / "data" / "optchat-long-horizon-v0.json").write_text('{"mine": 1}')
        # red: another run now owns the toolchain dir
        node = self.fa.z0_home / "toolchains" / "node" / "22.23.4"
        (node / ".z0-owned").write_text("someone-else\n")
        out = []
        counts = rollback_run(run, str(self.fa.z0_home), str(self.fa.home), out=out.append)
        self.assertGreaterEqual(counts.get("kept_changed", 0), 3)  # file, clone, toolchain
        self.assertEqual((clone / "web" / "data" / "optchat-long-horizon-v0.json").read_text(), '{"mine": 1}')
        self.assertTrue(node.is_dir())
        # what had an unchanged hash inside the kept clone is still removed
        self.assertFalse((clone / "site" / "index.html").exists())
        self.assertTrue(any("kept_changed" in line for line in out))

    def test_R1_replaced_file_restored_only_while_unchanged(self):
        from z0.onboard.rollback import rollback_run
        original = "version: 1\nroot: ~/elsewhere\ncomponents: {}\n"
        (self.fa.z0_home).mkdir(parents=True, exist_ok=True)
        (self.fa.z0_home / "workspace.yaml").write_text(original)
        run, _, _, _ = self.fa.onboard()
        self.assertNotEqual((self.fa.z0_home / "workspace.yaml").read_text(), original)
        backups = list((run / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(os.stat(backups[0]).st_mode & 0o777, 0o600)
        rollback_run(run, str(self.fa.z0_home), str(self.fa.home), out=lambda *_: None)
        self.assertEqual((self.fa.z0_home / "workspace.yaml").read_text(), original)

        run2, _, _, _ = self.fa.onboard()
        (self.fa.z0_home / "workspace.yaml").write_text("edited: true\n")  # red: changed since
        rollback_run(run2, str(self.fa.z0_home), str(self.fa.home), out=lambda *_: None)
        self.assertEqual((self.fa.z0_home / "workspace.yaml").read_text(), "edited: true\n")


@require_yaml
class AdoptedCheckout(unittest.TestCase):
    """A clean checkout of the pin is used in place; z0 never writes its .git, never
    moves it, and rollback never touches anything inside it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fa = FakeApply(Path(self.tmp.name), adopt=True)
        self.repo = self.fa.fake["repo"]

    def tearDown(self):
        self.tmp.cleanup()

    def git_state(self):
        from tests.onboard.fakeapply import git
        return (git("rev-parse", "HEAD", cwd=self.repo), git("status", "--porcelain", "--ignored", cwd=self.repo),
                tree_bytes(self.repo / ".git"))

    def test_used_in_place_and_never_touched_by_rollback(self):
        from z0.onboard.rollback import rollback_run
        head, _, git_before = self.git_state()
        run, result, code, receipt = self.fa.onboard()
        self.assertEqual(code, 0, json.dumps(receipt["steps"], indent=1))
        self.assertTrue(result.plan["components"]["z0evals"]["adopted"])
        self.assertEqual(result.results["z0evals.source"]["status"], "already_satisfied")
        self.assertTrue((self.repo / ".venv" / "bin" / "python").exists())
        self.assertFalse((self.fa.z0_home / "repos" / "z0evals").exists())
        self.assertEqual(self.git_state()[0], head)
        self.assertEqual(self.git_state()[2], git_before, ".git of the adopted checkout changed")
        after_apply = tree_bytes(self.repo)
        counts = rollback_run(run, str(self.fa.z0_home), str(self.fa.home), out=lambda *_: None)
        self.assertGreater(counts.get("kept_adopted", 0), 0)
        self.assertEqual(tree_bytes(self.repo), after_apply)


@require_yaml
class ConsentAtApply(unittest.TestCase):
    """C1/C2/L-LLM: the kernel decides again right before each step; a plan edited
    to run what it may not run is refused, whether or not its hash was redone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fa = FakeApply(Path(self.tmp.name))
        self.host = self.fa.detect()
        self.plan = self.fa.plan(self.host, self.fa.request())

    def tearDown(self):
        self.tmp.cleanup()

    def rehash(self, plan_obj):
        from z0.onboard.plan import plan_hash
        plan_obj["plan_hash"] = plan_hash(plan_obj)
        return plan_obj

    def entry(self, plan_obj, sid):
        return next(e for e in plan_obj["steps"] if e["step"]["id"] == sid)

    def test_edited_plan_without_a_new_hash_is_refused(self):
        from z0.onboard.apply import ApplyError, apply_run
        self.entry(self.plan, "toolchain.node")["state"] = {"status": "todo"}
        run = self.fa.write_run(self.host, self.plan)
        with self.assertRaises(ApplyError) as caught:
            apply_run(run, self.fa.deps(detect=False))
        self.assertEqual(caught.exception.code, 4)
        self.assertFalse((run / "journal.jsonl").exists())

    def test_C1_ungranted_step_marked_todo_is_refused(self):
        from z0.onboard.apply import apply_run
        self.entry(self.plan, "toolchain.node")["state"] = {"status": "todo"}
        run = self.fa.write_run(self.host, self.rehash(self.plan))
        result = apply_run(run, self.fa.deps(detect=False))
        self.assertEqual(result.results["toolchain.node"]["status"], "refused")
        self.assertIn("c1_ungranted", result.results["toolchain.node"]["reason"])
        self.assertFalse((self.fa.z0_home / "toolchains").exists())

    def test_C2_step_marked_todo_is_never_run_and_blocks_its_dependents(self):
        from z0.onboard.apply import apply_run
        entry = self.entry(self.plan, "z0evals.venv")
        entry["step"]["consent"] = {"class": "C2"}
        self.plan["grants"] = {"bundles": ["toolchains", "harness", "services", "models"], "source": "flag"}
        run = self.fa.write_run(self.host, self.rehash(self.plan))
        result = apply_run(run, self.fa.deps(detect=False))
        self.assertEqual(result.results["z0evals.venv"]["status"], "refused")
        self.assertIn("c2_never_auto", result.results["z0evals.venv"]["reason"])
        self.assertEqual(result.results["z0evals.deps"]["status"], "blocked")
        self.assertEqual(result.results["z0evals.t0.rollout"]["status"], "passed")  # independent
        self.assertFalse((self.fa.z0_home / "repos" / "z0evals" / ".venv").exists())

    def test_L_LLM_an_llm_sourced_grant_runs_nothing_C1(self):
        from z0.onboard.apply import apply_run
        self.plan["grants"] = {"bundles": ["toolchains"], "source": "llm"}
        self.entry(self.plan, "toolchain.node")["state"] = {"status": "todo"}
        run = self.fa.write_run(self.host, self.rehash(self.plan))
        result = apply_run(run, self.fa.deps(detect=False))
        self.assertEqual(result.results["toolchain.node"]["status"], "refused")

    def test_ask_steps_never_execute(self):
        from z0.onboard.apply import apply_run
        entry = self.entry(self.plan, "z0evals.ask.kit_skills")
        entry["state"] = {"status": "todo"}
        entry["step"]["argv"] = ["touch", str(self.fa.root / "ask-ran")]
        run = self.fa.write_run(self.host, self.rehash(self.plan))
        result = apply_run(run, self.fa.deps(detect=False))
        self.assertEqual(result.results["z0evals.ask.kit_skills"]["status"], "ask")
        self.assertFalse((self.fa.root / "ask-ran").exists())


@require_yaml
class FreshnessAndLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fa = FakeApply(Path(self.tmp.name), online=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lock_blocks_a_second_run(self):
        from z0.onboard import lock
        from z0.onboard.apply import apply_run
        host = self.fa.detect()
        plan_obj = self.fa.plan(host, self.fa.request())
        run = self.fa.write_run(host, plan_obj)
        with lock.hold(str(self.fa.z0_home)):
            with self.assertRaises(lock.LockHeld):
                apply_run(run, self.fa.deps(detect=False))
        self.assertFalse((run / "journal.jsonl").exists())

    def test_drift_within_grants_replans_and_shows_the_diff(self):
        from z0.onboard.apply import apply_run
        host = self.fa.detect()
        plan_obj = self.fa.plan(host, self.fa.request())
        run = self.fa.write_run(host, plan_obj)
        bun = self.fa.home / ".bun" / "bin" / "bun"
        bun.write_text("#!/bin/sh\necho 1.5.0\n")  # a volatile fact changed
        lines = []
        result = apply_run(run, self.fa.deps(out=lines.append))
        self.assertEqual(result.code, 0)
        self.assertTrue(any("host changed since the plan (toolchains)" in l for l in lines), lines)
        self.assertTrue((run / "plan.replan.json").is_file())
        events = [json.loads(l) for l in (run / "journal.jsonl").read_text().splitlines()]
        self.assertEqual([e["decision"] for e in events if e["event"] == "replan"], ["show_diff"])

    def _node_removed_after_plan(self):
        node_dir = self.fa.home / ".local" / "share" / "fnm" / "aliases" / "default" / "bin"
        node_dir.mkdir(parents=True)
        node = node_dir / "node"
        node.write_text("#!/bin/sh\necho v22.1.0\n")
        node.chmod(0o755)
        host = self.fa.detect()
        plan_obj = self.fa.plan(host, self.fa.request(TOOLCHAINS))
        self.assertEqual(next(e for e in plan_obj["steps"] if e["step"]["id"] == "toolchain.node")
                         ["state"]["status"], "already_satisfied")
        run = self.fa.write_run(host, plan_obj)
        shutil.rmtree(node_dir)
        return run

    def test_drift_that_widens_consent_stops_without_a_new_confirmation(self):
        from z0.onboard.apply import ApplyError, apply_run
        run = self._node_removed_after_plan()
        with self.assertRaises(ApplyError) as caught:
            apply_run(run, self.fa.deps(confirm=None), yes=True)  # --yes cannot widen
        self.assertEqual(caught.exception.code, 3)
        from z0.onboard import journal
        self.assertEqual(journal.effects(journal.read(run / "journal.jsonl")), [])

    def test_drift_that_widens_consent_proceeds_after_confirming_again(self):
        from z0.onboard.apply import apply_run
        run = self._node_removed_after_plan()
        seen = []
        result = apply_run(run, self.fa.deps(confirm=lambda lines: seen.extend(lines) or True))
        self.assertTrue(any("toolchain.node" in l for l in seen))
        self.assertEqual(result.results["toolchain.node"]["status"], "passed")

    def test_H1_plan_from_another_host_is_refused(self):
        from z0.onboard.apply import ApplyError, apply_run
        host = self.fa.detect()
        plan_obj = self.fa.plan(host, self.fa.request())
        run = self.fa.write_run(host, plan_obj)
        other = dict(host, host_id="f" * 16)
        deps = self.fa.deps()
        deps.detect = lambda: other
        with self.assertRaises(ApplyError) as caught:
            apply_run(run, deps)
        self.assertEqual(caught.exception.code, 4)


@require_yaml
class FailureBlocksOnlyDependents(unittest.TestCase):
    def test_failed_step_blocks_dependents_and_exits_1(self):
        from z0.onboard.apply import apply_run
        from z0.onboard.verify import verify_run
        with tempfile.TemporaryDirectory() as tmp:
            fa = FakeApply(Path(tmp))
            for step in fa.snap["components"]["components"]["z0evals"]["onboard"]["steps"]:
                if step["id"] == "z0evals.t1.build_site":
                    step["argv"] = [".venv/bin/python", "-c", "raise SystemExit(5)"]
            host = fa.detect()
            plan_obj = fa.plan(host, fa.request())
            run = fa.write_run(host, plan_obj)
            deps = fa.deps(detect=False)
            result = apply_run(run, deps)
            self.assertEqual(result.code, 1)
            self.assertEqual(result.results["z0evals.t1.build_site"]["status"], "failed")
            self.assertEqual(result.results["z0evals.t1.build_site"]["remediation"], "mark_unavailable")
            self.assertEqual(result.results["z0evals.t1.site_data"]["status"], "blocked")
            self.assertEqual(result.results["z0evals.t1.posts_tests"]["status"], "blocked")
            self.assertEqual(result.results["z0evals.t1.validate"]["status"], "passed")
            code, receipt = verify_run(run, deps, prior=result.results, host=result.host,
                                       apply_code=result.code)
            self.assertEqual(code, 1)
            self.assertEqual(receipt["acceptance"]["z0evals"]["tier1"], "failed")
            self.assertIn("z0evals.t1.build_site", (run / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
