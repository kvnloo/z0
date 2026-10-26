"""Plan-level laws over the golden fixtures and seeded random variants (§10, §11).

O1 order, I1 idempotence, C1/C2 consent, L-LLM grant source, P1 forbidden harness,
M1/M2, H1 host match, D1/D2 dash gates, S1/S2 services, Z2 torch index, T1 prepared
PATH in the plan, plus one red case per law (a violating plan or input must fail).
"""
from __future__ import annotations

import json
import random
import unittest

from tests.onboard import support
from tests.onboard.support import ALL_BUNDLES, GOLDEN_CASES, require_yaml

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
        plan_obj = self.p.plan(support.fixture("mbp-cpu-15g"), self.snap)
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
        plan_obj = self.p.plan(support.fixture("mbp-cpu-15g"), self.snap, grants=ALL_BUNDLES,
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
        plan_obj = self.p.plan(support.fixture("groot-nvidia-32g"), snap, grants=ALL_BUNDLES)
        state = {e["step"]["id"]: e["state"] for e in plan_obj["steps"]}["z0intelligence.plugin.grok"]
        self.assertEqual(state, {"status": "refused", "reason": "forbidden_provider"})

    # --- M1 / M2 -------------------------------------------------------------------
    def test_M1_memento_never_planned(self):
        for name, _, _, plan_obj in self.plans():
            self.assertFalse([e for e in plan_obj["steps"] if e["step"]["component"] == "memento"
                              and e["state"]["status"] == "todo"], name)

    def test_M2_shadow_is_an_ask(self):
        plan_obj = self.p.plan(support.fixture("groot-nvidia-32g"), self.snap,
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
        plan_obj = self.p.plan(support.fixture("mbp-cpu-15g"), self.snap)
        self.assertEqual(plan_obj["components"]["dash"]["reason"], "rev_not_on_origin")
        dash = [e for e in plan_obj["steps"] if e["step"]["component"] == "dash"]
        self.assertEqual({e["state"]["status"] for e in dash}, {"unavailable"})
        self.assertTrue([e for e in plan_obj["steps"] if e["step"]["component"] == "z0evals"
                         and e["state"]["status"] in ("todo", "already_satisfied")])

    def test_D2_legacy_dash_is_refused(self):
        host = support.fixture("groot-nvidia-32g")
        for fact in host["revs"].values():
            if fact["repo"] == "kvnloo/dash":
                fact["flavour"] = "legacy"
        plan_obj = self.p.plan(host, self.snap, grants=ALL_BUNDLES)
        self.assertEqual(plan_obj["components"]["dash"]["verdict"], "refuse")
        self.assertEqual(plan_obj["components"]["dash"]["reason"], "legacy_flavour")

    # --- S1 / S2 / S3 ----------------------------------------------------------------
    def test_S2_no_tailnet_means_no_bridge_unit(self):
        host = support.fixture("groot-nvidia-32g")
        host["tailscale"] = {"installed": True, "logged_in": False}
        host["services"]["units"] = []
        host["workspace"]["owned"] = []
        plan_obj = self.p.plan(host, self.snap, grants=ALL_BUNDLES)
        state = {e["step"]["id"]: e["state"] for e in plan_obj["steps"]}
        self.assertEqual(state["dash.bridge.unit"], {"status": "unavailable", "reason": "no_tailnet"})
        ask = [a for a in plan_obj["asks"] if a["id"] == "dash.bridge.unit"]
        self.assertEqual(ask[0]["command"], "tailscale up, then ./z0 onboard accept dash.bridge.unit")
        self.assertEqual(state["dash.selftest.loopback"]["status"], "todo")

    def test_S1_S2_red_open_bind_and_checkout_root_are_refused(self):
        snap = support.snapshot()
        steps = snap["components"]["components"]["dash"]["onboard"]["steps"]
        unit = next(s for s in steps if s["id"] == "dash.bridge.unit")
        unit["service"]["bind"] = "0.0.0.0"
        host = support.fixture("groot-nvidia-32g")
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

    def test_S3_adopted_unit_same_sha_kept_other_sha_is_C2(self):
        plan_obj = self.p.plan(support.fixture("groot-nvidia-32g"), self.snap, grants=ALL_BUNDLES)
        state = {e["step"]["id"]: e["state"] for e in plan_obj["steps"]}
        self.assertEqual(state["dash.bridge.unit"]["status"], "already_satisfied")
        self.assertEqual(state["z0intelligence.router.unit"],
                         {"status": "ask", "reason": "c2_never_auto"})

    # --- Z1 / Z2 -------------------------------------------------------------------
    def test_Z2_cpu_class_uses_the_cpu_torch_index(self):
        plan_obj = self.p.plan(support.fixture("mbp-cpu-15g"), self.snap)
        torch = next(e["step"] for e in plan_obj["steps"] if e["step"]["id"] == "z0intelligence.torch")
        self.assertEqual(torch["argv"][-2:], ["--index-url", "https://download.pytorch.org/whl/cpu"])
        groot = self.p.plan(support.fixture("groot-nvidia-32g"), self.snap)
        torch = next(e["step"] for e in groot["steps"] if e["step"]["id"] == "z0intelligence.torch")
        self.assertNotIn("--index-url", torch["argv"])

    def test_Z1_intel_mac_refuses_z0intelligence(self):
        host = support.fixture("apple-m-32g")
        host["hardware"]["gpu"] = {"class": "intel_mac"}
        host["os"]["arch"] = "x86_64"
        plan_obj = self.p.plan(host, self.snap, profile="personal")
        self.assertEqual(plan_obj["components"]["z0intelligence"]["reason"], "intel_mac")

    # --- T1 ------------------------------------------------------------------------
    def test_T1_plan_carries_the_prepared_path(self):
        for name, host, _, plan_obj in self.plans():
            self.assertEqual(plan_obj["prepared_path"], host.get("prepared_path", []), name)

    def test_T1_red_tool_off_the_prepared_path_is_not_satisfied(self):
        host = support.fixture("mbp-cpu-15g")
        host["toolchains"]["bun"]["sh_resolves"] = False
        state = {e["step"]["id"]: e["state"] for e in self.p.plan(host, self.snap)["steps"]}
        self.assertNotEqual(state["toolchain.bun"]["status"], "already_satisfied")

    # --- profiles (§5.2) ----------------------------------------------------------
    def test_profile_defaults(self):
        expect = {"groot-nvidia-32g": "personal", "mbp-cpu-15g": "personal",
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
