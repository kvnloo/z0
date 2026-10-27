"""Profile -> first-task handoff for the contributor acceptance profiles, without a container.

The agent cells (scripts/onboard-agent-e2e) build a synthetic HOME with
tests/contrib_e2e/make_home.sh and run `z0int contribute` inside it; the judge then
checks the pick against tests/contrib_e2e/profiles/<profile>/oracle.json. z0int's own
oracle tests feed its ranker the *fixture* profile, so they never prove that the HOME
we build makes the T1 probe see that profile. agent.claude.ml-research.run1 (z0
c39c1d3) picked t-139 like a frontend contributor: the ml-research HOME had no `nvcc`
and no `nvidia-smi`, so the probe saw python on a CPU host.

- FixtureFacts (always): every toolchain and the GPU in the oracle's `profile_facts`
  is observable the way z0int's probe looks for it (TOOLCHAIN_BINARIES, nvidia-smi
  memory.total in MiB), and nothing more is.
- RankerHandoff (needs a z0intelligence checkout with `.venv`, via Z0INT_ROOT): z0int's
  real T0 probe in the fixture HOME (sealed PATH), T1, and the align() call that
  `z0int contribute suggest --llm=none --profile=minimal` makes, judged with the cell
  judge's oracle_ok.
  Z0_REQUIRE_Z0INT=1 (the E2 deterministic cell) turns a skip into a failure.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PROFILES = ("frontend", "ml-research", "systems-rust")
# z0int contribute/profile_min.py TOOLCHAIN_BINARIES (the closed toolchain vocab);
# python is always present. Keep in step with z0int.
TOOLCHAIN_BINARIES = {"node": ("node",), "bun": ("bun",), "cargo": ("cargo",), "go": ("go",),
                      "cuda": ("nvcc",), "llama-cpp": ("llama-server", "llama-cli")}
# base tools a z0int CLI run may exec; nothing the probe treats as a profile fact
SYSTEM_TOOLS = ("sh", "bash", "git", "env", "uname", "cat", "ls", "mkdir", "rm", "date", "id",
                "sed", "grep", "tr", "head", "python3")
QUERY = ["--query-gpu=memory.total", "--format=csv,noheader,nounits"]


def _judge():
    spec = importlib.util.spec_from_file_location("contrib_e2e_judge", HERE / "judge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def oracle_of(profile: str) -> dict:
    return json.loads((HERE / "profiles" / profile / "oracle.json").read_text(encoding="utf-8"))


def make_home(profile: str, home: Path) -> Path:
    subprocess.run(["bash", str(HERE / "make_home.sh"), profile, str(home), "Z0CANARYtest"],
                   check=True, capture_output=True, text=True, timeout=60)
    return home / ".local" / "bin"


def observed(bindir: Path) -> dict:
    """What z0int's T0 probe would find on PATH = bindir only."""
    have = lambda b: os.access(bindir / b, os.X_OK)  # noqa: E731
    tools = ["python"] + [tag for tag, bins in TOOLCHAIN_BINARIES.items() if any(have(b) for b in bins)]
    gpu = {"class": "none", "vram_gib": 0}
    if have("nvidia-smi"):
        out = subprocess.run([str(bindir / "nvidia-smi"), *QUERY], capture_output=True, text=True,
                             timeout=10).stdout.strip().splitlines()
        mib = float(out[0]) if out and out[0].replace(".", "", 1).isdigit() else 0.0
        if mib:
            gpu = {"class": "nvidia", "vram_gib": int(round(mib / 1024))}
            if "cuda" not in tools:
                tools.append("cuda")
    return {"toolchains": tools, "gpu": gpu}


class FixtureFacts(unittest.TestCase):
    def test_each_home_shows_exactly_its_oracle_facts(self):
        for profile in PROFILES:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as tmp:
                facts = oracle_of(profile)["profile_facts"]
                seen = observed(make_home(profile, Path(tmp) / "home"))
                self.assertEqual(sorted(seen["toolchains"]), sorted(facts["toolchains"]), profile)
                self.assertEqual(seen["gpu"], facts["gpu"], profile)


