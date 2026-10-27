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


class _MirrorBase(unittest.TestCase):
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


class Mirror(_MirrorBase):

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



@support.require_yaml
class MirrorSetups(_MirrorBase):
    """§2.6: zer0.repo.yaml `setup:` is read from the mirror at the pin (needs PyYAML)."""

    def _setup_origin(self, filtered: bool):
        (self.origin / "zer0.repo.yaml").write_text(
            "version: 1\nrepo: kvnloo/x\nid: x\nkind: research\narchitecture: {}\nsetup:\n"
            "  version: 1\n  steps:\n"
            "    - {id: x.check, component: x, kind: check, consent: {class: C0}, where: build,\n"
            "       argv: [python3, -c, pass]}\n"
            "    - {id: x.bad, component: x, kind: run, consent: {class: C0}, where: build,\n"
            "       argv: [make]}\n")
        git("add", "zer0.repo.yaml", cwd=self.origin)
        git("commit", "-qm", "setup", cwd=self.origin)
        if filtered:  # a blob-less mirror, like github.com serves it
            git("config", "uploadpack.allowFilter", "true", cwd=self.origin)
            git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=self.origin)
        pinned = git("rev-parse", "HEAD", cwd=self.origin)
        snap = support.snapshot()
        snap["components"]["components"] = {"x": {
            "repo": "kvnloo/x", "install": {"clone": "https://example.invalid/x.git", "ref": pinned},
            "onboard": {"steps": []}}}
        return snap, pinned

    def test_read_setups_reads_the_pin_from_the_mirror_only(self):
        """§2.6: the block at the pinned SHA, vetted; never a working tree."""
        snap, pinned = self._setup_origin(filtered=False)
        self.mirror.ensure(snap, str(self.z0_home), self.env, urls=self.urls)
        (self.origin / "zer0.repo.yaml").write_text("setup: {version: 1, steps: []}\n")  # tree drift
        setups = self.mirror.read_setups(snap, str(self.z0_home), self.env)
        entry = setups["x"]
        self.assertEqual((entry["repo"], entry["ref"]), ("kvnloo/x", pinned))
        self.assertEqual([s["id"] for s in entry["setup"]["steps"]], ["x.check"])
        self.assertTrue(any("x.bad" in e and "creates or probe" in e for e in entry["errors"]))
        self.assertRegex(entry["sha256"], "^[0-9a-f]{64}$")

    def test_read_setups_without_lazy_fetch_writes_nothing(self):
        """plan --stdout: a blob-less mirror is read as it is; no blob is fetched."""
        snap, _ = self._setup_origin(filtered=True)
        self.mirror.ensure(snap, str(self.z0_home), self.env, urls=self.urls)
        before = fakehost.tree_state(self.home)
        entry = self.mirror.read_setups(snap, str(self.z0_home), self.env, lazy=False)["x"]
        self.assertEqual(fakehost.tree_state(self.home), before)
        self.assertNotIn("setup", entry)  # the blob is not in the mirror: an error, never a guess
        self.assertIn("could not read zer0.repo.yaml", entry["errors"][0])
        # plan (with its fetch) brings the one blob into the mirror and reads it.
        entry = self.mirror.read_setups(snap, str(self.z0_home), self.env)["x"]
        self.assertEqual([s["id"] for s in entry["setup"]["steps"]], ["x.check"])

    def test_read_setups_skips_a_pin_without_the_file(self):
        snap = dict(self.snap)
        self.ensure()
        self.assertEqual(self.mirror.read_setups(snap, str(self.z0_home), self.env), {})


if __name__ == "__main__":
    unittest.main()
