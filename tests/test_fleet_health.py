"""Read-only fleet binding contract tests using only temporary native configs."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from z0 import bindings, registry
from z0.__main__ import main

FLEET = Path(__file__).parent / "fixtures/bindings/fleet.toml"


def fixture_components():
    return {
        "archive": {
            "bindings": {"harnesses": list(bindings.HARNESSES),
                         "mcp": {"command": "archive", "args": ["mcp"]}}
        },
        "memory": {
            "bindings": {"harnesses": ["hermes"],
                         "hermes": {"memory_provider": "fixture_memory"}}
        },
        "tencentdb-memory": {
            "bindings": {"harnesses": ["hermes"],
                         "hermes": {"memory_provider": "memory_tencentdb"}},
            "service": {"unit": "tencentdb-memory.service"},
        },
        "z0intelligence": {
            "bindings": {"harnesses": ["hermes"],
                         "hermes": {"mcp": {
                             "command": "${Z0INT_PYTHON}",
                             "args": ["-m", "z0int.intelligence_mcp"],
                             "env": {"Z0INT_HARNESS": "hermes", "Z0INT_SHARED_ONLY": "1"}}}}
        },
        "graphrag": {"bindings": {"harnesses": []}},
    }


class FleetBindingHealthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.enterContext(patch.object(Path, "home", return_value=self.home))
        self.enterContext(patch.object(bindings.socket, "gethostname", return_value="groot"))
        self.enterContext(patch.object(registry, "components", return_value=fixture_components()))
        self.enterContext(patch.object(registry, "load_workspace", return_value={}))
        self.enterContext(patch.dict(os.environ, {
            "Z0_HOME": str(self.home / ".z0"),
            "Z0INT_PYTHON": "/opt/z0int/bin/python",
        }))
        self.clean = self.home / ".hermes/profiles/clean/config.yaml"
        self.clean.parent.mkdir(parents=True)
        self.clean.write_text(
            "mcp_servers:\n"
            "  ctx: {command: ctx}\n"
            "  noop: {command: noop}\n"
            "  unmanaged: {command: vendor}\n"
            "memory: {provider: null, max_tokens: 4096}\n",
            encoding="utf-8",
        )

    def write_fleet(self, selection='["tencentdb-memory", "z0intelligence"]'):
        path = self.home / "fleet.toml"
        path.write_text(
            'schema = 1\n'
            '[hosts.desktop]\nmatch_hostnames = ["groot", "0"]\n'
            '[hosts.desktop.z0_components.harnesses.hermes.profiles.clean]\n'
            f'components = {selection}\n'
            '[hosts.phone]\nmatch_hostnames = ["omarchy-phone"]\n',
            encoding="utf-8",
        )
        return path

    def invoke(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(args)
        return status, output.getvalue()

    def doctor(self, path, *extra):
        return self.invoke([
            "doctor", "--bindings", "--json", "--harness", "hermes",
            "--harness-profile", "clean", "--host-profile", str(path), *extra,
        ])

    def healthy_config(self):
        self.clean.write_text(
            "mcp_servers:\n"
            "  ctx: {command: ctx}\n"
            "  noop: {command: noop}\n"
            "  unmanaged: {command: vendor}\n"
            "  z0intelligence:\n"
            "    command: /opt/z0int/bin/python\n"
            "    args: [-m, z0int.intelligence_mcp]\n"
            '    env: {Z0INT_HARNESS: hermes, Z0INT_SHARED_ONLY: "1"}\n'
            "memory: {provider: memory_tencentdb, max_tokens: 4096}\n",
            encoding="utf-8",
        )

    def test_exact_logical_id_hostname_alias_and_no_cross_host_fallback(self):
        intent = bindings.Intent(host="groot", host_profile=str(FLEET))
        self.assertEqual(intent.logical_host, "desktop")
        self.assertEqual(bindings.Intent(host="desktop", host_profile=str(FLEET)).logical_host, "desktop")
        self.assertEqual(bindings.Intent(host="mbp", host_profile=str(FLEET)).logical_host, "mbp")
        self.assertIsNone(bindings.Intent(host="omarchy-phone", host_profile=str(FLEET)).desired(
            bindings.Target("hermes", "clean", self.clean)))
        with self.assertRaisesRegex(ValueError, "no entry"):
            bindings.Intent(host="unlisted", host_profile=str(FLEET))

    def test_ambiguous_alias_rejected_even_with_absent_components(self):
        path = self.home / "ambiguous.toml"
        path.write_text(
            '[hosts.desktop]\nmatch_hostnames = ["groot"]\n'
            '[hosts.other]\nmatch_hostnames = ["groot"]\n'
        )
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            bindings.Intent(host="groot", host_profile=str(path))
        # Exact logical ids take priority over aliases.
        self.assertEqual(bindings.Intent(host="desktop", host_profile=str(path)).logical_host,
                         "desktop")

    def test_global_harness_per_profile_precedence_and_empty(self):
        intent = bindings.Intent(host="groot", host_profile=str(FLEET))
        target = lambda harness, profile: bindings.Target(harness, profile, self.clean)
        self.assertEqual(intent.desired(target("hermes", "clean")), ["archive", "memory"])
        self.assertEqual(intent.desired(target("hermes", "other")), ["memory"])
        self.assertEqual(intent.desired(target("claude", "global")), ["archive"])
        self.assertEqual(intent.desired(target("codex", "global")), [])
        self.assertEqual(intent.desired(target("hermes", "empty")), [])
        self.assertEqual(bindings.Intent(host="mbp", host_profile=str(FLEET)).desired(
            target("hermes", "clean")), [])

    def test_missing_table_is_unknown_not_workspace_or_observation(self):
        intent = bindings.Intent(host="omarchy-phone", host_profile=str(FLEET))
        self.assertEqual(intent.spec, {})
        self.assertIsNone(intent.desired(bindings.Target("hermes", "clean", self.clean)))
        with patch.object(bindings, "service_state", return_value="active"):
            result = bindings.observe(bindings.Target("hermes", "clean", self.clean),
                                      None, fixture_components(), {})
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(any(f["status"] == "DRIFT" for f in result["findings"]))

    def test_yaml_remains_supported_and_invalid_fleet_fails_closed(self):
        source = self.home / "legacy.yaml"
        source.write_text('hosts:\n  groot:\n    components: [archive]\n')
        self.assertEqual(bindings.Intent(host="groot", host_profile=str(source)).desired(
            bindings.Target("omp", "global", self.clean)), ["archive"])
        source.write_text('components: []\n')
        self.assertEqual(bindings.Intent(host="groot", host_profile=str(source)).desired(
            bindings.Target("omp", "global", self.clean)), [])
        invalid = self.home / "invalid.toml"
        for value in ('[hosts.desktop]\nmatch_hostnames = "groot"\n',
                      '[hosts.desktop.z0_components]\ncomponents = ["missing"]\n',
                      '[hosts.desktop.z0_components.harnesses.claude.profiles.test]\ncomponents = []\n',
                      '[hosts.desktop.z0_components.harnesses.hermes.profiles.".."]\ncomponents = []\n',
                      '[hosts.desktop.z0_components]\ncomponents = "archive"\n'):
            invalid.write_text(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                bindings.Intent(host="desktop", host_profile=str(invalid))

    def test_match_is_read_only_and_preserves_unmanaged_servers(self):
        self.healthy_config()
        before = self.clean.read_bytes()
        path = self.write_fleet()
        with patch.object(bindings, "service_state", return_value="active"):
            code, stdout = self.doctor(path)
        result = json.loads(stdout)
        self.assertEqual(code, 0)
        self.assertEqual(result["kind"], "binding-observation")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["logical_host"], "desktop")
        self.assertEqual(len(result["configs"]), 1)
        self.assertIsInstance(result["findings"], list)
        self.assertTrue(all(f["status"] == "INFO" for f in result["findings"]))
        config = result["configs"][0]
        self.assertEqual(config["status"], "MATCH")
        self.assertEqual(config["desired"], ["tencentdb-memory", "z0intelligence"])
        self.assertTrue({"ctx", "noop", "unmanaged"} <= set(config["bound"]))
        self.assertEqual(self.clean.read_bytes(), before)
        receipt = Path(result["receipt"])
        self.assertEqual(json.loads(receipt.read_text()), result)
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.home.rglob("*.z0-backup-*")))
        self.assertNotIn("Configured does not mean", stdout)
        self.assertNotIn("stage", result)
        self.assertNotIn("execution", result)

    def test_requested_missing_disabled_mismatch_and_service_inactive_are_drift(self):
        path = self.write_fleet()
        with patch.object(bindings, "service_state", return_value="active"):
            code, stdout = self.doctor(path)
        self.assertEqual(code, 1)
        record = json.loads(stdout)["configs"][0]
        self.assertEqual(record["status"], "DRIFT")
        self.assertTrue(any(f["status"] == "DRIFT" for f in record["findings"]))
        self.healthy_config()
        self.clean.write_text(self.clean.read_text().replace(
            "command: /opt/z0int/bin/python", "command: incorrect"))
        with patch.object(bindings, "service_state", return_value="active"):
            code, stdout = self.doctor(path)
        self.assertEqual(code, 1)
        self.assertIn("binding-mismatch", [f["kind"] for f in json.loads(stdout)["configs"][0]["findings"]])
        self.healthy_config()
        self.clean.write_text(self.clean.read_text().replace(
            "    command: /opt/z0int/bin/python",
            "    enabled: false\n    command: /opt/z0int/bin/python"))
        with patch.object(bindings, "service_state", return_value="active"):
            code, stdout = self.doctor(path)
        self.assertEqual(code, 1)
        self.assertIn("missing-desired-component",
                      [f["kind"] for f in json.loads(stdout)["configs"][0]["findings"]])
        self.healthy_config()
        with patch.object(bindings, "service_state", return_value="inactive"):
            code, stdout = self.doctor(path)
        self.assertEqual(code, 1)
        self.assertIn("bound-but-service-not-running",
                      [f["kind"] for f in json.loads(stdout)["configs"][0]["findings"]])

    def test_unobservable_service_and_unbound_recipe_do_not_claim_match(self):
        path = self.write_fleet()
        self.healthy_config()
        with patch.object(bindings, "service_state", return_value="unknown"):
            code, stdout = self.doctor(path)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["status"], "UNKNOWN")
        with patch.dict(os.environ, {"Z0INT_PYTHON": ""}):
            code, stdout = self.doctor(path)
        # Empty expansion is not a runnable recipe; it must never be green.
        self.assertNotEqual(json.loads(stdout)["status"], "MATCH")
        path = self.write_fleet('["graphrag"]')
        code, stdout = self.doctor(path)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["status"], "UNKNOWN")
        self.assertIn("binding-not-observable",
                      [f["kind"] for f in json.loads(stdout)["configs"][0]["findings"]])

    def test_explicit_empty_means_none_unmanaged_is_informational(self):
        path = self.write_fleet("[]")
        code, stdout = self.doctor(path)
        result = json.loads(stdout)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "MATCH")
        record = result["configs"][0]
        self.assertEqual(record["desired"], [])
        self.assertIn("unmanaged", record["bound"])
        self.assertTrue(all(f["status"] == "INFO" for f in record["findings"]))

    def test_unreadable_config_and_bad_host_are_json_errors(self):
        path = self.write_fleet()
        self.clean.write_text('token: secret\nmcp_servers: [not-a-mapping]\n')
        code, stdout = self.doctor(path)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout)["configs"][0]["status"], "ERROR")
        self.assertNotIn("secret", stdout)
        code, stdout = self.doctor(path, "--host", "desktop")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["status"], "ERROR")
        self.assertNotIn("Binding observation:", stdout)

    def test_exclusive_receipt_and_missing_profile_are_safe(self):
        path = self.write_fleet()
        receipt = self.home / "one-receipt.json"
        code, stdout = self.doctor(path, "--receipt", str(receipt))
        self.assertEqual(code, 1)
        before = receipt.read_bytes()
        code, stdout = self.doctor(path, "--receipt", str(receipt))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["status"], "ERROR")
        self.assertEqual(receipt.read_bytes(), before)
        self.assertFalse(list(self.home.rglob("*.z0-backup-*")))
        self.clean.unlink()
        code, stdout = self.doctor(path)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout)["configs"][0]["status"], "DRIFT")
        self.assertFalse(self.clean.exists())

    def test_plan_preserves_ctx_noop_unmanaged_and_memory_fields(self):
        path = self.write_fleet()
        intent = bindings.Intent(host="groot", host_profile=str(path))
        desired = intent.desired(bindings.Target("hermes", "clean", self.clean))
        before = self.clean.read_bytes()
        plan = bindings.make_plan(bindings.Target("hermes", "clean", self.clean),
                                  desired, fixture_components())
        self.assertTrue(plan.changed)
        self.assertIn("ctx:", plan.rendered)
        self.assertIn("noop:", plan.rendered)
        self.assertIn("unmanaged:", plan.rendered)
        self.assertIn("max_tokens: 4096", plan.rendered)
        self.assertIn("provider: memory_tencentdb", plan.rendered)
        self.assertIn("z0intelligence:", plan.rendered)
        self.assertNotIn("Z0INT_PYTHON", plan.rendered)
        self.assertEqual(self.clean.read_bytes(), before)

    def test_registry_recipe_source_and_graphrag_block(self):
        # Exercise committed registry, not a stubbed test definition.
        registered = registry._load("components.yaml")["components"]
        z0int = registered["z0intelligence"]["bindings"]
        self.assertEqual(z0int["harnesses"], ["hermes", "claude", "codex"])
        for harness in z0int["harnesses"]:
            native = bindings.recipe(registered["z0intelligence"], harness)["mcp"]
            self.assertEqual(native["command"], "${Z0INT_PYTHON}")
            self.assertEqual(native["args"], ["-m", "z0int.intelligence_mcp"])
            self.assertNotIn("url", native)
        self.assertEqual(registered["graphrag"]["bindings"]["harnesses"], [])


if __name__ == "__main__":
    unittest.main()
