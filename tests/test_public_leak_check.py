"""scripts/public-leak-check: generic patterns, fixture allowances, denylist, no echo.

Leak samples are assembled at runtime so this file itself scans clean.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public-leak-check"
loader = importlib.machinery.SourceFileLoader("public_leak_check", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
plc = importlib.util.module_from_spec(spec)
loader.exec_module(plc)

TS_IP = ".".join(["100", "101", "2", "3"])
TS_NAME = "box." + "tail" + "abcd12" + ".ts" + ".net"
GH_TOKEN = "gh" + "p_" + "B" * 36


def rules(text, denylist=()):
    return [rule for _, rule in plc.findings_in_text(text, denylist)]


class Patterns(unittest.TestCase):
    def test_tailnet_ipv4_flagged(self):
        self.assertEqual(rules(f"host = {TS_IP}"), ["tailnet-ipv4"])

    def test_range_edges(self):
        self.assertEqual(rules("100.63.1.1 100.128.1.1"), [])
        self.assertEqual(rules(".".join(["100", "127", "1", "1"])), ["tailnet-ipv4"])

    def test_documentation_fixtures_allowed(self):
        self.assertEqual(rules("peer 100.64.0.1 at laptop.example.ts.net"), [])

    def test_tailnet_names_flagged(self):
        self.assertEqual(sorted(rules(f"ssh you@{TS_NAME}")), ["tailnet-id", "tailnet-name"])

    def test_ipv6_tailnet_flagged(self):
        self.assertEqual(rules("addr " + "fd7a:115c:a1e0:" + ":1"), ["tailnet-ipv6"])

    def test_ipv6_prefix_alone_is_documentation(self):
        self.assertEqual(rules("the range " + "fd7a:115c:a1e0:" + ":/48"), [])

    def test_secret_flagged_without_echo(self):
        found = list(plc.findings_in_text(f"token: {GH_TOKEN}"))
        self.assertEqual(found, [(1, "github-token")])

    def test_denylist_literal_flagged_without_echo(self):
        found = list(plc.findings_in_text("a\nroot=/very/private\n", ["/very/private"]))
        self.assertEqual(found, [(2, "denylist")])

    def test_quad100_service_address_allowed(self):
        self.assertEqual(rules("nameserver 100.100.100.100"), [])

    def test_personal_paths_flagged(self):
        user = "k" + "q" + "z"
        self.assertEqual(rules(f"root=/home/{user}/x and /Users/{user}/y"), ["personal-path"] * 2)
        self.assertEqual(rules("mount /mnt/" + "bigdisk" + "/models"), ["mount-path"])

    def test_placeholder_paths_allowed(self):
        self.assertEqual(rules("/home/user/x /home/someone/x /Users/runner/y /home/$USER/z ~/x"), [])

    def test_personal_email_flagged_placeholders_allowed(self):
        self.assertEqual(rules("mail " + "kqz" + "@" + "gmail" + ".com"), ["personal-email"])
        self.assertEqual(rules("t@example.com 1+x@users.noreply.github.com noreply@anthropic.com"), [])

    def test_line_numbers_are_exact(self):
        self.assertEqual(list(plc.findings_in_text(f"a\nb\nhost {TS_IP}\n")), [(3, "tailnet-ipv4")])

    def test_absolute_denylist_path_needs_a_path_start(self):
        self.assertEqual(rules("~/srvx/a ./srvx b/srvx", ["/srvx"]), [])
        self.assertEqual(rules("cd /srvx/a; x=/srvx", ["/srvx"]), ["denylist", "denylist"])

    def test_clean_text(self):
        self.assertEqual(rules("port = 4747  # default\npath = ~/.config/z0-hosts"), [])


class Cli(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                              capture_output=True, text=True)

    def test_directory_scan_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "ok.md").write_text("nothing here\n")
            self.assertEqual(self.run_cli(str(tmp)).returncode, 0)
            (tmp / "bad.md").write_text(f"x {TS_IP}\n")
            res = self.run_cli(str(tmp))
            self.assertEqual(res.returncode, 1)
            self.assertIn("bad.md:1: tailnet-ipv4", res.stdout)
            self.assertNotIn(TS_IP, res.stdout + res.stderr)

    def test_overlay_literals_denied_and_never_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            host = tmp / "hosts" / "h1"
            host.mkdir(parents=True)
            (host / "files.toml").write_text('[storage]\nmodel_root = "/srv/PRIVROOT"\n')
            (host / "devices.toml").write_text('[p]\nkind = "phone"\nserial = "SER1AL99"\n')
            (tmp / "tree").mkdir()
            (tmp / "tree" / "f.txt").write_text("x /srv/PRIVROOT/y\nphone SER1AL99\n")
            res = self.run_cli(str(tmp / "tree"), "--overlay", str(tmp))
            self.assertEqual(res.returncode, 1)
            self.assertIn("f.txt:1: denylist", res.stdout)
            self.assertIn("f.txt:2: denylist", res.stdout)
            self.assertNotIn("PRIVROOT", res.stdout + res.stderr)
            self.assertNotIn("SER1AL99", res.stdout + res.stderr)
            self.assertEqual(self.run_cli(str(tmp / "tree"), "--overlay", str(tmp / "none")).returncode, 2)

    def test_denylist_file_never_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "deny.txt").write_text("# private\nSECRETPATHVALUE\n")
            (tmp / "tree").mkdir()
            (tmp / "tree" / "f.txt").write_text("SECRETPATHVALUE\n")
            res = self.run_cli(str(tmp / "tree"), "--denylist", str(tmp / "deny.txt"))
            self.assertEqual(res.returncode, 1)
            self.assertNotIn("SECRETPATHVALUE", res.stdout + res.stderr)

    def test_missing_path_is_usage_error(self):
        self.assertEqual(self.run_cli("/nonexistent/z0-leak-check").returncode, 2)

    def test_git_tracked_mode_only_scans_tracked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
            subprocess.run(["git", "init", "-q", tmp], check=True)
            (Path(tmp) / "tracked.txt").write_text("clean\n")
            subprocess.run([*git, "-C", tmp, "add", "tracked.txt"], check=True)
            (Path(tmp) / "untracked.txt").write_text(f"{TS_IP}\n")
            self.assertEqual(self.run_cli(cwd=tmp).returncode, 0)

    def test_this_repository_is_clean(self):
        res = self.run_cli(cwd=ROOT)
        self.assertEqual(res.returncode, 0, res.stdout)


if __name__ == "__main__":
    unittest.main()