# Runs inside the z0intelligence venv: the real T0 probe in the fixture HOME, then the same
# align() call `z0int contribute suggest --profile=minimal --llm=none` makes. RAM and disk
# are host facts, not profile facts: they are pinned (a "16 GB" laptop probes 15.5 GiB,
# z0int 7bbeb311; a roomy disk), so the test checks the profile handoff on any host.
RANK = r"""
import json, os, sys
from pathlib import Path
from z0int.contribute import align as A, priorities as P, profile_min
root = Path(sys.argv[1])
prof = profile_min.probe_t0(home=Path(os.environ["HOME"]), workdir=root)
prof["hw"].update(ram_gib=15.5, disk_free_gib=100.0)
prof = profile_min.apply_tier(prof, "T1")
out = A.align(P.load_priorities(root), P.load_vocab(root), prof, {}, live_claims=None,
              issue_states=None, onboard_mode="full", llm="none")
print(json.dumps({"pick": out["pick"], "alternatives": out["alternatives"],
                  "toolchains": prof["toolchains"], "gpu": prof["hw"]["gpu"]}))
"""


@unittest.skipUnless(os.environ.get("Z0INT_ROOT") or os.environ.get("Z0_REQUIRE_Z0INT") == "1",
                     "set Z0INT_ROOT to a z0intelligence checkout with .venv (the E2 cell does)")
class RankerHandoff(unittest.TestCase):
    """The real T1 probe and ranker on each fixture HOME pick what the oracle allows."""

    @classmethod
    def setUpClass(cls):
        root = os.environ.get("Z0INT_ROOT", "")
        cls.zi = Path(root)
        cls.py = cls.zi / ".venv" / "bin" / "python"
        if not (root and cls.py.exists()):
            raise AssertionError(f"Z0INT_ROOT={root!r} has no .venv/bin/python")
        cls.judge = _judge()
        cls.tasks = cls.judge.task_index(cls.judge.load_yaml(cls.zi / ".z0" / "priorities.yaml"))

    def rank(self, profile: str, home: Path) -> dict:
        bindir = make_home(profile, home)
        # A sealed PATH, like the container: the fixture stubs plus a few base tools.
        # The host /usr/bin can hold node, go, nvidia-smi or harnesses, which the probe
        # would count as this profile's facts.
        sysbin = home.parent / "sysbin"
        sysbin.mkdir(exist_ok=True)
        for tool in SYSTEM_TOOLS:
            found = shutil.which(tool)
            if found and not (sysbin / tool).exists():
                (sysbin / tool).symlink_to(found)
        env = {"HOME": str(home), "USER": "contributor", "LANG": "C.UTF-8",
               "PATH": f"{bindir}:{sysbin}"}
        run = subprocess.run([str(self.py), "-c", RANK, str(self.zi)], cwd=self.zi, env=env,
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        return json.loads(run.stdout.strip().splitlines()[-1])

    def test_pick_matches_the_oracle_for_every_profile(self):
        for profile in PROFILES:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as tmp:
                out = self.rank(profile, Path(tmp) / "home")
                facts = oracle_of(profile)["profile_facts"]
                self.assertEqual(sorted(out["toolchains"]), sorted(facts["toolchains"]), profile)
                self.assertEqual(out["gpu"], facts["gpu"], profile)
                pick = out["pick"]["task"]
                alts = [a["task"] for a in out["alternatives"]]
                ok, why = self.judge.oracle_ok(pick, alts, oracle_of(profile)["oracle"], self.tasks)
                self.assertTrue(ok, f"{profile}: {why}; pick {pick}, reasons {out['pick'].get('reasons')}")


if __name__ == "__main__":
    unittest.main()
