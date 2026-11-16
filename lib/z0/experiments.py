"""`z0 exp`: the experiment map, dedup fingerprints and the results ledger.

z0 owns the map, not the experiments. This module reads `registry/experiments.yaml`,
tells an agent what to run next (`start`), and formats/posts results (`post`). The
runners themselves live in each experiment's owning repo.

Results are GitHub issue comments that carry one machine-readable marker:

    <!-- z0-exp-result {"schema": "z0.exp.result.v1", ...} -->

so the ledger is just those markers, collected from every experiment issue. A cell
is identified by its fingerprint (see `fingerprint`); `start` offers only arms whose
cell has no result yet, so nobody repeats a measured cell by accident.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "registry" / "experiments.yaml"
RESULT_SCHEMA = "z0.exp.result.v1"
MARKER_RE = re.compile(r"<!--\s*z0-exp-result\s+(\{.*?\})\s*-->", re.S)
VERDICTS = {"KEEP", "DISCARD", "NULL", "INVALID"}
REQUIRED = ("schema", "exp_id", "epoch", "arm", "data_tier", "data_manifest_sha256",
            "hardware_class", "repo_sha", "n", "metric", "verdict", "command")
# Public-tier cells are worth re-running a few times by different people (replication);
# after that they count as done. Self-tier cells are per contributor dataset.
PUBLIC_REPLICATIONS = 3


def load_map(path: Path = MAP_PATH) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if data.get("schema") != "z0.experiments.v1":
        raise ValueError(f"{path}: schema must be z0.experiments.v1")
    ids = [e["id"] for e in data["experiments"]]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"duplicate experiment ids: {sorted(dup)}")
    for e in data["experiments"]:
        if e.get("goal") not in data["north_star"]:
            raise ValueError(f"{e['id']}: goal {e.get('goal')!r} is not a north_star key")
        for t in e.get("data_tier", []):
            if t not in data["data_tiers"]:
                raise ValueError(f"{e['id']}: unknown data tier {t!r}")
    return data


def get(data: dict[str, Any], exp_id: str) -> dict[str, Any]:
    for e in data["experiments"]:
        if e["id"] == exp_id:
            return {**data.get("defaults", {}), **e}
    raise KeyError(f"unknown experiment {exp_id!r}; run `./z0 exp list`")


def hardware_class() -> str:
    """Coarse and non-identifying: os-arch-ramGiB-gpu. Enough to separate cells."""
    ram = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                ram = round(int(line.split()[1]) / 1048576)
    except OSError:
        pass
    gpu = "nogpu"
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            gpu = re.sub(r"[^a-z0-9]+", "", out.stdout.strip().splitlines()[0].lower())
    except (OSError, subprocess.SubprocessError):
        pass
    return f"{platform.system().lower()}-{platform.machine()}-{ram}g-{gpu}"


def fingerprint(exp_id: str, epoch: int, arm: str, data_tier: str,
                data_manifest_sha256: str, hw: str, arm_spec_sha256: str = "") -> str:
    cell = {"exp": exp_id, "epoch": int(epoch), "arm": arm, "arm_spec": arm_spec_sha256,
            "tier": data_tier, "data": data_manifest_sha256, "hw": hw}
    return hashlib.sha256(json.dumps(cell, sort_keys=True).encode()).hexdigest()[:16]


def validate_result(r: dict[str, Any], exp: dict[str, Any]) -> list[str]:
    errs = [f"missing field {k}" for k in REQUIRED if k not in r]
    if r.get("schema") != RESULT_SCHEMA:
        errs.append(f"schema must be {RESULT_SCHEMA}")
    if r.get("exp_id") != exp["id"]:
        errs.append("exp_id does not match the experiment")
    if int(r.get("epoch", -1)) != int(exp.get("epoch", 1)):
        errs.append(f"epoch {r.get('epoch')} is stale; current epoch is {exp.get('epoch', 1)}")
    if r.get("verdict") not in VERDICTS:
        errs.append(f"verdict must be one of {sorted(VERDICTS)}")
    if r.get("data_tier") not in exp.get("data_tier", ["public"]):
        errs.append(f"data_tier {r.get('data_tier')!r} not allowed for this experiment")
    if r.get("data_tier") == "owner":
        errs.append("owner-tier results are posted only by the owner's loop")
    m = r.get("metric") or {}
    if exp.get("metric") and m.get("name") != exp["metric"]["name"]:
        errs.append(f"metric.name must be {exp['metric']['name']}")
    if not isinstance(m.get("value"), (int, float)):
        errs.append("metric.value must be a number")
    arms = {a["id"].split("<")[0] for a in exp.get("arms", [])}
    if arms and not any(r.get("arm", "").startswith(a) for a in arms):
        errs.append(f"arm {r.get('arm')!r} is not in the map (open a PR to add it)")
    if exp.get("controls_first", True) and exp.get("arms") and r.get("verdict") == "KEEP" \
            and not r.get("controls"):
        errs.append("KEEP needs the control values measured on the same split (controls)")
    return errs


def render_comment(r: dict[str, Any]) -> str:
    m = r["metric"]
    ci = m.get("ci95")
    ci_s = f" (95% CI {ci[0]:.4g} to {ci[1]:.4g})" if ci else ""
    lines = [
        f"### Result: `{r['arm']}` -> **{r['verdict']}**",
        "",
        f"- {m['name']} = **{m['value']:.4g}**{ci_s}, n = {r['n']}",
        f"- tier `{r['data_tier']}`, hardware `{r['hardware_class']}`, repo sha `{r['repo_sha'][:12]}`",
        f"- fingerprint `{r['fingerprint']}`, epoch {r['epoch']}",
        f"- command: `{r['command']}`",
    ]
    if r.get("controls"):
        lines.append("- controls: " + ", ".join(f"{k}={v:.4g}" for k, v in r["controls"].items()))
    if r.get("notes"):
        lines += ["", r["notes"]]
    lines += ["", f"<!-- z0-exp-result {json.dumps(r, sort_keys=True)} -->"]
    return "\n".join(lines)


def parse_markers(comments: list[str]) -> list[dict[str, Any]]:
    rows = []
    for body in comments:
        for raw in MARKER_RE.findall(body or ""):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("schema") == RESULT_SCHEMA:
                rows.append(row)
    return rows


def _cache_dir() -> Path:
    return Path(os.environ.get("Z0_HOME", Path.home() / ".z0")) / "experiments"


def fetch_ledger(exp: dict[str, Any], refresh: bool = True) -> list[dict[str, Any]]:
    """Result rows for one experiment: cached markers, refreshed from its issue via gh."""
    cache = _cache_dir() / f"{exp['id']}.ledger.json"
    issue = exp.get("issue")
    if refresh and issue:
        try:
            out = subprocess.run(
                ["gh", "api", "--paginate", f"repos/{exp['repo']}/issues/{issue}/comments",
                 "--jq", ".[].body"], capture_output=True, text=True, timeout=60)
            if out.returncode == 0:
                # --jq prints bodies separated by newlines; markers are single-line JSON.
                rows = parse_markers([out.stdout])
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(rows))
                return rows
        except (OSError, subprocess.SubprocessError):
            pass
    return json.loads(cache.read_text()) if cache.exists() else []


def untried_arms(exp: dict[str, Any], ledger: list[dict[str, Any]], tier: str, hw: str,
                 data_sha: str) -> list[dict[str, Any]]:
    epoch = int(exp.get("epoch", 1))
    out = []
    for arm in exp.get("arms", []):
        aid = arm["id"]
        if "<" in aid:  # open arm family (one per model/hash): always offered
            out.append({**arm, "status": "open-family"})
            continue
        same = [r for r in ledger if r.get("arm") == aid and int(r.get("epoch", 0)) == epoch
                and r.get("data_tier") == tier and r.get("verdict") != "INVALID"]
        if tier == "public":
            mine = [r for r in same if r.get("hardware_class") == hw]
            if mine or len(same) >= PUBLIC_REPLICATIONS:
                continue
        elif any(r.get("data_manifest_sha256") == data_sha for r in same):
            continue
        out.append({**arm, "status": "untried" if not same else f"replicate ({len(same)} so far)"})
    return out


def next_action(exp: dict[str, Any], ledger: list[dict[str, Any]], tier: str, hw: str,
                data_sha: str) -> dict[str, Any]:
    runner = exp.get("runner") or {}
    repo = exp["repo"].split("/", 1)[1]
    checkout = f"~/.z0/repos/{repo}"
    if exp["kind"] == "enabler" or runner.get("status") == "missing":
        return {"kind": "build", "why": (
            "This entry has no runner yet. The task is to build it exactly as the issue's "
            "Deliverable/Runner spec says, in a worktree of " + exp["repo"] + ", with tests, "
            "then open a draft PR after the user says yes. Building it is the contribution."),
            "command": f"cd {checkout} && git worktree add ../{repo}-{exp['id']} -b exp/{exp['id']}"}
    arms = untried_arms(exp, ledger, tier, hw, data_sha)
    controls = [a for a in arms if a.get("control")]
    if not arms:
        return {"kind": "done", "why": "Every arm has a result for this tier and hardware. "
                "Propose a new arm via PR to registry/experiments.yaml, or run another tier."}
    pick = controls[0] if controls else arms[0]
    cmd = runner.get("command") or f"python {runner.get('path')} --arm {pick['id']} --tier {tier}"
    return {"kind": "run", "arm": pick["id"], "why": (
        "Controls first: measure every control before any candidate." if controls else
        "Controls are measured; run the next untried candidate."),
        "command": f"cd {checkout} && {cmd} --out ~/.z0/experiments/{exp['id']}/result.json",
        "then": f"./z0 exp post {exp['id']} ~/.z0/experiments/{exp['id']}/result.json",
        "untried": [a["id"] for a in arms]}


def render_issue(data: dict[str, Any], exp_id: str, rfc_url: str = "") -> str:
    e = get(data, exp_id)
    ns = data["north_star"][e["goal"]]
    L = [f"> Experiment `{e['id']}` · {e['kind']} · north star **{e['goal']} {ns['title']}**"
         + (f" · parent RFC: {rfc_url}" if rfc_url else ""),
         "> Canonical definition: [`kvnloo/z0` registry/experiments.yaml]"
         "(https://github.com/kvnloo/z0/blob/main/registry/experiments.yaml). "
         "This issue holds discussion and posted results.", "",
         "## Why this matters", e["problem"].strip(), "", f"North star: {ns['text'].strip()}", "",
         "## Hypothesis", e["hypothesis"].strip(), ""]
    if e.get("deliverable"):
        L += ["## Deliverable", e["deliverable"].strip(), ""]
    if e.get("arms"):
        L += ["## Arms", "| arm | role | notes |", "|---|---|---|"]
        for a in e["arms"]:
            L.append(f"| `{a['id']}` | {'control' if a.get('control') else 'candidate'} | {a.get('desc', '')} |")
        L.append("")
    if e.get("metric"):
        L += ["## Metric and gates",
              f"- primary: `{e['metric']['name']}` ({e['metric']['direction']} is better)"]
        L += [f"- gate: {g}" for g in e.get("gates", [])]
        L += [f"- keep rule: {e['keep_rule'].strip()}", ""]
    if e.get("data_tier"):
        L += ["## Data"] + [f"- `{t}`: {data['data_tiers'][t].strip()}" for t in e["data_tier"]] + [""]
    if e.get("hardware"):
        L += [f"**Hardware/budget:** {e['hardware']}", ""]
    r = e.get("runner") or {}
    L += ["## How to run it (self-contained)",
          "Tell your coding agent: **\"start experiment " + e["id"] + "\"**. It does this:", "```bash",
          "git clone https://github.com/kvnloo/z0 ~/z0 && cd ~/z0",
          "./z0 onboard --auto --llm none     # once per machine; see AGENTS.md",
          f"./z0 exp start {e['id']}           # prints next_action JSON: build | run | done",
          "```",
          f"Runner status: **{r.get('status', 'missing')}**"
          + (f" (`{r.get('command') or r.get('path')}`)" if r.get("command") or r.get("path") else "") + ".",
          "If the status is `missing`, `next_action.kind` is `build`: building the runner to the spec "
          "above (with tests and a `--arm/--tier/--out` interface that writes `z0.exp.result.v1`) is the "
          "contribution. Claim it with `/claim " + e["id"] + "` in a comment.", "",
          "## Posting results (automatic, no repeats)",
          f"`./z0 exp post {e['id']} result.json` validates the result (schema, epoch, arm, controls) "
          "and prints the comment; with `--yes` it posts here. Each comment carries a "
          "`<!-- z0-exp-result {...} -->` marker. `./z0 exp start` reads those markers and offers only "
          "cells nobody has measured on your tier/hardware, so experiments are never repeated by "
          "accident. Post nulls and failures too; they are results.", ""]
    if e.get("prior"):
        L += ["## Prior work (read before starting)"] + [f"- {p}" for p in e["prior"]] + [""]
    if e.get("done_when"):
        L += ["## Done when", e["done_when"], ""]
    L += ["## Rules", "- Never post, push or open a PR without your user's explicit yes.",
          "- Raw private data never leaves the machine; post aggregates only.",
          "- Changing arms, metric, gates or data means a PR that bumps `epoch` in the map.",
          "- Credit upstream projects you reuse in the PR body."]
    return "\n".join(L)


def cmd(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="z0 exp", description="Experiment map, dedup and results")
    sub = p.add_subparsers(dest="sub")
    pl = sub.add_parser("list"); pl.add_argument("--repo"); pl.add_argument("--json", action="store_true")
    ps = sub.add_parser("show"); ps.add_argument("id")
    pst = sub.add_parser("start"); pst.add_argument("id")
    pst.add_argument("--tier", default="public"); pst.add_argument("--data-sha", default="fixture")
    pst.add_argument("--offline", action="store_true", help="use the cached ledger only")
    pp = sub.add_parser("post"); pp.add_argument("id"); pp.add_argument("result")
    pp.add_argument("--yes", action="store_true", help="post the comment (needs the user's explicit yes)")
    pr = sub.add_parser("render"); pr.add_argument("id"); pr.add_argument("--rfc", default="")
    pf = sub.add_parser("fingerprint"); pf.add_argument("id"); pf.add_argument("arm")
    pf.add_argument("--tier", default="public"); pf.add_argument("--data-sha", default="fixture")
    a = p.parse_args(argv)
    data = load_map()
    if a.sub == "list":
        rows = [e for e in data["experiments"] if not a.repo or e["repo"].endswith(a.repo)]
        if a.json:
            print(json.dumps([{k: e.get(k) for k in ("id", "kind", "repo", "goal", "title", "issue")}
                              for e in rows], indent=2))
        else:
            for e in rows:
                st = (e.get("runner") or {}).get("status", "missing")
                print(f"{e['id']:26} {e['goal']} {e['kind']:10} runner={st:8} {e['repo']}#{e.get('issue', '?')}  {e['title']}")
        return 0
    if a.sub in ("show", "render"):
        print(render_issue(data, a.id, getattr(a, "rfc", "")))
        return 0
    exp = get(data, a.id)
    hw = hardware_class()
    if a.sub == "fingerprint":
        print(fingerprint(exp["id"], exp.get("epoch", 1), a.arm, a.tier, a.data_sha, hw))
        return 0
    if a.sub == "start":
        ledger = fetch_ledger(exp, refresh=not a.offline)
        act = next_action(exp, ledger, a.tier, hw, a.data_sha)
        print(json.dumps({"schema": "z0.exp.start.v1", "exp_id": exp["id"], "epoch": exp.get("epoch", 1),
                          "issue": f"https://github.com/{exp['repo']}/issues/{exp.get('issue', '')}",
                          "hardware_class": hw, "tier": a.tier, "ledger_rows": len(ledger),
                          "next_action": act}, indent=2))
        return 0
    if a.sub == "post":
        r = json.loads(Path(a.result).expanduser().read_text())
        r.setdefault("hardware_class", hw)
        r["fingerprint"] = fingerprint(exp["id"], r.get("epoch", 0), r.get("arm", ""),
                                       r.get("data_tier", ""), r.get("data_manifest_sha256", ""),
                                       r["hardware_class"], r.get("arm_spec_sha256", ""))
        errs = validate_result(r, exp)
        if errs:
            print("\n".join(f"INVALID: {x}" for x in errs))
            return 2
        body = render_comment(r)
        if not a.yes:
            print(body)
            print("\n# Not posted. Re-run with --yes after your user approves the post.")
            return 0
        if not exp.get("issue"):
            print("no issue number in the map for this experiment")
            return 2
        return subprocess.run(["gh", "issue", "comment", str(exp["issue"]), "-R", exp["repo"],
                               "--body", body]).returncode
    p.print_help()
    return 0
