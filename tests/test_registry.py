"""Local, dependency-light registry contract tests; no services or network."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from z0 import generate, registry


class ComponentValidationTests(unittest.TestCase):
    def setUp(self):
        # Deliberately a small injected authority, not a copied AODL catalog.
        self.ids = {"hermes", "test-harness"}
        self.component = {
            "kind": "memory-source",
            "status": "experimental",
            "bindings": {
                "mcp": {"command": "example-mcp", "args": ["--root", "${ROOT}"],
                        "env": {"TOKEN": "${EXAMPLE_TOKEN}"}},
                "harnesses": ["hermes"],
                "hermes": {"memory_provider": None},
            },
            "evidence_source_for": ["z0intelligence.context-packet"],
        }

    def validate(self, component=None):
        registry.validate_components(
            {"example": self.component if component is None else component},
            harness_ids=self.ids,
        )

    def test_optional_bindings_and_new_kinds(self):
        for kind in ("memory-source", "service", "worker-coordinator", "sensor"):
            with self.subTest(kind=kind):
                self.validate({"kind": kind, "status": "idea"})

    def test_valid_stdio_provider_and_remote_bindings(self):
        self.validate()
        self.component["bindings"]["hermes"]["memory_provider"] = "memory_example"
        self.validate()
        self.component["bindings"]["mcp"] = {
            "url": "http://127.0.0.1:1234/mcp", "headers": {"Authorization": "${TOKEN}"}
        }
        self.validate()

    def test_authoritative_ids_not_local_harness_rows(self):
        self.component["bindings"]["harnesses"] = ["test-harness"]
        self.component["bindings"].pop("hermes")
        self.component["bindings"]["test-harness"] = {"native_setting": True}
        with patch.object(registry, "harnesses", side_effect=AssertionError("local catalog used")):
            self.validate()

    def test_unknown_aodl_id_fails_closed(self):
        self.component["bindings"]["harnesses"] = ["claude-code"]
        with self.assertRaisesRegex(ValueError, "unknown AODL"):
            self.validate()

    def test_invalid_binding_shapes(self):
        variants = [None, [], {"harnesses": "hermes"}, {"harnesses": ["hermes", "hermes"]},
                    {"harnesses": [None]}, {"harnesses": [""]},
                    {"harnesses": ["hermes"], "hermes": None},
                    {"harnesses": [], "hermes": {}},
                    {"harnesses": ["hermes"], "hermes": {"memory_provider": False}},
                    {"harnesses": ["hermes"], "hermes": {"memory_provider": ""}},
                    {"harnesses": [], "observed": {"running": True}}]
        for bindings in variants:
            with self.subTest(bindings=bindings), self.assertRaises(ValueError):
                self.validate({"kind": "service", "status": "experimental", "bindings": bindings})

    def test_invalid_mcp_definitions(self):
        variants = [None, [], {}, {"command": ""}, {"command": False},
                    {"command": "x", "url": "http://localhost"},
                    {"url": ""}, {"command": "x", "args": "--flag"},
                    {"command": "x", "args": [1]}, {"command": "x", "env": {"X": 1}},
                    {"command": "x", "env": []}, {"command": "x", "env": {"": "x"}},
                    {"url": "http://localhost", "args": []},
                    {"url": "http://localhost", "env": {}},
                    {"command": "x", "headers": {}}, {"url": "http://localhost", "headers": {"X": 1}},
                    {"command": "x", "unexpected": True}]
        for mcp in variants:
            with self.subTest(mcp=mcp), self.assertRaises(ValueError):
                component = copy.deepcopy(self.component)
                component["bindings"]["mcp"] = mcp
                self.validate(component)

    def test_harness_mcp_override_is_validated(self):
        self.component["bindings"]["hermes"]["mcp"] = {"command": "native-mcp"}
        self.validate()
        self.component["bindings"]["hermes"]["mcp"] = {"args": []}
        with self.assertRaises(ValueError):
            self.validate()

    def test_invalid_evidence_dependencies(self):
        for targets in (None, "context", [""], ["context", "context"], [False]):
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                component = copy.deepcopy(self.component)
                component["evidence_source_for"] = targets
                self.validate(component)

    def test_invalid_component_vocabulary(self):
        for field, value in (("kind", "typo"), ("status", "running"), ("execution", "verified")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                component = copy.deepcopy(self.component)
                component[field] = value
                self.validate(component)

    def test_observations_require_dated_provenance(self):
        valid = {"at": "2026-10-22", "host": "test-host", "summary": "Built, unbound.",
                 "evidence": ["README.md"]}
        self.component["observed"] = valid
        self.validate()
        for value in (None, {}, {**valid, "at": None}, {**valid, "host": ""},
                      {**valid, "summary": False}, {**valid, "evidence": []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.component["observed"] = value
                self.validate()

    def test_unknown_structured_vocabulary_fails_cleanly(self):
        for field in ("kind", "status", "execution"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate({**self.component, field: []})
        with self.assertRaises(ValueError):
            registry.validate_components([], harness_ids=self.ids)

    def test_catalog_loaded_only_when_bindings_need_it(self):
        with patch.object(registry, "aodl_harness_ids", return_value=self.ids) as load:
            registry.validate_components({"x": {"kind": "sensor", "status": "idea"}})
            load.assert_not_called()
            registry.validate_components({"x": self.component, "y": self.component})
            load.assert_called_once_with()

    def test_local_external_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps({"supported": ["hermes", "test-harness"]}))
            with patch.dict("os.environ", {"Z0_AODL_CATALOG": str(path)}):
                self.assertEqual(registry.aodl_harness_ids(), self.ids)
            for supported in (None, [], [1], [""], ["hermes", "hermes"]):
                path.write_text(json.dumps({"supported": supported}))
                with self.subTest(supported=supported), self.assertRaises(ValueError):
                    registry.aodl_harness_ids(path)

    def test_remote_catalog_uses_declared_authority(self):
        with patch.object(registry, "harness_catalog", return_value={
            "authority": "example/aodl", "ref": "exact-ref", "path": "harnesses/catalog.json"
        }), patch.object(registry, "urlopen") as fetch:
            fetch.return_value.__enter__.return_value.read.return_value = b'{"supported":["external"]}'
            self.assertEqual(registry.aodl_harness_ids(), {"external"})
            fetch.assert_called_once_with(
                "https://raw.githubusercontent.com/example/aodl/exact-ref/harnesses/catalog.json", timeout=15
            )

    def test_bindings_render_as_declarations_not_live_status(self):
        self.component["observed"] = {
            "at": "2026-10-22", "host": "test-host", "summary": "Built, unbound.",
            "evidence": ["README.md"],
        }
        with patch.object(registry, "components", return_value={"example": self.component}):
            text = generate.bindings_md()
        self.assertIn("Declarative bindings", text)
        self.assertIn("2026-10-22, test-host", text)
        self.assertIn("Built, unbound.", text)
        self.assertIn("README.md", text)
        self.assertIn("not host enablement", text)

    def test_schema_vocabulary_matches_validator(self):
        schema = json.loads((registry.ROOT / "schemas/component.schema.json").read_text())
        properties = schema["properties"]
        self.assertEqual(set(properties["kind"]["enum"]), registry.COMPONENT_KINDS)
        for field in ("status", "execution"):
            self.assertEqual(set(properties[field]["enum"]), set(registry.maturity()[field]))
        self.assertIn("observed", properties)
        self.assertIn("bindings", properties)

    def test_generation_indexes_fresh_reference_docs_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(generate, "ROOT", root), \
                 patch.object(generate, "GENERATED", root / "generated"), \
                 patch.object(generate, "DOCS_GEN", root / "docs/reference"):
                outputs = generate.write_all()
                first = {path: path.read_bytes() for path in outputs}
                rows = [json.loads(line) for line in
                        (root / "generated/docs-index.jsonl").read_text().splitlines()]
                ownership = next(row for row in rows if row["path"] == "docs/reference/ownership.md")
                self.assertIn("z0bridge", ownership["components"])
                generate.write_all()
                self.assertEqual(first, {path: path.read_bytes() for path in outputs})

    def test_current_registry_preserves_unqualified_and_disabled_states(self):
        comps = registry.components()
        expected = {
            "z0live", "z0bridge", "oss-factory", "agentsview", "ctx",
            "tencentdb-memory", "qmd", "graphrag", "supermemory", "memento",
        }
        self.assertTrue(expected <= comps.keys())
        self.assertEqual(comps["oss-factory"]["kind"], "worker-coordinator")
        self.assertEqual(comps["memento"]["kind"], "sensor")
        self.assertEqual(comps["memento"]["status"], "idea")
        self.assertNotIn("execution", comps["memento"])
        for cid in expected:
            self.assertEqual(comps[cid]["profiles"], [])
            self.assertTrue(comps[cid]["observed"]["evidence"])
        for cid in ("graphrag", "supermemory", "memento"):
            self.assertEqual(comps[cid]["bindings"]["harnesses"], [])
            self.assertNotIn("execution", comps[cid])
        self.assertNotIn("mcp", comps["graphrag"]["bindings"])
        self.assertIn("credential", comps["supermemory"]["summary"])
        self.assertEqual(
            comps["tencentdb-memory"]["bindings"]["hermes"]["memory_provider"], "memory_tencentdb"
        )


if __name__ == "__main__":
    unittest.main()
