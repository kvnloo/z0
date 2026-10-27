"""Onboard schemas: well-formed, closed where the laws need it, and in step with kernel.py.

Structural checks are stdlib only. Instance checks (green and red fixtures) run when
`jsonschema` is importable; it is not a dependency of z0.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from z0.onboard import kernel as k  # noqa: E402

SCHEMAS = ROOT / "schemas"
NAMES = ("host-profile", "onboard-step", "onboard-plan", "onboard-receipt", "onboarding")
STEP_KINDS = ["ensure_toolchain", "adopt_or_clone", "build_tree", "stage_release", "swap_current",
              "venv", "pip_install", "run", "write_file", "service_unit", "harness_plugin",
              "delegate", "check", "ask"]  # design §2.5
PLAN_STATES = ["todo", "already_satisfied", "ask", "unavailable", "refused", "blocked"]  # §6.1

try:
    import jsonschema
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - optional
    jsonschema = None


def load(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text())


def snake(enum):
    return [member.name.lower() for member in enum]


class SchemaStructure(unittest.TestCase):
    def test_all_parse_with_draft_and_id(self):
        for name in NAMES:
            with self.subTest(schema=name):
                schema = load(name)
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertTrue(schema["$id"].endswith(f"/schemas/{name}.schema.json"))
                self.assertFalse(schema.get("additionalProperties", True), "top level must be closed")

    def test_step_kinds_are_the_closed_design_set(self):
        self.assertEqual(load("onboard-step")["$defs"]["kind"]["enum"], STEP_KINDS)

    def test_where_has_no_checkout(self):
        where = load("onboard-step")["$defs"]["where"]["enum"]
        self.assertEqual(where, ["mirror", "build", "release", "venv", "home"])

    def test_bind_classes_are_exactly_what_the_kernel_allows(self):
        allowed = [b.name.lower() for b in k.BindClass
                   if k.decide_bind(b, k.IpSource.CURRENT) == k.ALLOW]
        self.assertEqual(load("onboard-step")["$defs"]["bind"]["enum"], allowed)
        self.assertEqual(load("onboarding")["properties"]["bind_classes"]["items"]["enum"], allowed)

    def test_consent_classes_match_kernel(self):
        consent = load("onboard-step")["$defs"]["consent"]["properties"]["class"]["enum"]
        self.assertEqual(consent, [c.value for c in k.ConsentClass])

    def test_plan_states(self):
        state = load("onboard-plan")["$defs"]["state"]["properties"]["status"]["enum"]
        self.assertEqual(state, PLAN_STATES)

    def test_host_profile_enums_match_kernel(self):
        props = load("host-profile")["properties"]
        self.assertEqual(props["hardware"]["properties"]["gpu"]["properties"]["class"]["enum"],
                         snake(k.HwClass))
        self.assertEqual(props["python_window"]["enum"], snake(k.PyWindow))
        self.assertEqual(props["workspace"]["properties"]["host_match"]["enum"], snake(k.HostMatch))
        unit = props["services"]["properties"]["units"]["items"]["properties"]
        self.assertEqual(unit["exec_root_kind"]["enum"], snake(k.RootKind))

    def test_llm_providers_are_never_forbidden(self):
        llm = load("onboarding")["properties"]["llm"]["properties"]
        for provider in llm["providers"]["items"]["properties"]["id"]["enum"]:
            verdict = k.decide_provider(k.provider_from_id(provider))
            self.assertIn(verdict.kind, (k.Kind.ALLOW, k.Kind.ASK), provider)
        receipt = load("onboard-receipt")["properties"]["llm_decisions"]["items"]["properties"]
        for provider in receipt["provider"]["enum"]:
            self.assertNotEqual(k.decide_provider(k.provider_from_id(provider)).kind, k.Kind.REFUSE)

    def test_secret_values_cannot_be_expressed(self):
        secret = load("host-profile")["properties"]["secrets"]["additionalProperties"]
        self.assertEqual(set(secret["properties"]), {"present", "mode_ok"})
        self.assertFalse(secret["additionalProperties"])


GREEN_STEP = {
    "id": "dash.bridge.unit", "component": "dash", "kind": "service_unit",
    "consent": {"class": "C1", "bundle": "services"}, "where": "release",
    "service": {"template": "dash-bridge", "bind": "tailnet_ipv4", "port": 4747,
                "limits": {"memory_max": "1G"}},
}


@unittest.skipIf(jsonschema is None, "jsonschema not installed (optional)")
class SchemaInstances(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        resources = [(load(n)["$id"], Resource.from_contents(load(n))) for n in NAMES]
        cls.registry = Registry().with_resources(resources)

    def validator(self, name):
        return jsonschema.Draft202012Validator(load(name), registry=self.registry)

    def assert_valid(self, name, instance):
        errors = list(self.validator(name).iter_errors(instance))
        self.assertEqual(errors, [], name)

    def assert_invalid(self, name, instance, why):
        self.assertTrue(list(self.validator(name).iter_errors(instance)), why)

    def test_schemas_are_valid_2020_12(self):
        for name in NAMES:
            jsonschema.Draft202012Validator.check_schema(load(name))

    def test_green_step(self):
        self.assert_valid("onboard-step", GREEN_STEP)

    def test_red_steps(self):
        wildcard = json.loads(json.dumps(GREEN_STEP))
        wildcard["service"]["bind"] = "0.0.0.0"
        self.assert_invalid("onboard-step", wildcard, "S2: wildcard bind")
        checkout = dict(GREEN_STEP, where="checkout")
        self.assert_invalid("onboard-step", checkout, "S1: where=checkout")
        run = {"id": "x.run", "component": "x", "kind": "run", "argv": ["true"], "where": "build",
               "consent": {"class": "C0"}}
        self.assert_invalid("onboard-step", run, "run without creates|probe")
        self.assert_valid("onboard-step", dict(run, probe={"argv": ["true"]}))
        ungrouped = dict(GREEN_STEP, consent={"class": "C1"})
        self.assert_invalid("onboard-step", ungrouped, "C1 without a bundle")
        home = dict(run, probe={"argv": ["true"]}, creates=["/home/someone/x"])
        self.assert_invalid("onboard-step", home, "absolute $HOME path instead of ~")

    def test_plan_wraps_steps_with_state(self):
        plan = {"version": 1, "plan_hash": "0" * 64, "host_id": "0123456789abcdef",
                "mode": "auto", "grants": {"bundles": ["services"], "source": "flag"},
                "registry": {"registry/components.yaml": "1" * 64},
                "steps": [{"step": GREEN_STEP, "state": {"status": "todo"}}]}
        self.assert_valid("onboard-plan", plan)
        llm_grant = json.loads(json.dumps(plan))
        llm_grant["grants"]["source"] = "llm"
        self.assert_invalid("onboard-plan", llm_grant, "L-LLM: an LLM is not a grant source")
        no_reason = json.loads(json.dumps(plan))
        no_reason["steps"][0]["state"] = {"status": "refused"}
        self.assert_invalid("onboard-plan", no_reason, "refused without reason")

    def test_onboarding_requires_grok_and_cursor_forbidden(self):
        policy = {"version": 1,
                  "consent": {"classes": {"C0": "", "C1": "", "C2": ""},
                              "bundles": {"toolchains": "", "harness": "", "services": "",
                                          "models": ""}},
                  "bind_classes": ["loopback", "tailnet_ipv4"],
                  "llm": {"providers": [{"id": "local", "order": 1}],
                          "budget": {"max_calls": 8, "call_timeout_s": 30, "total_s": 180},
                          "forbidden": ["grok", "cursor"]},
                  "denylists": {"reads": ["~/.ssh"], "redaction": ["~/.ssh"]}}
        self.assert_valid("onboarding", policy)
        self.assert_invalid("onboarding", dict(policy, llm=dict(policy["llm"], forbidden=["grok"])),
                            "P1: cursor missing from forbidden")
        grok = dict(policy["llm"], providers=[{"id": "grok", "order": 1}])
        self.assert_invalid("onboarding", dict(policy, llm=grok), "P1: grok as provider")
        self.assert_invalid("onboarding", dict(policy, bind_classes=["0.0.0.0"]), "S2")


if __name__ == "__main__":
    unittest.main()
