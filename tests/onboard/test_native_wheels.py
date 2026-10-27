"""The z0intelligence install needs manylinux_2_38 wheels (fff-search ships no sdist-free
build for older glibc): on glibc < 2.38 the step is unavailable with a stated condition
instead of failing inside pip (found on debian:12 in CI)."""
from __future__ import annotations

import unittest

from tests.onboard import support


class NativeWheels(unittest.TestCase):
    def test_derived_fact(self):
        from z0.onboard.plan import facts_of
        for os_block, want in (({"os": "linux", "libc": "glibc", "libc_version": "2.36"}, False),
                               ({"os": "linux", "libc": "glibc", "libc_version": "2.38"}, True),
                               ({"os": "linux", "libc": "glibc", "libc_version": "2.44"}, True),
                               ({"os": "linux", "libc": "glibc", "libc_version": ""}, False),
                               ({"os": "linux", "libc": "musl"}, False),
                               ({"os": "darwin", "libc": "darwin"}, True)):
            with self.subTest(os=os_block):
                self.assertIs(facts_of({"os": os_block}, "auto", None)["derived"]["manylinux_2_38"], want)

    def test_old_glibc_makes_install_unavailable(self):
        support.require_yaml(self)
        from z0.onboard import plan as p
        host = support.fixture("laptop-cpu-15g")
        host["os"]["libc_version"] = "2.36"
        state = {e["step"]["id"]: e["state"] for e in
                 p.plan(host, support.snapshot(), with_ids=["z0intelligence"], grants=support.ALL_BUNDLES)["steps"]}
        self.assertEqual(state["z0intelligence.install"]["status"], "unavailable")
        self.assertIn("manylinux_2_38", state["z0intelligence.install"]["reason"])

    def test_libc_version_parse(self):
        from z0.onboard.detect import osinfo

        class R:
            def __init__(self, out):
                self.out, self.err, self.ok = out, "", True

        class Ctx:
            def __init__(self, out):
                self._out = out

            def run(self, argv):
                return R(self._out)

        self.assertEqual(osinfo._libc_version(Ctx("ldd (Debian GLIBC 2.36-9+deb12u7) 2.36\n"), "linux"), "2.36")
        self.assertEqual(osinfo._libc_version(Ctx("ldd (GNU libc) 2.44\n"), "linux"), "2.44")
        self.assertEqual(osinfo._libc_version(Ctx("musl libc (x86_64)\n"), "linux"), "")
        self.assertEqual(osinfo._libc_version(Ctx(""), "darwin"), "")


if __name__ == "__main__":
    unittest.main()
