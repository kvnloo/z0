"""Plan-level laws over the golden fixtures and seeded random variants (§10, §11).

O1 order, I1 idempotence, C1/C2 consent, L-LLM grant source, P1 forbidden harness,
M1/M2, H1 host match, D1/D2 dash gates, S1/S2 services, Z2 torch index, T1 prepared
PATH in the plan, plus one red case per law (a violating plan or input must fail).
"""
from __future__ import annotations

import json
from pathlib import Path
import random
import unittest

from tests.onboard import support
from tests.onboard.support import ALL_BUNDLES, GOLDEN_CASES, require_yaml

TTY_ALL = dict(ALL_BUNDLES, source="tty")

SEED = 20261025
MUTANTS = 60


def _edges(plan_obj: dict, snap: dict) -> list:
    """Declared + implicit edges the plan must respect: needs, tool needs, depends_on."""
    from z0.onboard import regsnap
    comps = regsnap.components(snap)
    ids = [e["step"]["id"] for e in plan_obj["steps"]]
    by_comp: dict = {}
    for entry in plan_obj["steps"]:
        by_comp.setdefault(entry["step"]["component"], []).append(entry["step"]["id"])
    edges = []
    for entry in plan_obj["steps"]:
        step = entry["step"]
        for need in step.get("needs") or []:
            if need in ids:
                edges.append((need, step["id"]))
        comp = comps.get(step["component"]) or {}
        for req in ((comp.get("onboard") or {}).get("requires") or {}).get("tools") or []:
            tool = str(req).split(">=")[0]
            tool = {"python": "python3", "npm": "node"}.get(tool, tool)
            if f"toolchain.{tool}" in ids:
                edges.append((f"toolchain.{tool}", step["id"]))
        for dep in comp.get("depends_on") or []:
            for before in by_comp.get(dep, []):
                edges.append((before, step["id"]))
    return edges


def mutate(host: dict, rng: random.Random) -> dict:
    """A random but schema-shaped variant of a fixture."""
    host = json.loads(json.dumps(host))
    host["hardware"]["ram_gib"] = rng.choice([2.0, 3.9, 6.0, 8.0, 15.5, 31.0, 64.0])
    host["hardware"]["disks"][0]["free_gib"] = rng.choice([1.0, 4.0, 9.0, 20.0, 120.0])
    host["hardware"]["gpu"] = rng.choice([{"class": "cpu"}, {"class": "amd", "rocm": True},
                                          {"class": "nvidia", "cuda_max": "12.4"},
                                          {"class": "nvidia", "cuda_max": "12.8"},
                                          {"class": "apple"}, {"class": "intel_mac"}])
    host["python_window"] = rng.choice(["present", "makeable", "impossible"])
    for name in host.get("network") or {}:
        host["network"][name] = rng.random() < 0.7
    for tool in list(host.get("toolchains") or {}):
        if rng.random() < 0.3:
            host["toolchains"][tool] = {"state": "absent"}
    if rng.random() < 0.5:
        host["tailscale"] = {"installed": True, "logged_in": True, "ipv4": "100.64.0.9"}
    else:
        host["tailscale"] = {"installed": False, "logged_in": False}
    for sha, fact in (host.get("revs") or {}).items():
        fact["on_origin"] = rng.choice(["yes", "yes", "unknown", "no"])
        if fact["repo"] == "kvnloo/dash":
            fact["flavour"] = rng.choice(["current", "current", "legacy", "unknown"])
    host["workspace"]["host_match"] = rng.choice(["fresh", "same", "same", "fresh", "other"])
    for hid, entry in host.get("harnesses", {}).items():
        if rng.random() < 0.3:
            entry["state"] = rng.choice(["installed", "absent", "config_only"])
    return host


