"""Stage 0 (§1.3) on a fake host: bash only, consent for downloads, writes only under
$Z0_HOME/{bootstrap,venv}, hashed PyYAML, no --break-system-packages."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.onboard import fakehost
from tests.onboard.support import HAVE_YAML, ROOT

STAGE0 = ROOT / "lib/z0/onboard/stage0.sh"
TOOLS = ("awk", "uname", "dirname", "cat", "mkdir", "date", "cut", "rm", "tar", "basename")


def tool_dir(root: Path, with_python: bool, python_body: str = "") -> Path:
    """A PATH of harmless real tools; `python_body` runs first in the python3 wrapper."""
    bin_dir = root / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        if found:
            os.symlink(found, bin_dir / tool)
    if with_python:
        wrapper = bin_dir / "python3"
        wrapper.write_text(f'#!/bin/sh\n{python_body}\nexec "{sys.executable}" "$@"\n')
        wrapper.chmod(0o755)
    return bin_dir


# A Debian/Ubuntu python3 without python3-venv: `import ensurepip` fails.
NO_ENSUREPIP = 'case "$*" in *ensurepip*) echo "No module named ensurepip" >&2; exit 1 ;; esac'
# `python -m venv` leaves a partial dir behind, then fails.
VENV_FAILS = 'if [ "$1" = -m ] && [ "$2" = venv ]; then mkdir -p "$3/bin"; exit 1; fi'


class Stage0(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bash = shutil.which("bash")

    def tearDown(self):
        self.tmp.cleanup()

    def run_stage0(self, path, *args, extra=None):
        # Sealed: the python search after PATH sees only the fake home, never the real
        # host's /opt/homebrew/bin or pyenv/mise shims.
        env = {"HOME": str(self.home), "PATH": str(path), "Z0_HOME": str(self.home / ".z0"),
               "LANG": "C", "Z0_STAGE0_PY_DIRS": str(self.home / ".local/bin")}
        env.update(extra or {})
        return subprocess.run([self.bash, str(STAGE0), *args], env=env, capture_output=True,
                              text=True, stdin=subprocess.DEVNULL, timeout=120)

    @unittest.skipUnless(HAVE_YAML, "PyYAML not installed")
    def test_uv_pin_parse_matches_the_registry(self):
        import yaml
        uv = yaml.safe_load((ROOT / "registry/toolchains.yaml").read_text())["tools"]["uv"]["install"]
        for key, row in uv["targets"].items():
            out = subprocess.run([self.bash, str(STAGE0), "__uv_pin", key], capture_output=True,
                                 text=True, check=True).stdout.split()
            self.assertEqual(out, [uv["version"], row["target"], row["sha256"]], key)

    def test_no_python_and_no_consent_exits_3_and_writes_nothing(self):
        bin_dir = tool_dir(self.root, with_python=False)
        before = fakehost.tree_state(self.home)
        out = self.run_stage0(bin_dir, "onboard", "plan")
        self.assertEqual(out.returncode, 3, out.stderr)
        self.assertIn("--yes", out.stderr)
        self.assertIn("sha256sum -c", out.stderr)
        self.assertEqual(fakehost.tree_state(self.home), before)

    def test_python_without_ensurepip_and_no_consent_exits_3(self):
        bin_dir = tool_dir(self.root, with_python=True, python_body=NO_ENSUREPIP)
        before = fakehost.tree_state(self.home)
        out = self.run_stage0(bin_dir, "onboard", "plan")
        self.assertEqual(out.returncode, 3, out.stderr)
        self.assertIn("no ensurepip", out.stderr)
        self.assertIn("--yes", out.stderr)
        self.assertIn("venv --python", out.stderr)
        self.assertIn("python3-venv", out.stderr)
        self.assertEqual(fakehost.tree_state(self.home), before)

    def test_python_without_ensurepip_uses_an_existing_uv(self):
        bin_dir = tool_dir(self.root, with_python=True, python_body=NO_ENSUREPIP)
        log = self.root / "uv.log"
        fake_uv = bin_dir / "uv"
        fake_uv.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\n'
                           'if [ "$1" = venv ]; then eval "d=\\${$#}"; mkdir -p "$d/bin"; '
                           f'ln -s "{sys.executable}" "$d/bin/python"; fi\nexit 0\n')
        fake_uv.chmod(0o755)
        out = self.run_stage0(bin_dir, "onboard", "plan", extra={"Z0_STAGE0_DRY_EXEC": "1"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("venv --quiet --python", log.read_text())

    def test_a_failed_venv_is_removed(self):
        bin_dir = tool_dir(self.root, with_python=True, python_body=VENV_FAILS)
        out = self.run_stage0(bin_dir, "onboard", "plan")
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("could not create the z0 venv", out.stderr)
        self.assertFalse((self.home / ".z0/venv").exists(), "a partial venv was left behind")

    def test_with_python_makes_only_the_z0_venv(self):
        bin_dir = tool_dir(self.root, with_python=True)
        log = self.root / "uv.log"
        fake_uv = bin_dir / "uv"
        fake_uv.write_text(f'''#!/bin/sh
printf '%s|UV_CACHE_DIR=%s\\n' "$*" "$UV_CACHE_DIR" >> "{log}"
if [ "$1" = venv ]; then
  shift; while [ "$#" -gt 1 ]; do case "$1" in --python) py="$2"; shift 2 ;; *) shift ;; esac; done
  "$py" -m venv --without-pip "$1"
fi
exit 0
''')
        fake_uv.chmod(0o755)
        out = self.run_stage0(bin_dir, "onboard", "plan", "--stdout",
                              extra={"Z0_STAGE0_DRY_EXEC": "1"})
        self.assertEqual(out.returncode, 0, out.stderr)
        z0 = self.home / ".z0"
        self.assertEqual(out.stdout.strip(), f"exec {z0}/venv/bin/python -m z0 onboard plan --stdout")
        top = sorted(p.name for p in self.home.iterdir())
        self.assertEqual(top, [".z0"])
        self.assertEqual(sorted(p.name for p in z0.iterdir()), ["bootstrap", "venv"])
        self.assertTrue((z0 / "venv/.z0-owned").is_file())
        self.assertTrue((z0 / "bootstrap/.z0-owned").is_file())
        journal = (z0 / "bootstrap/stage0.jsonl").read_text()
        self.assertIn('"step":"venv"', journal)
        self.assertNotIn(str(self.home), journal)
        calls = log.read_text()
        self.assertIn("--require-hashes -r " + str(ROOT / "requirements.lock"), calls)
        self.assertIn(f"UV_CACHE_DIR={z0}/bootstrap/uv-cache", calls)
        self.assertNotIn("break-system-packages", calls)

    def test_lock_pins_pyyaml_with_hashes(self):
        text = (ROOT / "requirements.lock").read_text()
        self.assertIn("pyyaml==6.0.3", text.lower())
        self.assertGreater(text.count("--hash=sha256:"), 10)


if __name__ == "__main__":
    unittest.main()
