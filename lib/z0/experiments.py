"""`z0 exp`: the experiment map, dedup fingerprints and the results ledger.

z0 owns the map, not the experiments. This module reads `registry/experiments.yaml`,
tells an agent what to run next (`start`), and formats/posts results (`post`). The
runners themselves live in each experiment's owning repo.

Results are GitHub issue comments that carry one machine-readable marker:

    <!-- z0-exp-result {"schema": "z0.exp.result.v1", ...} -->

so the ledger is just those markers, collected from every experiment issue. A cell
is identified by its fingerprint (see `fingerprint`); `start` offers only arms whose
cell has no result yet, so nobody repeats a measured cell by accident.

`./z0 exp ledger --refresh` harvests every mapped issue's markers into
`generated/experiments-ledger.jsonl` plus one leaderboard per experiment
(`generated/experiments/<id>.md`); a scheduled Action keeps them current. A referee
re-run that reproduces a cell marks it with a second marker kind,
`<!-- z0-exp-verify {"schema": "z0.exp.verify.v1", ...} -->`, which the ledger
merges into the matching row as `verified`.
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
VERIFY_SCHEMA = "z0.exp.verify.v1"
VERIFY_MARKER_RE = re.compile(r"<!--\s*z0-exp-verify\s+(\{.*?\})\s*-->", re.S)
# Fields the ledger build derives; stripped when deduping a row seen from two sources.
DERIVED_FIELDS = frozenset({"issue", "verified", "verified_by", "verified_note"})
LEDGER_JSONL = ROOT / "generated" / "experiments-ledger.jsonl"
LEDGER_MD_DIR = ROOT / "generated" / "experiments"
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
    if str(r.get("repo_sha", "")).endswith("+dirty"):
        errs.append("repo_sha ends in +dirty: the run had uncommitted changes; commit, re-run, then post")
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


def _markers(comments: list[str], rx: re.Pattern, schema: str) -> list[dict[str, Any]]:
    rows = []
    for body in comments:
        for raw in rx.findall(body or ""):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get("schema") == schema:
                rows.append(row)
    return rows


def parse_markers(comments: list[str]) -> list[dict[str, Any]]:
    return _markers(comments, MARKER_RE, RESULT_SCHEMA)


def parse_verify_markers(comments: list[str]) -> list[dict[str, Any]]:
    return _markers(comments, VERIFY_MARKER_RE, VERIFY_SCHEMA)


def _cache_dir() -> Path:
    return Path(os.environ.get("Z0_HOME", Path.home() / ".z0")) / "experiments"


def _gh_issue_bodies(exp: dict[str, Any]) -> str | None:
    """Raw issue-comment text via gh; None when gh or the issue is unavailable.
    --jq prints bodies separated by newlines; markers are single-line JSON."""
    issue = exp.get("issue")
    if not issue:
        return None
    try:
        out = subprocess.run(
            ["gh", "api", "--paginate", f"repos/{exp['repo']}/issues/{issue}/comments",
             "--jq", ".[].body"], capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            return out.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def repo_ledger_rows(exp_id: str, path: Path | None = None) -> list[dict[str, Any]]:
    """Rows committed in generated/experiments-ledger.jsonl for one experiment."""
    p = path or LEDGER_JSONL
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("exp_id") == exp_id:
            rows.append(row)
    return rows


def _row_key(row: dict[str, Any]) -> str:
    core = {k: v for k, v in row.items() if k not in DERIVED_FIELDS}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First occurrence wins: the committed ledger carries verify marks gh rows lack."""
    seen, out = set(), []
    for r in rows:
        key = _row_key(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def fetch_ledger(exp: dict[str, Any], refresh: bool = True,
                 ledger_path: Path | None = None) -> list[dict[str, Any]]:
    """Result rows for one experiment: committed ledger + fresh markers or the cache."""
    cache = _cache_dir() / f"{exp['id']}.ledger.json"
    fresh = None
    if refresh:
        bodies = _gh_issue_bodies(exp)
        if bodies is not None:
            fresh = parse_markers([bodies])
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(fresh))
            except OSError:
                pass
    if fresh is None and cache.exists():
        try:
            fresh = json.loads(cache.read_text())
        except (OSError, json.JSONDecodeError):
            fresh = []
    return _dedupe_rows(repo_ledger_rows(exp["id"], ledger_path) + (fresh or []))


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
    worktree = f"cd {checkout} && git worktree add ../{repo}-{exp['id']} -b exp/{exp['id']}"
    result = f"~/.z0/experiments/{exp['id']}/result.json"
    post = f"./z0 exp post {exp['id']} {result}"
    if exp["kind"] == "enabler" or runner.get("status") == "missing":
        return {"kind": "build", "why": (
            "This entry has no runner yet. The task is to build it exactly as the issue's "
            "Deliverable/Runner spec says, in a worktree of " + exp["repo"] + ", with tests, "
            "then open a draft PR after the user says yes. Building it is the contribution."),
            "command": worktree}
    arms = untried_arms(exp, ledger, tier, hw, data_sha)
    controls = [a for a in arms if a.get("control")]
    if not arms:
        return {"kind": "done", "why": "Every arm has a result for this tier and hardware. "
                "Propose a new arm via PR to registry/experiments.yaml, or run another tier."}
    pick = controls[0] if controls else arms[0]
    if pick.get("status") == "open-family" and not runner.get("command"):  # `<...>` is not an arm
        return {"kind": "build", "arm": pick["id"], "why": (
            f"Every fixed arm is measured. The next cell is your own `{pick['id']}` arm: write it "
            f"as the issue's Deliverable says, with a test, in the worktree below, and commit it. "
            f"Then run the runner there with `--arm` set to your arm id (`{pick['id'].split('<')[0]}` "
            f"plus your own value for the `<...>` part) and `--out {result}`, so the result's "
            "repo_sha is your commit, and post it."),
            "command": worktree, "then": post, "untried": [a["id"] for a in arms]}
    cmd = runner.get("command") or f"python3 {runner.get('path')} --arm {pick['id']} --tier {tier}"
    return {"kind": "run", "arm": pick["id"], "why": (
        "Controls first: measure every control before any candidate." if controls else
        "Controls are measured; run the next untried candidate."),
        "command": f"cd {checkout} && {cmd} --out {result}",
        "then": post, "untried": [a["id"] for a in arms]}