@require_yaml
class PlanLaws(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from z0.onboard import kernel, plan as plan_mod
        cls.k, cls.p = kernel, plan_mod
        cls.snap = support.snapshot()
        rng = random.Random(SEED)
        cls.cases = []
        for stem, fixture, kwargs in GOLDEN_CASES:
            cls.cases.append((stem, support.fixture(fixture), kwargs))
        bases = [support.fixture(n) for n in support.fixture_names()]
        modes = [{}, {"grants": ALL_BUNDLES}, {"mode": "guided", "profile": "core"},
                 {"grants": {"bundles": ["toolchains"], "source": "flag"}},
                 {"with_ids": ["memento", "flow", "evolution-lab"]}]
        for index in range(MUTANTS):
            cls.cases.append((f"mutant-{index}", mutate(rng.choice(bases), rng), rng.choice(modes)))

    def plans(self):
        for name, host, kwargs in self.cases:
            yield name, host, kwargs, self.p.plan(host, self.snap, **kwargs)

    # --- O1 ----------------------------------------------------------------------
    def test_O1_topological_order(self):
        for name, _, _, plan_obj in self.plans():
            position = {e["step"]["id"]: i for i, e in enumerate(plan_obj["steps"])}
            for before, after in _edges(plan_obj, self.snap):
                with self.subTest(case=name, edge=(before, after)):
                    self.assertLess(position[before], position[after])

    def test_O1_red_detects_a_reordered_plan(self):
        plan_obj = self.p.plan(support.fixture("laptop-cpu-15g"), self.snap)
        steps = plan_obj["steps"]
        swapped = dict(plan_obj, steps=[steps[-1], *steps[1:-1], steps[0]])
        position = {e["step"]["id"]: i for i, e in enumerate(swapped["steps"])}
        broken = [e for e in _edges(swapped, self.snap) if position[e[0]] >= position[e[1]]]
        self.assertTrue(broken, "a reordered plan must violate O1")

    # --- I1 ----------------------------------------------------------------------
    def test_I1_second_plan_has_no_todo(self):
        for name, host, kwargs, plan_obj in self.plans():
            with self.subTest(case=name):
                after = support.simulate_apply(host, plan_obj)
                again = self.p.plan(after, self.snap, **kwargs)
                self.assertEqual(self.p.todo_ids(again), [])

    def test_I1_red_without_effects_todo_remains(self):
        host = support.fixture("tiny-4g-vps")
        plan_obj = self.p.plan(host, self.snap, grants=ALL_BUNDLES)
        self.assertTrue(self.p.todo_ids(plan_obj), "the I1 check above must not be vacuous")
        self.assertTrue(self.p.todo_ids(self.p.plan(host, self.snap, grants=ALL_BUNDLES)))

    # --- consent -------------------------------------------------------------------
    def test_C1_C2_consent_bounds(self):
        for name, _, kwargs, plan_obj in self.plans():
            granted = set(plan_obj["grants"]["bundles"])
            for entry in plan_obj["steps"]:
                step, status = entry["step"], entry["state"]["status"]
                if status != "todo":
                    continue
                with self.subTest(case=name, step=step["id"]):
                    consent = step["consent"]
                    self.assertNotEqual(consent["class"], "C2", "C2 is never todo")
                    if consent["class"] == "C1":
                        self.assertIn(consent.get("bundle"), granted, "ungranted C1 executed")

    def test_C2_shadow_and_manual_asks_never_todo_even_with_yes(self):
        plan_obj = self.p.plan(support.fixture("laptop-cpu-15g"), self.snap, grants=ALL_BUNDLES,
                               with_ids=["flow", "evolution-lab"])
        for entry in plan_obj["steps"]:
            if entry["step"]["component"] in ("flow", "evolution-lab") or entry["step"]["kind"] == "ask":
                self.assertIn(entry["state"]["status"], ("ask", "unavailable", "blocked"),
                              entry["step"]["id"])

    def test_L_LLM_grant_source_never_llm(self):
        for _, _, _, plan_obj in self.plans():
            self.assertIn(plan_obj["grants"]["source"], ("tty", "flag", "none"))

    # --- P1 ------------------------------------------------------------------------
    def test_P1_no_step_targets_grok_or_cursor(self):
        for name, _, _, plan_obj in self.plans():
            for entry in plan_obj["steps"]:
                text = json.dumps(entry["step"])
                with self.subTest(case=name, step=entry["step"]["id"]):
                    self.assertNotIn('"harness": "grok"', text)
                    self.assertNotIn('"harness": "cursor-agent"', text)

    def test_P1_red_grok_step_is_refused(self):
        snap = support.snapshot()
        comp = snap["components"]["components"]["z0intelligence"]
        comp["onboard"]["steps"].append({
            "id": "z0intelligence.plugin.grok", "kind": "harness_plugin", "harness": "grok",
            "consent": {"class": "C1", "bundle": "harness"}, "where": "release",
            "probe": {"exists": "$Z0_HOME/onboard/stamps/grok"}})
        plan_obj = self.p.plan(support.fixture("desktop-nvidia-32g"), snap, grants=ALL_BUNDLES)
        state = {e["step"]["id"]: e["state"] for e in plan_obj["steps"]}["z0intelligence.plugin.grok"]
        self.assertEqual(state, {"status": "refused", "reason": "forbidden_provider"})

    # --- M1 / M2 -------------------------------------------------------------------
    def test_M1_memento_never_planned(self):
        for name, _, _, plan_obj in self.plans():
            self.assertFalse([e for e in plan_obj["steps"] if e["step"]["component"] == "memento"
                              and e["state"]["status"] == "todo"], name)

    def test_M2_shadow_is_an_ask(self):
        plan_obj = self.p.plan(support.fixture("desktop-nvidia-32g"), self.snap,
                               with_ids=["evolution-lab"], grants=ALL_BUNDLES)
        summary = plan_obj["components"]["evolution-lab"]
        self.assertEqual((summary["verdict"], summary["reason"]), ("ask", "shadow"))
        self.assertIn("evolution-lab", [a["id"] for a in plan_obj["asks"]])

    # --- H1 ------------------------------------------------------------------------
    def test_H1_other_host_refuses_everything(self):
        plan_obj = self.p.plan(support.fixture("host-mismatch"), self.snap, grants=ALL_BUNDLES)
        self.assertTrue(plan_obj["steps"])
        self.assertEqual({e["state"]["status"] for e in plan_obj["steps"]}, {"refused"})
        self.assertEqual(self.p.exit_code(plan_obj), 4)

    def test_H1_red_same_host_is_not_refused(self):
        host = support.fixture("host-mismatch")
        host["workspace"]["host_match"] = "same"
        self.assertEqual(self.p.exit_code(self.p.plan(host, self.snap)), 0)

    # --- D1 / D2 -------------------------------------------------------------------
    def test_D1_dash_rev_not_on_origin_is_unavailable_and_rest_continues(self):
        host = support.fixture("laptop-cpu-15g")
        for fact in host["revs"].values():
            if fact["repo"] == "kvnloo/dash":
                fact.update(on_origin="no", evidence="mirror")
        plan_obj = self.p.plan(host, self.snap)
        self.assertEqual(plan_obj["components"]["dash"]["reason"], "rev_not_on_origin")
        dash = [e for e in plan_obj["steps"] if e["step"]["component"] == "dash"]
        self.assertEqual({e["state"]["status"] for e in dash}, {"unavailable"})
        self.assertTrue([e for e in plan_obj["steps"] if e["step"]["component"] == "z0evals"
                         and e["state"]["status"] in ("todo", "already_satisfied")])
        entry = next(u for u in plan_obj["unavailable"] if u["id"] == "dash")
        self.assertIn("maintainer must push", entry["detail"])

    def test_D1_unchecked_dash_rev_is_unverified_not_unpushed(self):
        """No mirror and no checkout: say so, never claim the maintainer must push."""
        for fixture in ("laptop-cpu-15g", "fresh-stranger"):
            plan_obj = self.p.plan(support.fixture(fixture), self.snap)
            self.assertEqual(plan_obj["components"]["dash"]["reason"], "rev_unverified", fixture)
            entry = next(u for u in plan_obj["unavailable"] if u["id"] == "dash")
            self.assertIn("re-run `./z0 onboard plan` with network", entry["detail"])
            text = json.dumps(plan_obj)
            self.assertNotIn("maintainer must push", text, fixture)

    def test_D2_legacy_dash_is_refused(self):
        host = support.fixture("desktop-nvidia-32g")
        for fact in host["revs"].values():
            if fact["repo"] == "kvnloo/dash":
                fact["flavour"] = "legacy"
        plan_obj = self.p.plan(host, self.snap, grants=ALL_BUNDLES)
        self.assertEqual(plan_obj["components"]["dash"]["verdict"], "refuse")
        self.assertEqual(plan_obj["components"]["dash"]["reason"], "legacy_flavour")

    # --- S1 / S2 / S3 ----------------------------------------------------------------
    def test_S2_no_tailnet_means_no_bridge_unit(self):
        host = support.fixture("desktop-nvidia-32g")
        host["tailscale"] = {"installed": True, "logged_in": False}
        host["services"]["units"] = []
        host["workspace"]["owned"] = []
        plan_obj = self.p.plan(host, self.snap, grants=ALL_BUNDLES)
        state = {e["step"]["id"]: e["state"] for e in plan_obj["steps"]}
        self.assertEqual(state["dash.bridge.unit"], {"status": "unavailable", "reason": "no_tailnet"})
        ask = [a for a in plan_obj["asks"] if a["id"] == "dash.bridge.unit"]
        self.assertEqual(ask[0]["command"], "tailscale up, then re-run ./z0 onboard")
        self.assertEqual(state["dash.selftest.loopback"]["status"], "todo")

    def test_S1_S2_red_open_bind_and_checkout_root_are_refused(self):
        snap = support.snapshot()
        steps = snap["components"]["components"]["dash"]["onboard"]["steps"]
        unit = next(s for s in steps if s["id"] == "dash.bridge.unit")
        unit["service"]["bind"] = "0.0.0.0"
        host = support.fixture("desktop-nvidia-32g")
        host["services"]["units"] = []
        host["workspace"]["owned"] = []
        state = {e["step"]["id"]: e["state"] for e in
                 self.p.plan(host, snap, grants=ALL_BUNDLES)["steps"]}
        self.assertEqual(state["dash.bridge.unit"], {"status": "refused", "reason": "open_bind"})
        unit["service"]["bind"] = "tailnet_ipv4"
        unit["where"] = "build"
        state = {e["step"]["id"]: e["state"] for e in
                 self.p.plan(host, snap, grants=ALL_BUNDLES)["steps"]}
        self.assertEqual(state["dash.bridge.unit"], {"status": "refused", "reason": "through_checkout"})

    def test_S1_harness_plugins_never_link_a_checkout_or_build_tree(self):
        """§11 S1 covers plugin paths: a harness_plugin step where: build is refused."""
        snap = support.snapshot()
        steps = snap["components"]["components"]["oh-my-pi"]["onboard"]["steps"]
        setup = next(s for s in steps if s["id"] == "oh-my-pi.setup")
        host = support.fixture("desktop-nvidia-32g")
        state = {e["step"]["id"]: e["state"] for e in
                 self.p.plan(host, snap, grants=ALL_BUNDLES)["steps"]}
        self.assertEqual(state["oh-my-pi.setup"]["status"], "todo")
        for where, reason in (("build", "through_checkout"), ("mirror", "through_checkout"),
                              ("home", "outside_roots")):
            setup["where"] = where
            state = {e["step"]["id"]: e["state"] for e in
                     self.p.plan(host, snap, grants=ALL_BUNDLES)["steps"]}
            self.assertEqual(state["oh-my-pi.setup"], {"status": "refused", "reason": reason}, where)

    def test_S1_shim_and_env_files_point_only_at_releases_or_venvs(self):
        for name, _, _, plan_obj in self.plans():
            for entry in plan_obj["steps"]:
                step = entry["step"]
                if step["kind"] in ("service_unit", "harness_plugin") or step.get("target_where"):
                    if entry["state"]["status"] in ("todo", "already_satisfied"):
                        with self.subTest(case=name, step=step["id"]):
                            self.assertIn(step.get("target_where", step.get("where")),
                                          ("release", "venv"))
        snap = support.snapshot()
        steps = snap["components"]["components"]["z0intelligence"]["onboard"]["steps"]
        next(s for s in steps if s["id"] == "z0intelligence.shim")["target_where"] = "build"
        state = {e["step"]["id"]: e["state"] for e in
                 self.p.plan(support.fixture("desktop-nvidia-32g"), snap, grants=ALL_BUNDLES)["steps"]}
        self.assertEqual(state["z0intelligence.shim"], {"status": "refused", "reason": "through_checkout"})

    # --- §3 / §6.1 blocked(dep) over depends_on --------------------------------------
    def test_depends_on_failure_blocks_dependents(self):
        plan_obj = self.p.plan(support.fixture("tiny-4g-vps"), self.snap, profile="full")
        state = {e["step"]["id"]: e["state"] for e in plan_obj["steps"]}
        by_comp: dict = {}
        for entry in plan_obj["steps"]:
            by_comp.setdefault(entry["step"]["component"], []).append(entry["state"]["status"])
        # the dependency's own C0 source clone needs only git and may still run; every
        # other tokenomics step must not (its toolchains are not granted)
        own = [e["state"]["status"] for e in plan_obj["steps"]
               if e["step"]["component"] == "tokenomics" and e["step"]["kind"] != "adopt_or_clone"]
        self.assertNotIn("todo", own)
        self.assertNotIn("already_satisfied", by_comp["tokenomics"])
        for dependent in ("kerdoios",):  # z0intelligence only integrates with tokenomics (test extra), it does not depend on it
            with self.subTest(dependent=dependent):
                self.assertNotIn("todo", by_comp[dependent])
        self.assertEqual(state["kerdoios.source"]["status"], "blocked")
        self.assertTrue(state["kerdoios.source"]["blocked_by"].startswith("tokenomics."))
        self.assertEqual(plan_obj["components"]["kerdoios"]["blocked_by"], "tokenomics")
        # Red: with the dependency's tools granted, the dependent is planned again.
        granted = self.p.plan(support.fixture("tiny-4g-vps"), self.snap, profile="full",
                              grants=ALL_BUNDLES)
        state = {e["step"]["id"]: e["state"] for e in granted["steps"]}
        self.assertEqual(state["kerdoios.source"]["status"], "todo")

    # --- P1 on the prepared PATH (§4) ------------------------------------------------
    def test_P1_prepared_path_holds_no_never_harness_dir(self):
        never = {hid for hid, row in self.snap["harnesses"]["harnesses"].items()
                 if (row.get("policy") or {}).get("configure") == "never"}
        system = set(self.snap["toolchains"]["detect"]["system_dirs"])
        checked = 0
        for name, host, _, plan_obj in self.plans():
            for hid in never:
                entry = (host.get("harnesses") or {}).get(hid) or {}
                for bin_dir in entry.get("bin_dirs") or [entry.get("bin_dir")]:
                    if bin_dir and bin_dir not in system:
                        checked += 1
                        with self.subTest(case=name, harness=hid, bin_dir=bin_dir):
                            self.assertNotIn(bin_dir, plan_obj["prepared_path"])
                            self.assertIn("$Z0_HOME/bin/links", plan_obj["prepared_path"])
        self.assertGreater(checked, 0, "no fixture exercises a shared never-harness dir")
        desktop = self.p.plan(support.fixture("desktop-nvidia-32g"), self.snap)
        self.assertEqual(desktop["prepared_path"],
                         ["$Z0_HOME/bin/links", "~/.bun/bin", "/usr/bin", "/bin"])
        links = {link["link"].rsplit("/", 1)[1]: link["target"] for link in desktop["path_links"]}
        self.assertEqual(links["claude"], "~/.local/bin/claude")
        self.assertEqual(links["uv"], "~/.local/bin/uv")
        self.assertNotIn("grok", links)
        self.assertEqual(desktop["steps"][0]["step"]["id"], "z0.path_links")

    def test_P1_red_without_bin_dir_the_shared_dir_stays(self):
        host = support.fixture("desktop-nvidia-32g")
        del host["harnesses"]["grok"]["bin_dir"]
        host["harnesses"]["grok"].pop("bin_dirs", None)
        self.assertIn("~/.local/bin", self.p.plan(host, self.snap)["prepared_path"])

    def test_P1_every_bin_dir_of_a_never_harness_is_dropped(self):
        """grok in two prepared-PATH dirs: both are swapped out, not only the first."""
        host = support.fixture("desktop-nvidia-32g")
        host["harnesses"]["grok"]["bin_dirs"] = ["~/.local/bin", "~/.bun/bin"]
        path = self.p.plan(host, self.snap)["prepared_path"]
        self.assertNotIn("~/.local/bin", path)
        self.assertNotIn("~/.bun/bin", path)
        # Red: the first dir alone (the old bin_dir) leaves the second on the PATH.
        host["harnesses"]["grok"]["bin_dirs"] = ["~/.local/bin"]
        self.assertIn("~/.bun/bin", self.p.plan(host, self.snap)["prepared_path"])

    # --- §4/§8.1 hub checks run with the z0 venv -------------------------------------
    def test_hub_checks_resolve_python3_to_the_z0_venv(self):
        """On a host whose system python3 lacks PyYAML (why stage 0 exists), the hub
        checks still find it: the z0 venv bin leads their PATH."""
        for name, _, _, plan_obj in self.plans():
            for entry in plan_obj["steps"]:
                step = entry["step"]
                if step["component"] == "z0" and step["kind"] == "check":
                    with self.subTest(case=name, step=step["id"]):
                        path = step.get("env", {}).get("PATH", "")
                        self.assertEqual(path, ":".join(["$Z0_HOME/venv/bin", *plan_obj["prepared_path"]]))

    # --- §1.2 asks a stranger can act on ----------------------------------------------
    def test_every_ask_is_actionable_today(self):
        for name, _, _, plan_obj in self.plans():
            for ask in plan_obj["asks"]:
                with self.subTest(case=name, ask=ask["id"]):
                    self.assertNotIn("onboard accept", ask["command"], "accept arrives in Z2")
                    self.assertNotRegex(ask["reason"], r"^[a-z0-9_]+$", "raw reason code")
                    if ask["consent"] == "C1":
                        self.assertRegex(ask["command"], r"^\./z0 onboard --accept [a-z]+")
                        self.assertIn("needs consent", ask["reason"])

    def test_no_toolchain_ask_when_every_user_is_unavailable(self):
        plan_obj = self.p.plan(support.fixture("fresh-stranger"), self.snap)
        self.assertEqual(plan_obj["profile"], "core")
        dead = {u["id"] for u in plan_obj["unavailable"]}
        self.assertTrue({"oh-my-pi", "dash"} <= dead)
        ids = [a["id"] for a in plan_obj["asks"]]
        self.assertNotIn("toolchain.bun", ids)
        self.assertIn("toolchain.node", ids)  # tokenomics and the z0evals web tier need it
        node = next(a for a in plan_obj["asks"] if a["id"] == "toolchain.node")
        self.assertEqual(node["command"], "./z0 onboard --accept toolchains   (or --yes for every bundle)")
        self.assertIn("node 22.23.4", node["reason"])

    def test_unavailable_components_say_why(self):
        plan_obj = self.p.plan(support.fixture("fresh-stranger"), self.snap)
        entry = next(u for u in plan_obj["unavailable"] if u["id"] == "oh-my-pi")
        self.assertEqual(entry["reason"], "hardware:disk<5GiB")
        self.assertEqual(entry["detail"], "disk < 5 GiB free at ~; free space or set Z0_HOME on a "
                                          "larger volume")
        from z0.onboard.cli import summary_text
        text = summary_text(plan_obj, None)
        self.assertIn("Unavailable:\n", text)
        self.assertIn("  oh-my-pi: unavailable (disk < 5 GiB free at ~;", text)
        self.assertIn("  dash: unavailable (could not check the pinned revs on origin;", text)

    def test_S3_adopted_unit_same_sha_kept_other_sha_is_C2(self):
        plan_obj = self.p.plan(support.fixture("desktop-nvidia-32g"), self.snap, grants=ALL_BUNDLES)
        state = {e["step"]["id"]: e["state"] for e in plan_obj["steps"]}
        self.assertEqual(state["dash.bridge.unit"]["status"], "already_satisfied")
        self.assertEqual(state["z0intelligence.router.unit"],
                         {"status": "ask", "reason": "c2_never_auto"})

    def test_S3_red_adopted_unit_with_its_unit_file_present_still_asks(self):
        """On a configured host the adopted unit's file exists (detect puts it in
        `owned`). That must not turn a redeploy at another SHA into already_satisfied."""
        host = support.fixture("desktop-nvidia-32g")
        host["workspace"]["owned"].append("~/.config/systemd/user/z0intelligence.service")
        unit = next(u for u in host["services"]["units"] if u["name"] == "z0intelligence.service")
        pin = self.snap["components"]["components"]["z0intelligence"]["install"]["ref"]
        self.assertFalse(pin.startswith(unit["deployed_sha"]), "fixture must run another SHA")
        for kwargs, reason in (({"grants": ALL_BUNDLES}, "c2_never_auto"),
                               ({"mode": "guided", "grants": TTY_ALL}, "c2_confirm")):
            plan_obj = self.p.plan(host, self.snap, **kwargs)
            entry = next(e for e in plan_obj["steps"] if e["step"]["id"] == "z0intelligence.router.unit")
            with self.subTest(**{"mode": kwargs.get("mode", "auto")}):
                self.assertEqual(entry["state"], {"status": "ask", "reason": reason})
                self.assertEqual(entry["step"]["consent"], {"class": "C2"})
                ask = next(a for a in plan_obj["asks"] if a["id"] == "z0intelligence.router.unit")
                self.assertEqual(ask["consent"], "C2")
        # Same SHA: the unit is adopted and kept, with or without its file in `owned`.
        unit["deployed_sha"] = pin
        state = {e["step"]["id"]: e["state"] for e in
                 self.p.plan(host, self.snap, grants=ALL_BUNDLES)["steps"]}
        self.assertEqual(state["z0intelligence.router.unit"], {"status": "already_satisfied"})

    def test_C2_a_bundle_grant_never_confirms_a_C2_step(self):
        """§3: guided asks C2 per step. A TTY grant of every bundle is not a per-step
        confirmation: the adopted other-SHA unit, ask steps and shadow components stay asks."""
        host = support.fixture("desktop-nvidia-32g")
        host["workspace"]["owned"].append("~/.config/systemd/user/z0intelligence.service")
        plan_obj = self.p.plan(host, self.snap, mode="guided", grants=TTY_ALL,
                               with_ids=["evolution-lab", "flow"])
        c2 = [e for e in plan_obj["steps"] if e["step"]["consent"]["class"] == "C2"
              or e["step"]["kind"] == "ask" or e["step"]["component"] in ("evolution-lab", "flow")]
        self.assertIn("z0intelligence.router.unit", [e["step"]["id"] for e in c2])
        for entry in c2:
            with self.subTest(step=entry["step"]["id"]):
                self.assertNotIn(entry["state"]["status"], ("todo", "already_satisfied"))
        # A per-step TTY confirmation (answers.yaml confirmed_steps) is what applies it.
        answers = {"confirmed_steps": ["z0intelligence.router.unit"]}
        state = {e["step"]["id"]: e["state"] for e in
                 self.p.plan(host, self.snap, mode="guided", grants=TTY_ALL, answers=answers)["steps"]}
        self.assertEqual(state["z0intelligence.router.unit"], {"status": "todo"})
        # Red: the same confirmation from a flag (--yes) or in auto never applies C2.
        for kwargs in ({"mode": "guided", "grants": ALL_BUNDLES}, {"grants": TTY_ALL}):
            state = {e["step"]["id"]: e["state"] for e in
                     self.p.plan(host, self.snap, answers=answers, **kwargs)["steps"]}
            self.assertEqual(state["z0intelligence.router.unit"]["status"], "ask", kwargs)

    # --- §8.2.5 generators first / I1 on an adopted checkout ---------------------------
    def test_I1_tracked_file_never_satisfies_a_generator(self):
        """web/data/study.json is tracked, so every adopted z0evals checkout has it.
        Only the untracked generator output may say build_site_data.py already ran."""
        host = support.fixture("laptop-cpu-15g")
        summary = self.p.plan(host, self.snap)["components"]["z0evals"]
        self.assertTrue(summary["adopted"])
        tree = summary["tree"]
        host["workspace"]["owned"].append(f"{tree}/web/data/study.json")
        state = {e["step"]["id"]: e["state"] for e in self.p.plan(host, self.snap)["steps"]}
        self.assertEqual(state["z0evals.t1.site_data"], {"status": "todo"})
        host["workspace"]["owned"].append(f"{tree}/web/data/optchat-long-horizon-v0.json")
        state = {e["step"]["id"]: e["state"] for e in self.p.plan(host, self.snap)["steps"]}
        self.assertEqual(state["z0evals.t1.site_data"], {"status": "already_satisfied"})

    def test_z0evals_steps_never_probe_a_tracked_path(self):
        """Paths z0evals tracks in git (spec §1 C6, §9 B3) exist in every checkout."""
        tracked = ("web/data/study.json", "studies/slm-router-v0/data/phase1b-matrix.json",
                   "web/package-lock.json", "requirements.txt")
        for step in self.snap["components"]["components"]["z0evals"]["onboard"]["steps"]:
            paths = list(step.get("creates") or []) + [(step.get("probe") or {}).get("exists", "")]
            for path in paths:
                with self.subTest(step=step["id"], path=path):
                    self.assertFalse(any(path.endswith("/" + t) for t in tracked))

    # --- §2.6 repo-local setup ----------------------------------------------------------
    def test_repo_setup_registry_wins_and_conflicts_are_reported(self):
        host = support.fixture("laptop-cpu-15g")
        plan_obj = self.p.plan(host, self.snap, repo_setups=support.SETUP_CONFLICT)
        by_id = {e["step"]["id"]: e for e in plan_obj["steps"]}
        registry = {s["id"]: s for s in self.snap["components"]["components"]["z0evals"]["onboard"]["steps"]}
        conflicts = {c["id"]: c for c in plan_obj["conflicts"]}
        self.assertEqual(set(conflicts), {"z0evals.t1.pages", "z0evals.t1.validate_again"})
        self.assertEqual(conflicts["z0evals.t1.pages"]["fields"], ["argv"])
        self.assertEqual(conflicts["z0evals.t1.validate_again"]["registry_id"], "z0evals.t1.validate")
        self.assertEqual(by_id["z0evals.t1.pages"]["step"]["argv"], registry["z0evals.t1.pages"]["argv"])
        self.assertNotIn("z0evals.t1.validate_again", by_id)
        self.assertEqual(by_id["z0evals.t1.repo_setup"]["state"], {"status": "todo"})
        self.assertEqual(by_id["z0evals.t1.receipt_index"]["step"]["creates"],
                         ["~/workspace/z0evals/web/data/receipts.json"])
        self.assertNotIn("z0evals.t1.warm_cache", by_id)
        self.assertTrue(any("warm_cache" in w and "(I1)" in w for w in plan_obj["warnings"]))
        source = "kvnloo/z0evals@29a28336e526edfb4c3913c30df6eff12b28b2d6:zer0.repo.yaml"
        self.assertIn(source, plan_obj["registry"])
        from z0.onboard.cli import summary_text
        text = summary_text(plan_obj, None)
        self.assertIn("Repo setup conflicts (zer0.repo.yaml vs the registry; the registry wins):", text)
        self.assertIn("  z0evals.t1.pages: differs in argv", text)
        # Without a setup block the plan is the registry's alone.
        plain = self.p.plan(host, self.snap)
        self.assertNotIn("conflicts", plain)
        self.assertNotIn(source, plain["registry"])

    def test_repo_setup_read_at_another_sha_is_ignored(self):
        setups = json.loads(json.dumps(support.SETUP_CONFLICT))
        setups["z0evals"]["ref"] = "0" * 40
        plan_obj = self.p.plan(support.fixture("laptop-cpu-15g"), self.snap, repo_setups=setups)
        self.assertNotIn("conflicts", plan_obj)
        self.assertNotIn("z0evals.t1.repo_setup", [e["step"]["id"] for e in plan_obj["steps"]])
        self.assertTrue(any("not at the pin" in w for w in plan_obj["warnings"]))

    def test_repo_setup_steps_count_in_detect_owned_paths(self):
        """detect and plan merge the same steps, so a repo step's path proves it ran (I1)."""
        import tempfile
        from z0.onboard.detect import Ctx
        from z0.onboard.detect.workspace import owned_paths
        snap = support.snapshot()
        snap["repo_setups"] = support.SETUP_CONFLICT
        with tempfile.TemporaryDirectory() as home:
            out = Path(home, ".z0/repos/z0evals/web/data/receipts.json")
            out.parent.mkdir(parents=True)
            out.write_text("{}")
            ctx = Ctx(registry=snap, env={"HOME": home}, uname=("Linux", "x86_64"), hostname="h")
            owned = owned_paths(ctx, {"checkouts": []})
        self.assertIn("$Z0_HOME/repos/z0evals/web/data/receipts.json", owned)

    # --- Z1 / Z2 -------------------------------------------------------------------
    def test_Z2_cpu_class_uses_the_cpu_torch_index(self):
        plan_obj = self.p.plan(support.fixture("laptop-cpu-15g"), self.snap)
        torch = next(e["step"] for e in plan_obj["steps"] if e["step"]["id"] == "z0intelligence.torch")
        self.assertEqual(torch["argv"][-2:], ["--index-url", "https://download.pytorch.org/whl/cpu"])
        desktop = self.p.plan(support.fixture("desktop-nvidia-32g"), self.snap)
        torch = next(e["step"] for e in desktop["steps"] if e["step"]["id"] == "z0intelligence.torch")
        self.assertNotIn("--index-url", torch["argv"])

    def test_Z1_intel_mac_refuses_z0intelligence(self):
        host = support.fixture("apple-m-32g")
        host["hardware"]["gpu"] = {"class": "intel_mac"}
        host["os"]["arch"] = "x86_64"
        plan_obj = self.p.plan(host, self.snap, profile="personal")
        self.assertEqual(plan_obj["components"]["z0intelligence"]["reason"], "intel_mac")

    # --- T1 ------------------------------------------------------------------------
    def test_T1_plan_carries_the_prepared_path(self):
        """The plan's PATH is detect's, with only a never-harness dir swapped (P1)."""
        for name, host, _, plan_obj in self.plans():
            swapped = {d for e in (host.get("harnesses") or {}).values()
                       for d in (e.get("bin_dirs") or [e.get("bin_dir")])}
            want = []
            for d in host.get("prepared_path", []):
                d = "$Z0_HOME/bin/links" if d in swapped and d not in ("/usr/bin", "/bin") else d
                if d not in want:
                    want.append(d)
            self.assertEqual(plan_obj["prepared_path"], want, name)

    def test_T1_no_python_stranger_runs_the_stage0_python3(self):
        """§1.1/§1.3: no python3 on PATH; stage 0 made $Z0_HOME/venv. `python3` is that
        interpreter, its dir leads the prepared PATH, and tier 0 runs with it."""
        host = support.fixture("no-python")
        plan_obj = self.p.plan(host, self.snap)
        state = {e["step"]["id"]: e["state"] for e in plan_obj["steps"]}
        self.assertEqual(state["toolchain.python3"], {"status": "already_satisfied"})
        python_dir = host["toolchains"]["python3"]["path"].rsplit("/", 1)[0]
        self.assertEqual(plan_obj["prepared_path"][0], python_dir)
        tier0 = [sid for sid in state if sid.startswith("z0evals.t0.")]
        self.assertEqual(len(tier0), 4)
        for sid in tier0:
            self.assertEqual(state[sid], {"status": "todo"}, sid)
        # Red: python3 is absent (a window python exists only off the PATH). The window
        # alone must not satisfy python3, and tier 0 must not run with a missing python3.
        host["toolchains"]["python3"] = {"state": "absent"}
        host["prepared_path"] = ["/usr/bin", "/bin"]
        state = {e["step"]["id"]: e["state"] for e in self.p.plan(host, self.snap)["steps"]}
        self.assertNotEqual(state["toolchain.python3"]["status"], "already_satisfied")
        for sid in tier0:
            self.assertNotIn(state[sid]["status"], ("todo", "already_satisfied"), sid)
        # Red: a python3 below 3.10 on the PATH does not satisfy python>=3.10 either.
        host["toolchains"]["python3"] = {"state": "present", "version": "3.9.18", "sh_resolves": True,
                                         "source": "path", "path": "/usr/bin/python3"}
        state = {e["step"]["id"]: e["state"] for e in self.p.plan(host, self.snap)["steps"]}
        self.assertNotEqual(state["toolchain.python3"]["status"], "already_satisfied")

    def test_T1_red_tool_off_the_prepared_path_is_not_satisfied(self):
        host = support.fixture("laptop-cpu-15g")
        host["toolchains"]["bun"]["sh_resolves"] = False
        state = {e["step"]["id"]: e["state"] for e in self.p.plan(host, self.snap)["steps"]}
        self.assertNotEqual(state["toolchain.bun"]["status"], "already_satisfied")

    # --- profiles (§5.2) ----------------------------------------------------------
    def test_profile_defaults(self):
        expect = {"desktop-nvidia-32g": "personal", "laptop-cpu-15g": "personal",
                  "apple-m-32g": "personal", "tiny-4g-vps": "core", "offline": "personal"}
        for fixture, profile in expect.items():
            self.assertEqual(self.p.plan(support.fixture(fixture), self.snap)["profile"], profile)
        host = support.fixture("tiny-4g-vps")
        host["hardware"]["disks"][0]["free_gib"] = 2.0
        plan_obj = self.p.plan(host, self.snap)
        self.assertEqual(plan_obj["profile"], "")
        self.assertEqual(self.p.exit_code(plan_obj), 4)

    def test_missing_system_tool_degrades_with_a_printed_command(self):
        plan_obj = self.p.plan(support.fixture("offline"), self.snap)
        ask = next(a for a in plan_obj["asks"] if a["id"] == "toolchain.git")
        self.assertEqual(ask["command"], "sudo dnf install -y git")
        self.assertEqual(ask["consent"], "C2")


if __name__ == "__main__":
    unittest.main()
