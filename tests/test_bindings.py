"""Fixture-only native config tests. Never read or write the operator's home."""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from z0 import bindings, registry
from z0.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures" / "bindings"


def components():
    return {
        "archive": {"bindings": {"harnesses": list(bindings.HARNESSES),
                                 "mcp": {"command": "archive", "args": ["mcp"],
                                         "env": {"ACCESS_TOKEN": "${ARCHIVE_TOKEN}"}}},
                    "service": {"unit": "archive.service"}},
        "memory": {"bindings": {"harnesses": ["hermes"],
                                "hermes": {"memory_provider": "fixture_memory"}},
                   "service": {"unit": "memory.service"}},
        "native-only": {"bindings": {"harnesses": ["omp"], "omp": {"extension": "native-only"}}},
        "no-binding": {},
    }


class NativeBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.comps = components()
        self.comps["unbound"] = {"bindings": {"harnesses": []}}
        self.enterContext(patch.object(Path, "home", return_value=self.home))
        self.enterContext(patch.object(registry, "components", return_value=self.comps))
        self.enterContext(patch.object(registry, "load_workspace", return_value={}))
        self.enterContext(patch.dict(os.environ, {"ARCHIVE_TOKEN": "desired-secret",
                                                "Z0_HOME": str(self.home / ".z0")}))
        self.targets = {target.harness: target for target in bindings.targets(self.home)}
        for harness, target in self.targets.items():
            extension = {"hermes": "yaml", "codex": "toml"}.get(harness, "json")
            target.path.parent.mkdir(parents=True, exist_ok=True)
            target.path.write_text((FIXTURES / f"{harness}.{extension}").read_text())

    def invoke(self, argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(argv)
        return status, output.getvalue()

    def test_each_native_format_preserves_unowned_keys_and_backup(self):
        for harness, target in self.targets.items():
            with self.subTest(harness=harness):
                original, data = bindings.read_config(target)
                before = bindings.plain(data)
                desired = ["archive", "memory"] if harness == "hermes" else ["archive"]
                plan = bindings.make_plan(target, desired, self.comps, strict=True)
                self.assertTrue(plan.changed)
                self.assertIn("--- ", plan.diff)
                self.assertIn("<set>", plan.diff)
                self.assertNotIn("fixture-secret", plan.diff)
                self.assertNotIn("desired-secret", plan.diff)
                self.assertNotIn("unrelated-secret", plan.diff)
                backup = bindings.write_plan(plan)
                self.assertEqual(backup.read_text(), original)
                self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
                _, updated = bindings.read_config(target)
                key = bindings.MCP_KEYS[harness]
                self.assertEqual(bindings.plain(updated[key]["unrelated"]), before[key]["unrelated"])
                self.assertEqual(bindings.plain(updated[key]["archive"]),
                                 bindings.native_mcp(bindings.expand(self.comps["archive"]["bindings"]["mcp"]), harness))
                for name in before.keys() - {key, "memory"}:
                    self.assertEqual(bindings.plain(updated[name]), before[name])
                if harness == "hermes":
                    self.assertEqual(updated["memory"]["provider"], "fixture_memory")
                    self.assertEqual(updated["memory"]["max_tokens"], 4096)
                if harness in {"hermes", "codex"}:
                    self.assertIn("# Keep this host setting and comment.", target.path.read_text())
                self.assertFalse(bindings.make_plan(target, desired, self.comps).changed)

    def test_dry_run_is_repeatable_and_writes_nothing(self):
        before = {target.path: target.path.read_bytes() for target in self.targets.values()}
        args = ["apply", "--dry-run", "--components", "archive"]
        first = self.invoke(args)
        self.assertEqual(first[0], 0)
        self.assertEqual(self.invoke(args), first)
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertFalse(list(self.home.rglob("*.z0-backup-*")))
        self.assertFalse((self.home / ".z0").exists())
        for secret in ("fixture-secret", "desired-secret", "unrelated-secret"):
            self.assertNotIn(secret, first[1])

    def test_apply_refused_without_yes_before_reading_config(self):
        with patch.object(bindings, "read_config", side_effect=AssertionError("config read")):
            status, output = self.invoke(["apply", "--apply", "--components", "archive"])
        self.assertEqual(status, 2)
        self.assertIn("--apply requires --yes", output)
        self.assertFalse(list(self.home.rglob("*.z0-backup-*")))

    def test_apply_with_yes_only_writes_selected_harness(self):
        other = self.targets["omp"].path.read_bytes()
        status, output = self.invoke(["apply", "--apply", "--yes", "--components", "archive",
                                      "--harness", "codex"])
        self.assertEqual(status, 0, output)
        self.assertEqual(self.targets["omp"].path.read_bytes(), other)
        self.assertEqual(len(list(self.targets["codex"].path.parent.glob("*.z0-backup-*"))), 1)
        status, output = self.invoke(["apply", "--dry-run", "--components", "archive", "--harness", "codex"])
        self.assertEqual(status, 0)
        self.assertIn("No changes.", output)

    def test_native_remote_transport_and_header_keys(self):
        mcp = {"url": "https://example.invalid/mcp", "headers": {"Authorization": "remote-secret"}}
        self.comps["archive"]["bindings"]["mcp"] = mcp
        for harness, target in self.targets.items():
            with self.subTest(harness=harness):
                plan = bindings.make_plan(target, ["archive"], self.comps)
                bindings.write_plan(plan)
                _, data = bindings.read_config(target)
                server = data[bindings.MCP_KEYS[harness]]["archive"]
                self.assertEqual(server["url"], mcp["url"])
                self.assertNotIn("command", server)
                self.assertEqual(server["http_headers" if harness == "codex" else "headers"]["Authorization"], "remote-secret")
                if harness in {"claude", "omp"}:
                    self.assertEqual(server["type"], "http")
                self.assertNotIn("remote-secret", plan.diff)

    def test_per_harness_recipe_overrides_shared_recipe(self):
        self.comps["archive"]["bindings"]["codex"] = {"mcp": {"command": "codex-archive"}}
        plan = bindings.make_plan(self.targets["codex"], ["archive"], self.comps)
        self.assertIn("codex-archive", plan.diff)
        self.assertEqual(bindings.recipe(self.comps["archive"], "codex"), {"mcp": {"command": "codex-archive"}})

    def test_secret_only_change_is_not_mistaken_for_no_change(self):
        target = self.targets["hermes"]
        first = bindings.make_plan(target, ["archive"], self.comps)
        bindings.write_plan(first)
        with patch.dict(os.environ, {"ARCHIVE_TOKEN": "replacement-secret"}):
            plan = bindings.make_plan(target, ["archive"], self.comps)
        self.assertTrue(plan.changed)
        self.assertIn("differ beneath <set>", plan.diff)
        self.assertNotIn("replacement-secret", plan.diff)

    def test_secret_redaction_masks_arguments_and_url_credentials(self):
        masked = bindings.mask({"env": {"TOKEN": "env-secret"},
                                "args": ["--password", "arg-secret"],
                                "headers": {"Authorization": "header-secret"},
                                "url": "https://user:password@example.invalid/mcp?key=query-secret#fragment-secret"})
        text = json.dumps(masked)
        for secret in ("env-secret", "arg-secret", "header-secret", "password", "query-secret", "fragment-secret"):
            self.assertNotIn(secret, text)
        self.assertEqual(masked["env"]["TOKEN"], "<set>")

    def test_unset_variable_refuses_apply_before_any_write(self):
        with patch.dict(os.environ, {}, clear=True):
            status, output = self.invoke(["apply", "--apply", "--yes", "--components", "archive"])
        self.assertEqual(status, 2)
        self.assertIn("unset", output)
        self.assertFalse(list(self.home.rglob("*.z0-backup-*")))

    def test_bad_config_fails_preflight_without_secrets_or_writes(self):
        self.targets["omp"].path.write_text('{"secret": "do-not-print", invalid')
        status, output = self.invoke(["apply", "--apply", "--yes", "--components", "archive"])
        self.assertEqual(status, 2)
        self.assertNotIn("do-not-print", output)
        self.assertFalse(list(self.home.rglob("*.z0-backup-*")))

    def test_foreign_host_is_not_reported_as_this_host(self):
        status, output = self.invoke(["doctor", "--bindings", "--host", "not-this-host.invalid"])
        self.assertEqual(status, 2)
        self.assertIn("must name this host", output)
        self.assertFalse((self.home / ".z0").exists())

    def test_write_refused_if_file_changes_after_plan(self):
        target = self.targets["hermes"]
        plan = bindings.make_plan(target, ["archive"], self.comps)
        target.path.write_text("model: changed-by-user\n")
        with self.assertRaisesRegex(ValueError, "changed after planning"):
            bindings.write_plan(plan)
        self.assertEqual(target.path.read_text(), "model: changed-by-user\n")

    def test_symlink_write_refused(self):
        target = self.targets["hermes"]
        real = self.home / "linked-config.yaml"
        target.path.rename(real)
        target.path.symlink_to(real)
        status, output = self.invoke(["apply", "--apply", "--yes", "--components", "archive"])
        self.assertEqual(status, 2)
        self.assertIn("symlink", output)
        self.assertFalse(list(self.home.rglob("*.z0-backup-*")))

    def test_missing_new_config_created_only_on_explicit_apply(self):
        target = self.targets["codex"]
        target.path.unlink()
        plan = bindings.make_plan(target, ["archive"], self.comps)
        self.assertFalse(target.path.exists())
        self.assertTrue(plan.changed)
        self.assertIsNone(bindings.write_plan(plan))
        self.assertEqual(target.path.stat().st_mode & 0o777, 0o600)

    def test_conflicting_memory_providers_refuse_apply(self):
        self.comps["other-memory"] = copy.deepcopy(self.comps["memory"])
        self.comps["other-memory"]["bindings"]["hermes"]["memory_provider"] = "different_memory"
        status, output = self.invoke(["apply", "--apply", "--yes", "--components", "memory,other-memory"])
        self.assertEqual(status, 2)
        self.assertIn("conflicting", output)
        self.assertFalse(list(self.home.rglob("*.z0-backup-*")))

    def add_hermes_profile(self, name, text):
        path = self.home / ".hermes/profiles" / name / "config.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(text)
        return path

    def test_hermes_multi_profile_observation_and_profile_specific_intent(self):
        clean = self.add_hermes_profile("clean", "mcp_servers: {}\nmemory: {}\n")
        chief = self.add_hermes_profile("chiefstaff", "mcp_servers: {}\nmemory:\n  provider: fixture_memory\n")
        source = self.home / "host.yaml"
        source.write_text("components: [archive]\nharnesses:\n  hermes:\n    profiles:\n      clean:\n        components: []\n      chiefstaff:\n        components: [memory]\n")
        before = {path: path.read_bytes() for path in (clean, chief, self.targets["hermes"].path)}
        with patch.object(bindings, "service_state", return_value="inactive") as state:
            status, output = self.invoke(["doctor", "--bindings", "--harness", "hermes",
                                          "--host-profile", str(source)])
        self.assertEqual(status, 0, output)
        receipt = json.loads(next((self.home / ".z0/observations").glob("*.json")).read_text())
        records = {record["profile"]: record for record in receipt["configs"]}
        self.assertEqual(set(records), {"default", "clean", "chiefstaff"})
        self.assertEqual(records["clean"]["desired"], [])
        self.assertEqual(records["chiefstaff"]["desired"], ["memory"])
        self.assertTrue(any(finding["kind"] == "bound-but-service-not-running"
                            for finding in records["chiefstaff"]["findings"]))
        self.assertEqual(receipt["host"], socket.gethostname())
        self.assertEqual(receipt["registered_without_native_binding"], ["unbound"])
        self.assertIn("timestamp", receipt)
        self.assertTrue(all(record["mtime_ns"] is not None for record in records.values()))
        self.assertNotIn("execution", receipt)
        self.assertNotIn("stage", receipt)
        self.assertNotIn("fixture-secret", json.dumps(receipt))
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertIn("memory.service", [call.args[0] for call in state.call_args_list])

    def test_hermes_profile_selection_does_not_touch_other_profiles(self):
        clean = self.add_hermes_profile("clean", "mcp_servers: {}\n")
        other = self.add_hermes_profile("other", "mcp_servers: {}\n")
        original = other.read_text()
        root_original = self.targets["hermes"].path.read_bytes()
        status, output = self.invoke(["apply", "--apply", "--yes", "--harness", "hermes",
                                      "--harness-profile", "clean", "--components", "archive"])
        self.assertEqual(status, 0, output)
        self.assertIn("archive", clean.read_text())
        self.assertEqual(other.read_text(), original)
        self.assertEqual(self.targets["hermes"].path.read_bytes(), root_original)

    def test_doctor_all_drift_categories_and_no_implied_runtime_proof(self):
        # The unrelated server is deliberately absent from the registry.
        self.add_hermes_profile("empty", "mcp_servers: {}\n")
        with patch.object(bindings, "service_state", return_value="failed"):
            status, output = self.invoke(["doctor", "--bindings", "--components", "archive,memory"])
        self.assertEqual(status, 0, output)
        for kind in ("registered-but-unbound", "bound-but-unregistered", "bound-but-service-not-running",
                     "missing-desired-component", "binding-mismatch", "binding-not-observable"):
            self.assertIn(kind, output)
        self.assertIn("does not mean running or verified", output)
        self.assertIn("registered-but-unbound: unbound (no declared harness binding)", output)
        for secret in ("fixture-secret", "unrelated-secret", "desired-secret"):
            self.assertNotIn(secret, output)

    def test_doctor_unknown_desired_state_is_explicit(self):
        with patch.object(bindings, "service_state", return_value="active"):
            status, output = self.invoke(["doctor", "--bindings", "--harness", "hermes"])
        self.assertEqual(status, 0)
        self.assertIn("desired: unknown", output)
        self.assertNotIn("missing-desired-component", output)
        self.assertNotIn("bound-but-service-not-running", output)

    def test_receipt_cannot_overwrite_config_or_previous_receipt(self):
        path = self.targets["hermes"].path
        original = path.read_bytes()
        with patch.object(bindings, "service_state", return_value="active"):
            status, _ = self.invoke(["doctor", "--bindings", "--receipt", str(path)])
        self.assertEqual(status, 2)
        self.assertEqual(path.read_bytes(), original)

    def test_disabled_server_is_not_reported_as_bound(self):
        target = self.targets["hermes"]
        target.path.write_text("mcp_servers:\n  archive:\n    command: archive\n    enabled: false\n")
        record = bindings.observe(target, ["archive"], self.comps, {})
        self.assertNotIn("archive", record["bound"])
        self.assertIn("missing-desired-component", [finding["kind"] for finding in record["findings"]])

    def test_workspace_and_explicit_z0_profile_select_desired_components(self):
        with patch.object(registry, "load_workspace", return_value={"profile": "core"}), \
             patch.object(registry, "resolve_profile", return_value=["archive"]):
            intent = bindings.Intent(host=socket.gethostname())
            self.assertEqual(intent.desired(self.targets["omp"]), ["archive"])
        with patch.object(registry, "resolve_profile", return_value=["memory"]):
            intent = bindings.Intent(host=socket.gethostname(), profile="example")
            self.assertEqual(intent.desired(self.targets["hermes"]), ["memory"])

    def test_host_intent_uses_current_host_and_validates_all_selections(self):
        source = self.home / "host.yaml"
        source.write_text("hosts:\n  other-host:\n    components: [archive]\n")
        with self.assertRaisesRegex(ValueError, "no entry"):
            bindings.Intent(host=socket.gethostname(), host_profile=str(source))
        source.write_text("components: [unknown-component]\n")
        with self.assertRaisesRegex(ValueError, "unregistered"):
            bindings.Intent(host=socket.gethostname(), host_profile=str(source))

    def test_no_desired_state_cannot_apply(self):
        status, output = self.invoke(["apply", "--dry-run"])
        self.assertEqual(status, 2)
        self.assertIn("desired state is unknown", output)

    def test_systemctl_query_is_read_only_and_handles_missing_runtime(self):
        with patch.object(bindings.subprocess, "run") as run:
            run.return_value.stdout = "inactive\n"
            self.assertEqual(bindings.service_state("archive.service"), "inactive")
            self.assertEqual(run.call_args.args[0], ["systemctl", "--user", "is-active", "--", "archive.service"])
        with patch.object(bindings.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(bindings.service_state("archive.service"), "unknown")

    def test_null_provider_recipe_is_satisfied_without_claiming_a_bound_component(self):
        target = self.targets["hermes"]
        target.path.write_text("memory:\n  provider: null\n")
        self.comps["memory"]["bindings"]["hermes"]["memory_provider"] = None
        record = bindings.observe(target, ["memory"], self.comps, {})
        self.assertNotIn("memory", record["bound"])
        self.assertFalse(any(finding.get("component") == "memory" for finding in record["findings"]))

    def test_composite_recipe_requires_all_native_surfaces(self):
        target = self.targets["hermes"]
        self.comps["archive"]["bindings"]["hermes"] = {"memory_provider": "archive_memory"}
        record = bindings.observe(target, ["archive"], self.comps, {})
        self.assertIn("archive", record["bound"])
        self.assertTrue(any(finding["kind"] == "missing-desired-component" and finding["component"] == "archive"
                            for finding in record["findings"]))

    def test_yaml_aliases_do_not_extend_owned_keys(self):
        target = self.targets["hermes"]
        target.path.write_text(
            "memory: &memory_settings\n  provider: old_provider\n  limit: 100\n"
            "unrelated_memory: *memory_settings\n"
            "mcp_servers: &servers\n  unrelated:\n    command: keep-me\n"
            "unrelated_servers: *servers\n")
        plan = bindings.make_plan(target, ["archive", "memory"], self.comps)
        bindings.write_plan(plan)
        _, data = bindings.read_config(target)
        self.assertEqual(data["unrelated_memory"]["provider"], "old_provider")
        self.assertNotIn("archive", data["unrelated_servers"])
        self.assertEqual(data["memory"]["provider"], "fixture_memory")

    def test_declared_service_unit_contract(self):
        meta = {"kind": "service", "status": "experimental"}
        for unit in ("archive.service", "archive.socket", "archive.timer", "archive.target"):
            registry.validate_components({"archive": {**meta, "service": {"unit": unit}}})
        for service in (None, {}, {"unit": "--malicious"}, {"unit": "archive.service", "start": True},
                        {"unit": 123}, {"unit": "not a unit.service"}):
            with self.subTest(service=service), self.assertRaises(ValueError):
                registry.validate_components({"archive": {**meta, "service": service}})


if __name__ == "__main__":
    unittest.main()
