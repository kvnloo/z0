"""schemas/overlay.schema.json mirrors kvnloo/z0-hosts-template schema/host.schema.json.

Stdlib structural checks: closed objects, the component set, and no key that could hold an
address. When a template checkout is found (Z0_HOSTS_TEMPLATE or a sibling
../z0-hosts-template), the two schemas must agree on everything but $id and description.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "overlay.schema.json").read_text())
COMPONENTS = ["host", "dash", "z0int", "z0evals", "onboard", "files", "devices"]
ADDRESS = re.compile(r"(?i)(^|_)(ip|ip4|ip6|ipv4|ipv6|addr|address|cidr|tailnet|magicdns|dns_name|fqdn)(_|$)")


def objects(node, where="$"):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield where, node
        for key, sub in node.items():
            yield from objects(sub, f"{where}.{key}")
    elif isinstance(node, list):
        for i, sub in enumerate(node):
            yield from objects(sub, f"{where}[{i}]")


class OverlaySchema(unittest.TestCase):
    def test_header(self):
        self.assertEqual(SCHEMA["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertTrue(SCHEMA["$id"].endswith("/schemas/overlay.schema.json"))

    def test_components_are_the_closed_set(self):
        self.assertFalse(SCHEMA["additionalProperties"])
        self.assertEqual(list(SCHEMA["properties"]), COMPONENTS)

    def test_every_object_is_closed_or_key_constrained(self):
        for where, obj in objects(SCHEMA):
            with self.subTest(where=where):
                closed = obj.get("additionalProperties") is False
                keyed = "propertyNames" in obj
                self.assertTrue(closed or keyed, "open object without propertyNames")

    def test_no_address_shaped_property(self):
        for where, obj in objects(SCHEMA):
            for key in obj.get("properties", {}):
                self.assertIsNone(ADDRESS.search(key), f"{where}.{key}")

    def test_hostnames_cannot_hold_a_dot(self):
        pattern = SCHEMA["$defs"]["hostname"]["pattern"]
        self.assertIsNone(re.search(pattern, "laptop.example.ts.net"))
        self.assertIsNotNone(re.search(pattern, "laptop"))

    def test_matches_template_when_present(self):
        candidates = [os.environ.get("Z0_HOSTS_TEMPLATE"), str(ROOT.parent / "z0-hosts-template")]
        path = next((Path(c) / "schema" / "host.schema.json" for c in candidates
                     if c and (Path(c) / "schema" / "host.schema.json").is_file()), None)
        if path is None:
            self.skipTest("no z0-hosts-template checkout")
        template = json.loads(path.read_text())
        strip = lambda s: {k: v for k, v in s.items() if k not in ("$id", "description")}
        self.assertEqual(strip(SCHEMA), strip(template))


if __name__ == "__main__":
    unittest.main()
