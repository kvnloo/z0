"""Origin mirrors (§6.2): `plan` proves or disproves each pin on origin without a checkout.

Every origin here is a local file:// repo in a temp dir: no network, no real host state.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.onboard import fakehost, support  # noqa: F401  (support puts lib/ on sys.path)

GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
MISSING = "0123456789abcdef0123456789abcdef01234567"


def git(*args, cwd) -> str:
    env = dict(GIT_ENV, PATH=os.environ.get("PATH", "/usr/bin:/bin"), HOME=str(cwd))
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


class Mirror(unittest.TestCase):
    def setUp(self):
        from z0.onboard import mirror
        self.mirror = mirror
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home, self.z0_home, self.origin = root / "home", root / "home/.z0", root / "origin"
        self.home.mkdir()
        self.origin.mkdir()
        git("init", "-q", cwd=self.origin)
        for name in ("a", "b"):
            (self.origin / name).write_text(name)
            git("add", name, cwd=self.origin)
            git("commit", "-qm", name, cwd=self.origin)
        self.pinned = git("rev-parse", "HEAD~1", cwd=self.origin)  # on origin, not a ref tip
        self.snap = {"components": {"components": {"x": {
            "repo": "kvnloo/x", "install": {"clone": "https://example.invalid/x.git", "ref": self.pinned},
            "onboard": {"revs": {"app": self.pinned, "bridge": MISSING}}}}}}
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.home)}
        self.urls = {"kvnloo/x": f"file://{self.origin}"}

    def tearDown(self):
        self.tmp.cleanup()

    def ensure(self, **kw):
        return self.mirror.ensure(self.snap, str(self.z0_home), self.env, urls=self.urls, **kw)

    def test_fetch_proves_and_disproves_pins(self):
        before = fakehost.tree_state(self.home)
        self.assertEqual(self.ensure(), {self.pinned: "yes", MISSING: "no"})
        mirror = self.z0_home / "cache/git/x.git"
        self.assertTrue((mirror / ".z0-owned").is_file())
        after = fakehost.tree_state(self.home)
        changed = {p for p in after if before.get(p) != after[p]}
        allowed = (str(self.z0_home / "cache/git"),)
        for path in changed:  # P0: plan writes only the mirror (and its parents)
            self.assertTrue(path.startswith(allowed) or path in (str(self.z0_home),
                                                                  str(self.z0_home / "cache")), path)
        self.assertEqual(git("--git-dir", str(mirror), "cat-file", "-t", self.pinned, cwd=self.home),
                         "commit")

    def test_a_pin_already_mirrored_is_not_fetched_again(self):
        self.ensure()
        calls = []

        def spy(argv, env, timeout):
            calls.append(argv)
            return self.mirror._run(argv, env, timeout)
        self.assertEqual(self.ensure(run=spy)[self.pinned], "yes")
        fetches = [c for c in calls if "fetch" in c and self.pinned in c]
        self.assertEqual(fetches, [])

    def test_unreachable_origin_is_unknown_not_no(self):
        self.urls = {"kvnloo/x": f"file://{self.origin}-gone"}
        self.assertEqual(self.ensure(), {self.pinned: "unknown", MISSING: "unknown"})

    def test_merge_records_only_a_definite_no(self):
        host = {"revs": {self.pinned: {"repo": "kvnloo/x", "on_origin": "yes", "evidence": "mirror",
                                       "flavour": "unknown"}}}
        self.mirror.merge(host, {self.pinned: "no", MISSING: "no"}, self.snap)
        self.assertEqual(host["revs"][self.pinned]["on_origin"], "yes")
        self.assertEqual(host["revs"][MISSING]["on_origin"], "no")
        self.assertEqual(host["revs"][MISSING]["evidence"], "mirror")


if __name__ == "__main__":
    unittest.main()