def apply_verify(rows: list[dict[str, Any]],
                 verifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark rows whose fingerprint a z0-exp-verify marker reproduces (latest wins)."""
    latest = {v["fingerprint"]: v for v in verifications if v.get("fingerprint")}
    out = []
    for r in rows:
        v = latest.get(r.get("fingerprint"))
        if not v:
            out.append(r)
            continue
        marked = dict(r, verified=True)
        if v.get("by"):
            marked["verified_by"] = v["by"]
        if v.get("note"):
            marked["verified_note"] = v["note"]
        out.append(marked)
    return out


def verify_comment(exp: dict[str, Any], v: dict[str, Any]) -> str:
    lines = [f"### Verified cell `{v['fingerprint']}`", "",
             f"- experiment `{v['exp_id']}`, epoch {exp.get('epoch', 1)}"]
    if v.get("by"):
        lines.append(f"- verified by `{v['by']}`")
    if v.get("note"):
        lines += ["", v["note"]]
    lines += ["", f"<!-- z0-exp-verify {json.dumps(v, sort_keys=True)} -->"]
    return "\n".join(lines)


def gh_login() -> str:
    try:
        out = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def collect_rows(data: dict[str, Any], refresh: bool = True) -> dict[str, list[dict[str, Any]]]:
    """exp_id -> ledger rows: the committed ledger + fresh issue markers or caches."""
    out: dict[str, list[dict[str, Any]]] = {}
    for e in data["experiments"]:
        exp_id = e["id"]
        fresh: list[dict[str, Any]] | None = None
        if refresh:
            bodies = _gh_issue_bodies(e)
            if bodies is not None:
                rows = apply_verify(
                    parse_markers([bodies]),
                    [v for v in parse_verify_markers([bodies])
                     if v.get("exp_id", exp_id) == exp_id])
                cache = _cache_dir() / f"{exp_id}.ledger.json"
                try:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps(rows))
                except OSError:
                    pass
                fresh = rows
        if fresh is None:
            cache = _cache_dir() / f"{exp_id}.ledger.json"
            try:
                fresh = json.loads(cache.read_text()) if cache.exists() else []
            except (OSError, json.JSONDecodeError):
                fresh = []
        out[exp_id] = _dedupe_rows(repo_ledger_rows(exp_id) + fresh)
    return out


def _metric_value(row: dict[str, Any]) -> float | None:
    v = (row.get("metric") or {}).get("value")
    return v if isinstance(v, (int, float)) else None


def leaderboard_markdown(data: dict[str, Any], exp_id: str,
                         rows: list[dict[str, Any]]) -> str:
    exp = get(data, exp_id)
    metric = exp.get("metric") or {}
    mname = metric.get("name", "metric")
    direction = metric.get("direction", "up")
    tiers = list(exp.get("data_tier") or [])

    def tier_rank(t: str) -> int:
        return tiers.index(t) if t in tiers else len(tiers)

    def value_rank(r: dict[str, Any]) -> float:
        v = _metric_value(r)
        if v is None:
            return float("inf")
        return -v if direction == "up" else v

    ordered = sorted(rows, key=lambda r: (
        tier_rank(r.get("data_tier", "")), r.get("verdict") == "INVALID",
        value_rank(r), r.get("arm", ""), r.get("fingerprint", "")))

    L = [f"# {exp_id}: {exp.get('title', '')}", ""]
    if exp.get("issue"):
        L.append(f"- Issue: https://github.com/{exp['repo']}/issues/{exp['issue']}")
    L += [f"- Metric: `{mname}` ({direction} is better) · epoch {exp.get('epoch', 1)}",
          f"- {len(rows)} result row(s). Generated by `./z0 exp ledger --refresh` from "
          "`z0-exp-result` and `z0-exp-verify` markers; do not edit.", "",
          f"| arm | epoch | tier | hardware | verdict | {mname} | 95% CI | n | verified "
          "| repo sha | fingerprint |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in ordered:
        v = _metric_value(r)
        ci = (r.get("metric") or {}).get("ci95") or []
        ci_s = f"{ci[0]:.4g} to {ci[1]:.4g}" if len(ci) == 2 else "—"
        ver = ""
        if r.get("verified"):
            ver = "✓" + (f" {r['verified_by']}" if r.get("verified_by") else "")
        L.append("| " + " | ".join([
            f"`{r.get('arm', '')}`", str(r.get("epoch", "")),
            f"`{r.get('data_tier', '')}`", f"`{r.get('hardware_class', '')}`",
            r.get("verdict", ""), f"{v:.4g}" if v is not None else "—", ci_s,
            str(r.get("n", "")), ver, f"`{str(r.get('repo_sha', ''))[:12]}`",
            f"`{r.get('fingerprint', '')}`"]) + " |")
    L += ["", "_Generated from issue comments. Do not edit by hand._", ""]
    return "\n".join(L)


def build_ledger_files(data: dict[str, Any],
                       rows_by_exp: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    """relpath -> content for the committed ledger and per-experiment leaderboards."""
    rows = []
    for exp_id in sorted(rows_by_exp):
        exp = get(data, exp_id)
        issue_ref = f"{exp['repo']}#{exp['issue']}" if exp.get("issue") else ""
        for r in rows_by_exp[exp_id]:
            row = dict(r)
            if issue_ref:
                row["issue"] = issue_ref
            rows.append((exp_id, row))
    rows.sort(key=lambda t: (t[0], t[1].get("fingerprint", ""), t[1].get("arm", "")))
    files = {"generated/experiments-ledger.jsonl":
             "".join(json.dumps(r, sort_keys=True) + "\n" for _, r in rows)}
    for exp_id in sorted(rows_by_exp):
        if rows_by_exp[exp_id]:
            files[f"generated/experiments/{exp_id}.md"] = leaderboard_markdown(
                data, exp_id, rows_by_exp[exp_id])
    return files


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
          "accident. Post nulls and failures too; they are results. A referee re-run that "
          "reproduces a cell marks it verified with `./z0 exp verify " + e["id"] +
          " --fingerprint <fp>`.", ""]
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
    pld = sub.add_parser("ledger", help="Harvest markers into generated/experiments-ledger.jsonl + leaderboards")
    pld.add_argument("--refresh", action="store_true",
                     help="re-fetch every mapped issue via gh (default: caches + committed ledger)")
    pld.add_argument("--check", action="store_true", help="report stale generated files; write nothing")
    pv = sub.add_parser("verify", help="Mark a measured cell verified (referee re-run)")
    pv.add_argument("id")
    pv.add_argument("--fingerprint", required=True, help="16-hex cell id from a result comment")
    pv.add_argument("--by", default="", help="verifier name (default: the gh login)")
    pv.add_argument("--note", default="")
    pv.add_argument("--yes", action="store_true", help="post the comment (needs the user's explicit yes)")
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
    if a.sub == "ledger":
        rows_by_exp = collect_rows(data, refresh=a.refresh)
        files = build_ledger_files(data, rows_by_exp)
        expected = {k for k in files if k.startswith("generated/experiments/")}
        stale = []
        if LEDGER_MD_DIR.is_dir():
            map_ids = {e["id"] for e in data["experiments"]}
            for f in sorted(LEDGER_MD_DIR.glob("*.md")):
                if f.stem in map_ids and f"generated/experiments/{f.name}" not in expected:
                    stale.append(f)
        if a.check:
            bad = sorted(k for k, c in files.items()
                         if not (ROOT / k).is_file()
                         or (ROOT / k).read_text(encoding="utf-8") != c)
            bad += [f.relative_to(ROOT).as_posix() for f in stale]
            for k in bad:
                print(f"stale: {k}")
            if not bad:
                print("experiments ledger is up to date")
            return 1 if bad else 0
        for rel, content in files.items():
            p = ROOT / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        for f in stale:
            f.unlink()
        n_rows = sum(len(r) for r in rows_by_exp.values())
        print(f"ledger: {n_rows} result rows, {len(expected)} leaderboard(s) -> "
              "generated/experiments-ledger.jsonl"
              + (", generated/experiments/*.md" if expected else ""))
        return 0
    exp = get(data, a.id)
    hw = hardware_class()
    if a.sub == "fingerprint":
        print(fingerprint(exp["id"], exp.get("epoch", 1), a.arm, a.tier, a.data_sha, hw))
        return 0
    if a.sub == "verify":
        if not re.fullmatch(r"[0-9a-f]{16}", a.fingerprint):
            print("INVALID: --fingerprint must be the 16-hex cell id from a result comment")
            return 2
        ledger = fetch_ledger(exp, refresh=True)
        if ledger and a.fingerprint not in {r.get("fingerprint") for r in ledger}:
            print(f"INVALID: no {exp['id']} result row has fingerprint {a.fingerprint}; "
                  "run ./z0 exp ledger --refresh and check the result comment")
            return 2
        v = {"schema": VERIFY_SCHEMA, "exp_id": exp["id"], "fingerprint": a.fingerprint}
        by = a.by or gh_login()
        if by:
            v["by"] = by
        if a.note:
            v["note"] = a.note
        body = verify_comment(exp, v)
        if not a.yes:
            print(body)
            print("\n# Not posted. Re-run with --yes after your user approves the post.")
            return 0
        if not exp.get("issue"):
            print("no issue number in the map for this experiment")
            return 2
        return subprocess.run(["gh", "issue", "comment", str(exp["issue"]), "-R", exp["repo"],
                               "--body", body]).returncode
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
