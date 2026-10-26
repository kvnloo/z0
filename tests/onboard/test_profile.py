"""Contributor profile detector (contributor spec §3.2, §3.7) and privacy cells G1-G5 (§4.3).

Each test runs detect/profile.py against a fake HOME (tests/onboard/profilehome.py)
whose private files hold canaries. An audit hook records every file the process
opens and every directory it lists, and every probe runs in the fake host.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

from tests.onboard import profilehome, support
from tests.onboard.support import require_yaml

_AUDIT = {"on": False, "opens": [], "lists": [], "execs": []}


def _hook(event, args):
    if not _AUDIT["on"] or not args:
        return
    if event == "open" and isinstance(args[0], (str, bytes)):
        _AUDIT["opens"].append(os.fsdecode(args[0]))
    elif event in ("os.scandir", "os.listdir") and isinstance(args[0], (str, bytes)):
        _AUDIT["lists"].append(os.fsdecode(args[0]))
    elif event == "subprocess.Popen":
        _AUDIT["execs"].append(os.fsdecode(args[0]))


sys.addaudithook(_hook)

T1 = ["t1.git_identity", "t1.harness_keys"]
T2 = ["t2.github_languages", "t2.local_languages"]
T3 = ["t3.instruction_text", "t3.repo_names", "t3.starred_languages", "t3.topics"]
HOST = {"os": {"os": "linux", "arch": "x86_64"},
        "hardware": {"ram_gib": 31.2, "gpu": {"class": "nvidia", "vram_gib": 12.0}},
        "harnesses": {"claude-code": {"state": "installed"}, "codex": {"state": "installed"},
                      "grok": {"state": "absent"}}}


@require_yaml
class Profile(unittest.TestCase):
    def setUp(self):
        from z0.onboard.detect import Ctx, profile
        self.Ctx, self.p = Ctx, profile
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = profilehome.build(Path(self.tmp.name))
        self.registry = support.snapshot()

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, fake=None, **kw):
        fake = fake or self.fake
        args = dict(registry=self.registry, env=dict(fake["env"]), sysroot=str(fake["sysroot"]),
                    system_dirs=[str(fake["sysroot"] / "usr/bin")], uname=("Linux", "x86_64"),
                    hostname="fakehost", now="2026-10-26T00:00:00Z",
                    http_head=lambda url, timeout: False)
        args.update(kw)
        return self.Ctx(**args)

    def consent(self, *items, source="tty"):
        return self.p.Consent(frozenset(items), source)

    def run_profile(self, consent=None, fake=None, host=HOST, **kw):
        """detect + write under audit; returns (profile, file text)."""
        fake = fake or self.fake
        for key in ("opens", "lists", "execs"):
            _AUDIT[key].clear()
        before = profilehome.tree_state(fake["home"] / "workspace")
        _AUDIT["on"] = True
        try:
            prof = self.p.run(self.ctx(fake, **kw.pop("ctx_kw", {})), consent, host, **kw)
        finally:
            _AUDIT["on"] = False
        self.assertEqual(before, profilehome.tree_state(fake["home"] / "workspace"),
                         "profile changed files under HOME")
        out = Path(fake["home"]) / ".z0int/contribute/profile.json"
        text = out.read_text()
        self.assertEqual(json.loads(text), prof)
        self.assert_schema(prof)
        return prof, text

    def assert_schema(self, prof):
        if support.jsonschema is None:
            return
        import jsonschema
        schema = json.loads((support.ROOT / "schemas/profile.schema.json").read_text())
        errors = [e.message for e in jsonschema.Draft202012Validator(schema).iter_errors(prof)]
        self.assertEqual(errors, [])

    def opened(self, relative):
        target = str(self.fake["home"] / relative)
        return [p for p in _AUDIT["opens"] if p == target or p.startswith(target + "/")]

    def listed(self, relative):
        target = str(self.fake["home"] / relative)
        return [p for p in _AUDIT["lists"] if p == target or p.startswith(target + "/")]

    # --- T0 ---------------------------------------------------------------------------
    def test_t0_facts_only(self):
        prof, text = self.run_profile(self.consent(source="flag"))
        self.assertEqual(prof["tier"], "T0")
        self.assertEqual(prof["hw"], {"os": "linux", "arch": "x86_64", "ram_gib": 31.2,
                                      "gpu": {"class": "nvidia", "vram_gib": 12.0}})
        self.assertEqual(prof["toolchains"], ["cargo", "node", "python"])
        self.assertEqual(prof["harnesses"], ["claude", "codex"])
        claude = prof["instruction_files"]["claude"]
        self.assertEqual((claude["exists"], claude["size"]), (True, len(
            (self.fake["home"] / ".claude/CLAUDE.md").read_text())))
        self.assertEqual(prof["instruction_files"]["gemini"], {"exists": False})
        for key in ("harness_config", "git_identity", "languages", "recency", "t3"):
            self.assertNotIn(key, prof)
        # T0 executes nothing and opens no signal file: stat only.
        self.assertEqual(profilehome.executed(self.fake), [])
        self.assertEqual(_AUDIT["execs"], [])
        self.assertEqual(self.opened(".claude"), [])
        self.assertEqual(self.opened(".codex"), [])
        self.assertEqual(self.opened(".gitconfig"), [])
        self.assertEqual(profilehome.gh_calls(self.fake), [])
        self.assert_no_canary(text)

    def test_hardware_probe_without_host_json(self):
        meminfo = self.fake["sysroot"] / "proc/meminfo"
        meminfo.parent.mkdir(parents=True)
        meminfo.write_text("MemTotal:       16314660 kB\n")
        prof, _ = self.run_profile(self.consent(), host=None)
        self.assertEqual(prof["hw"]["os"], "linux")
        self.assertEqual(prof["hw"]["gpu"], {"class": "cpu"})
        self.assertGreater(prof["hw"]["ram_gib"], 15)
        self.assertEqual(profilehome.executed(self.fake), [])

    # --- T1 ---------------------------------------------------------------------------
    def test_t1_key_names_and_identity_booleans(self):
        prof, text = self.run_profile(self.consent(*T1))
        self.assertEqual(prof["tier"], "T1")
        self.assertEqual(prof["harness_config"]["claude"],
                         {"keys": ["env", "mcpServers", "model", "permissions"], "mcp_servers": ["z0"]})
        self.assertEqual(prof["harness_config"]["codex"],
                         {"keys": ["approval_policy", "mcp_servers", "model", "notes", "profiles"],
                          "mcp_servers": ["other", "z0int"]})
        self.assertEqual(prof["git_identity"], {"name": True, "email": True})
        self.assertNotIn("languages", prof)
        self.assert_no_canary(text)

    # --- T2 / T3 ------------------------------------------------------------------------
    def test_t2_languages_and_recency(self):
        prof, text = self.run_profile(self.consent(*T1, *T2))
        self.assertEqual(prof["tier"], "T2")
        self.assertEqual(prof["language_sources"], ["local_repos", "github"])
        # local: ts 3, js 2, python 3, rust 2 (dot dirs and node_modules skipped);
        # github: typescript 1, python 1 (a repo with no language is not counted).
        self.assertEqual(prof["languages"], {"javascript": 0.1, "python": 0.4, "rust": 0.1,
                                             "typescript": 0.4})
        self.assertEqual(prof["recency"], "active_30d")
        self.assertEqual(prof["experience"], {"contrib_done": 0, "repos_bucket": "1-4"})
        self.assertNotIn("t3", prof)
        self.assertEqual(self.listed("workspace/.hidden"), [])
        self.assertEqual(self.listed("workspace/web-app/node_modules"), [])
        self.assertEqual(self.opened("workspace"), [], "a repo file was opened")
        self.assert_no_canary(text)

    def test_t3_items_with_full_consent(self):
        prof, text = self.run_profile(self.consent(*T1, *T2, *T3), interests=["latency", "Bad Tag"])
        self.assertEqual(prof["tier"], "T3")
        t3 = prof["t3"]
        self.assertEqual(t3["repo_names"], ["ml-thing", "tiny", "web-app"])
        self.assertEqual(t3["topics"], ["benchmark", "machine-learning", "react"])
        self.assertEqual(t3["starred_languages"], {"go": 0.33, "rust": 0.67})
        self.assertIn(profilehome.CANARIES["instruction"], t3["instruction_text"]["claude"])
        self.assertEqual(prof["interests"], ["benchmarking", "frontend", "latency", "ml"])
        public = json.dumps(self.p.public_view(prof))
        self.assertNotIn(profilehome.CANARIES["instruction"], public)
        self.assertNotIn("web-app", public)
        self.assert_no_canary(text, allowed=("instruction",))

    # --- G1: consent denied for each tier gives no data from that tier ------------------
    def test_G1_denied_tiers_give_no_data(self):
        cases = {
            "T0 only": ((), {"harness_config", "git_identity", "languages", "recency", "t3"}),
            "T1, no T2/T3": (T1, {"languages", "language_sources", "recency", "t3"}),
            "T1+T2, no T3": (T1 + T2, {"t3"}),
        }
        for label, (items, absent) in cases.items():
            with self.subTest(case=label):
                log = self.fake["root"] / "gh.log"
                if log.exists():
                    log.unlink()
                prof, text = self.run_profile(self.consent(*items))
                for key in absent:
                    self.assertNotIn(key, prof)
                if "t2.github_languages" not in items:
                    self.assertNotIn("repos_bucket", prof["experience"])
                calls = profilehome.gh_calls(self.fake)
                if not any(i.startswith("t2.github") for i in items):
                    self.assertEqual(calls, [], "gh ran without GitHub consent")
                    self.assertEqual(self.listed("workspace"), [], "repos walked without T2")
                else:
                    self.assertFalse([c for c in calls if "topics" in c or ".name" in c
                                      or "starred" in c], "a T3 call ran without T3 consent")
                if "t1.harness_keys" not in items:
                    self.assertEqual(self.opened(".claude/settings.json"), [])
                    self.assertEqual(self.opened(".codex/config.toml"), [])
                if "t1.git_identity" not in items:
                    self.assertEqual(self.opened(".gitconfig"), [])
                self.assertEqual(self.opened(".claude/CLAUDE.md"), [])
                self.assertEqual(self.opened(".codex/AGENTS.md"), [])
                self.assert_no_canary(text)

    def test_G1_each_t3_item_alone(self):
        keys = {"t3.repo_names": "repo_names", "t3.topics": "topics",
                "t3.starred_languages": "starred_languages", "t3.instruction_text": "instruction_text"}
        for item, key in keys.items():
            with self.subTest(item=item):
                prof, _ = self.run_profile(self.consent(*T1, item))
                self.assertEqual(set(prof["t3"]), {key})
                self.assertNotIn("languages", prof)
                self.assertEqual(prof["tier"], "T3")

    # --- G2: gh logged out -----------------------------------------------------------------
    def test_G2_gh_logged_out(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = profilehome.build(Path(folder), logged_in=False)
            prof, text = self.run_profile(self.consent(*T1, *T2, *T3), fake=fake)
            calls = profilehome.gh_calls(fake)
            self.assertEqual(calls, ["auth status --hostname github.com"])
            self.assertEqual(prof["language_sources"], ["local_repos"])
            self.assertNotIn("recency", prof)
            self.assertNotIn("repos_bucket", prof["experience"])
            self.assertEqual(set(prof["t3"]), {"instruction_text"})
            self.assertIn("profile: gh not logged in; GitHub signals skipped", prof["warnings"])
            self.assertFalse(any(c.startswith("WRITE") for c in calls))

    def test_G2_gh_not_installed(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = profilehome.build(Path(folder), with_gh=False)
            prof, _ = self.run_profile(self.consent(*T1, *T2), fake=fake)
            self.assertEqual(prof["language_sources"], ["local_repos"])
            self.assertIn("profile: gh not installed; GitHub signals skipped", prof["warnings"])

    def test_gh_is_read_only(self):
        self.run_profile(self.consent(*T1, *T2, *T3))
        calls = profilehome.gh_calls(self.fake)
        self.assertTrue(calls)
        for call in calls:
            self.assertTrue(call.startswith("auth status") or call.startswith("api "), call)
            self.assertNotIn("WRITE", call)

    # --- G3: --profile=none ------------------------------------------------------------------
    def test_G3_profile_none(self):
        consent = self.p.consent_for("none", {item: True for item in T2 + T3})
        self.assertEqual((consent.granted, consent.tier), (frozenset(), "T0"))
        prof, text = self.run_profile(consent)
        self.assertEqual(prof["tier"], "T0")
        self.assertEqual(prof["consent"], {"granted": [], "source": "flag"})
        self.assertEqual(profilehome.gh_calls(self.fake), [])
        self.assertEqual(self.listed("workspace"), [])
        self.assert_no_canary(text)

    def test_G3_consent_ux(self):
        p = self.p
        self.assertEqual(p.consent_for(None, None).granted, frozenset(T1))  # no TTY: T0+T1
        self.assertEqual(p.consent_for(None, None).source, "default")
        self.assertEqual(p.consent_for("minimal", {i: True for i in T2}).granted, frozenset(T1))
        self.assertEqual(p.consent_for("full", None).granted, frozenset(T1),
                         "--profile=full without a TTY never grants T2/T3")
        answers = {"t2.local_languages": True, "t3.topics": "y", "t3.repo_names": 1,
                   "t2.github_languages": False, "made.up": True, "t1.harness_keys": False}
        granted = p.consent_for("full", answers)
        self.assertEqual(granted.granted, frozenset(T1 + ["t2.local_languages"]))
        self.assertEqual(granted.tier, "T2")
        with self.assertRaises(ValueError):
            p.Consent(frozenset(T1), "llm")  # L-LLM: an LLM is never a consent source
        with self.assertRaises(ValueError):
            p.Consent(frozenset({"t9.everything"}))
        with self.assertRaises(ValueError):
            p.consent_for("everything")
        self.assertEqual({i for i, _ in p.consent_lines()}, set(T2 + T3))

    # --- G4: never-touch paths are not opened -------------------------------------------------
    def test_G4_never_touch_paths_not_opened(self):
        prof, text = self.run_profile(self.consent(*T1, *T2, *T3))
        home = str(self.fake["home"])
        for relative in profilehome.NEVER_TOUCH:
            with self.subTest(path=relative):
                self.assertEqual(self.opened(relative), [])
        for directory in (".claude/projects", ".claude/file-history", ".claude/paste-cache",
                          ".codex/attachments", ".codex/dictation-history", ".codex/mcp-oauth-locks",
                          ".ssh", ".config/gh"):
            self.assertEqual(self.listed(directory), [], directory)
            self.assertEqual(self.opened(directory), [], directory)
        allowed = {f"{home}/.claude/settings.json", f"{home}/.claude/CLAUDE.md",
                   f"{home}/.codex/config.toml", f"{home}/.codex/AGENTS.md", f"{home}/.gitconfig"}
        under_home = {p for p in _AUDIT["opens"] if p.startswith(home + "/")}
        under_home = {p for p in under_home if "/.z0int/contribute/" not in p}  # its own output
        self.assertEqual(under_home - allowed, set(), "opened a file outside the listed signals")
        self.assert_no_canary(text, allowed=("instruction",))

    def test_G4_never_touch_even_when_pointed_at(self):
        """A config-dir override that points into a never-touch path is not followed."""
        projects = self.fake["home"] / ".claude/projects"
        (projects / "settings.json").write_text(json.dumps({profilehome.CANARIES["transcript"]: 1}))
        (projects / "CLAUDE.md").write_text(profilehome.CANARIES["transcript"])
        env = dict(self.fake["env"], CLAUDE_CONFIG_DIR=str(projects))
        prof, text = self.run_profile(self.consent(*T1, *T3), ctx_kw={"env": env})
        self.assertEqual(self.listed(".claude/projects"), [])
        self.assertEqual(self.opened(".claude/projects"), [])
        self.assertNotIn("claude", prof.get("harness_config", {}))
        self.assertEqual(prof["instruction_files"]["claude"], {"exists": False})
        self.assertNotIn(profilehome.CANARIES["transcript"], text)

    # --- G5: the [mcp_servers.*.env] canary is not read -----------------------------------------
    def test_G5_mcp_env_values_never_kept(self):
        prof, text = self.run_profile(self.consent(*T1, *T2, *T3))
        for canary in ("mcp_env", "mcp_env_key", "settings_mcp_env", "settings_env",
                       "codex_value", "codex_multiline"):
            self.assertNotIn(profilehome.CANARIES[canary], text, canary)
        keys, servers = self.p.toml_names(profilehome.CODEX_CONFIG)
        self.assertEqual(servers, ["other", "z0int"])
        self.assertNotIn(profilehome.CANARIES["codex_multiline"], keys,
                         "a table header inside a multi-line string was parsed")
        self.assertNotIn(profilehome.CANARIES["mcp_env_key"], keys + servers)

    def test_G5_scanners_return_names_only(self):
        hostile = ('token = "Z0CANARY-a"\nmcp_servers.dotted.env.K = "Z0CANARY-c"\n'
                   '[mcp_servers."we ird".env]\nX = "Z0CANARY-b"\n'
                   '[a]\nb = """Z0CANARY-d\n[x]\n"""\n')
        keys, servers = self.p.toml_names(hostile)
        self.assertEqual(keys, ["a", "mcp_servers", "token"])
        self.assertEqual(servers, ["dotted"])
        self.assertNotIn("Z0CANARY", json.dumps([keys, servers]))
        self.assertEqual(self.p.json_names('{"a": "Z0CANARY", "mcpServers": {"s": {"env": 1}}}'),
                         (["a", "mcpServers"], ["s"]))
        self.assertEqual(self.p.json_names("[1, 2]"), ([], []))
        self.assertEqual(self.p.git_identity_names('[user "x"]\nname = Z0CANARY\n[core]\nemail = y\n'),
                         {"name"})

    # --- §3.7 and the detector contract -------------------------------------------------------
    def test_written_0600_without_home_paths(self):
        prof, text = self.run_profile(self.consent(*T1, *T2, *T3))
        out = self.fake["home"] / ".z0int/contribute/profile.json"
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(out.parent.stat().st_mode), 0o700)
        self.assertNotIn(str(self.fake["home"]), text)
        self.assertNotIn(str(self.fake["root"]), text)
        self.assertEqual(profilehome.executed(self.fake), [], "a toolchain binary was executed")
        self.assertEqual([e for e in _AUDIT["execs"] if not e.endswith("/gh")], [])

    def test_never_raises_and_always_writes(self):
        def boom(*args, **kwargs):
            raise RuntimeError("probe exploded")

        prof, _ = self.run_profile(self.consent(*T1, *T2, *T3), ctx_kw={"runner": boom})
        self.assertIn("profile: gh not logged in; GitHub signals skipped", prof["warnings"])
        original = self.p._toolchains
        self.p._toolchains = lambda ctx: (_ for _ in ()).throw(ValueError("x"))
        try:
            prof, _ = self.run_profile(self.consent())
        finally:
            self.p._toolchains = original
        self.assertEqual(prof["toolchains"], [])
        self.assertIn("profile: toolchains failed: ValueError", prof["warnings"])
        original = self.p.detect
        self.p.detect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
        try:
            prof, _ = self.run_profile(self.consent())
        finally:
            self.p.detect = original
        self.assertEqual(prof["warnings"], ["profile: detection failed; T0 fallback"])

    def test_HT_test_hardware_only_in_test_mode_under_the_test_root(self):
        fixture = self.fake["root"] / "hw.json"
        fixture.write_text(json.dumps({"os": "linux", "arch": "x86_64", "ram_gib": 64,
                                       "gpu": {"class": "amd", "vram_gib": 24}}))
        env = dict(self.fake["env"], Z0_TEST_HW=str(fixture), Z0_TEST_MODE="1")
        prof, _ = self.run_profile(self.consent(), ctx_kw={"env": env})
        self.assertEqual(prof["hw"]["gpu"]["class"], "nvidia", "production path honoured Z0_TEST_HW")
        prof, _ = self.run_profile(self.consent(), ctx_kw={"env": env},
                                   test_hw_root=str(self.fake["root"]))
        self.assertEqual(prof["hw"]["gpu"], {"class": "amd", "vram_gib": 24.0})
        env["Z0_TEST_MODE"] = "0"
        prof, _ = self.run_profile(self.consent(), ctx_kw={"env": env},
                                   test_hw_root=str(self.fake["root"]))
        self.assertEqual(prof["hw"]["gpu"]["class"], "nvidia")
        with tempfile.TemporaryDirectory() as other:
            prof, _ = self.run_profile(self.consent(), ctx_kw={"env": dict(env, Z0_TEST_MODE="1")},
                                       test_hw_root=other)
            self.assertEqual(prof["hw"]["gpu"]["class"], "nvidia", "fixture outside the test root")

    def assert_no_canary(self, text, allowed=()):
        for key, canary in profilehome.CANARIES.items():
            if key not in allowed:
                self.assertNotIn(canary, text, key)


class ProfileSchema(unittest.TestCase):
    def test_tier_gating_in_the_schema(self):
        if support.jsonschema is None:
            self.skipTest("jsonschema not installed (optional)")
        import jsonschema
        schema = json.loads((support.ROOT / "schemas/profile.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        base = {"schema": "z0.contribute.profile.v1", "tier": "T0",
                "detected_at": "2026-10-26T00:00:00Z", "consent": {"granted": [], "source": "flag"},
                "hw": {"os": "linux", "arch": "x86_64", "ram_gib": 8, "gpu": {"class": "cpu"}},
                "toolchains": [], "harnesses": [], "instruction_files": {}, "interests": [],
                "experience": {"contrib_done": 0}, "warnings": []}
        valid = jsonschema.Draft202012Validator(schema)
        self.assertEqual(list(valid.iter_errors(base)), [])
        red = {
            "T1 data at T0": dict(base, git_identity={"name": True, "email": True}),
            "T2 data at T1": dict(base, tier="T1", languages={"python": 1.0}),
            "T3 data at T2": dict(base, tier="T2", t3={"repo_names": ["x"]}),
            "a value instead of a name": dict(base, tier="T1", harness_config={
                "codex": {"keys": ["model = secret value"], "mcp_servers": []}}),
            "an unknown field": dict(base, email="someone@example.com"),
            "an LLM consent source": dict(base, consent={"granted": [], "source": "llm"}),
            "content at T0": dict(base, instruction_files={"claude": {"exists": True, "text": "x"}}),
        }
        for label, instance in red.items():
            with self.subTest(red=label):
                self.assertTrue(list(valid.iter_errors(instance)), label)


if __name__ == "__main__":
    unittest.main()
