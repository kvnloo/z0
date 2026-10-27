"""Onboarding rules for scripts/registry-check (design §2.7). Pure: snapshot in, errors out.

Rules:
- R-sync: each legacy install/verify command equals the shell projection of the
  `onboard` steps marked `legacy_projection: true` (an echo-only legacy install
  needs no projection).
- Every step has a closed shape; every `run` has `creates|probe` and a `where`;
  every effectful step declares what it creates or probes (law I1).
- No step names a `configure: never` harness (P1).
- No service has a non-closed bind or a `where` inside a checkout (S1, S2). Harness
  plugins run from a release or an owned venv; a write_file `target_where` (shim, env
  file) points into one (S1).
- Every `when` fact is a fact the host profile can carry (a typo is always false).
- No denylisted literal appears in the registry or in templates (H2).
- Every component in the auto target set has `acceptance`.
- `generated/onboarding-matrix.md` is up to date (checked by the script).
"""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Iterable

from . import regsnap
from .expand import LIST_PLACEHOLDERS, SCALARS, expand_step, leftover_placeholders

ROOT = Path(__file__).resolve().parents[3]
STEP_KEYS = set(json.loads((ROOT / "schemas/onboard-step.schema.json").read_text())["properties"])
HOST_SCHEMA = json.loads((ROOT / "schemas/host-profile.schema.json").read_text())
KINDS = json.loads((ROOT / "schemas/onboard-step.schema.json").read_text())["$defs"]["kind"]["enum"]
WHERE = ("mirror", "build", "release", "venv", "home")
LIVE_ROOTS = ("release", "venv")  # S1: where live code may resolve (decide_exec_root allows)
# Plan facts that are not host.json keys (plan.facts_of).
PLAN_FACTS = {"mode": None, "profile": None, "derived": {"acp_harness": None, "manylinux_2_38": None}}
BINDS = ("loopback", "tailnet_ipv4")
BUNDLES = ("toolchains", "harness", "services", "models")
EFFECTFUL = set(KINDS) - {"check", "ask"}
POLICIES = ("allowed", "ask", "detect_only", "never")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def projection(steps: Iterable[dict], verify: bool) -> str:
    """The shell form of the legacy-projected steps: argv joined, steps joined by &&."""
    parts = [shlex.join(step["argv"]) for step in steps
             if step.get("legacy_projection") and step.get("argv")
             and (step.get("kind") == "check") == verify]
    return " && ".join(parts)


def _dummy_context(cid: str) -> dict:
    ctx = {name: f"<{name}>" for name in SCALARS}
    ctx.update({"id": cid, "tree": "$Z0_HOME/repos/x", "torch_index_args": []})
    return ctx


def literal_pattern(literal: str) -> re.Pattern:
    """`re:<regex>` entries are patterns. Path-like literals match only at a path start:
    `~/workspace/x` is not `/workspace/`."""
    if literal.startswith("re:"):
        return re.compile(literal[3:])
    if literal.startswith("/"):
        return re.compile(r"(?<![\w.~/-])" + re.escape(literal))
    return re.compile(re.escape(literal))


def scan_literals(text: str, literals: Iterable[str]) -> list:
    return sorted({lit for lit in literals if literal_pattern(lit).search(text)})


def _schema_keys(node: dict):
    """The keys a host-profile object may carry: a set, or None when any key goes."""
    if "properties" in node:
        return node["properties"]
    return None


def fact_error(fact: str, snap: dict) -> str:
    """'' when `fact` names something the host profile (or the plan) can carry."""
    from .util import norm_key
    parts = str(fact).split(".")
    head, rest = parts[0], parts[1:]
    if head in PLAN_FACTS:
        node = PLAN_FACTS[head]
        for part in rest:
            if not isinstance(node, dict) or part not in node:
                return f"unknown plan fact {fact!r}"
            node = node[part]
        return ""
    props = HOST_SCHEMA["properties"]
    if head not in props:
        return f"unknown fact root {head!r}"
    names = {
        "network": set((regsnap.onboarding(snap).get("network_probes") or {})),
        "toolchains": {norm_key(t) for t in regsnap.toolchains(snap).get("tools") or {}},
        "harnesses": {norm_key(h) for h in regsnap.harnesses(snap)},
    }
    if head in names:
        if not rest or rest[0] not in names[head]:
            return f"{head} has no key {rest[0] if rest else ''!r} (known: {sorted(names[head])})"
        entry = props[head].get("additionalProperties")
        if len(rest) > 1 and isinstance(entry, dict):
            keys = _schema_keys(entry)
            if keys is not None and rest[1] not in keys:
                return f"{head}.{rest[0]} has no field {rest[1]!r}"
        return ""
    node = props[head]
    for part in rest:
        keys = _schema_keys(node) if isinstance(node, dict) else None
        if keys is None:
            return ""
        if part not in keys:
            return f"{head} has no field {part!r}"
        node = keys[part]
    return ""


def check_step(cid: str, step: dict, never: set, templates: dict, snap: dict = None,
               repo: bool = False) -> list:
    """Rules for one step. `repo`: a zer0.repo.yaml step, whose argv probe also counts
    as its idempotence probe (the registry's own steps must declare a path, law I1)."""
    errors = []
    sid = step.get("id", "?")
    where = f"component {cid} step {sid}"
    for key in ("id", "kind", "consent"):
        if key not in step:
            errors.append(f"{where}: missing {key}")
    extra = set(step) - STEP_KEYS
    if extra:
        errors.append(f"{where}: unknown keys {sorted(extra)}")
    if not str(sid).startswith(f"{cid}."):
        errors.append(f"{where}: id must start with '{cid}.'")
    kind = step.get("kind")
    if kind not in KINDS:
        errors.append(f"{where}: kind {kind!r} is not a closed step kind")
    consent = step.get("consent") or {}
    if consent.get("class") not in ("C0", "C1", "C2"):
        errors.append(f"{where}: consent class must be C0, C1 or C2")
    if consent.get("class") == "C1" and consent.get("bundle") not in BUNDLES:
        errors.append(f"{where}: C1 needs a bundle in {BUNDLES}")
    if kind in ("check", "ask") and consent.get("class") != "C0":
        errors.append(f"{where}: {kind} steps are C0")
    if "where" in step and step["where"] not in WHERE:
        errors.append(f"{where}: where {step['where']!r} not in {WHERE} (S1)")
    if kind == "run":
        if not step.get("argv") or "where" not in step:
            errors.append(f"{where}: run needs argv and where")
        if not step.get("creates") and not step.get("probe"):
            errors.append(f"{where}: run needs creates or probe")
    probe = step.get("probe") or {}
    if kind in EFFECTFUL and not step.get("creates") and not probe.get("exists") \
            and not (repo and probe.get("argv")):
        errors.append(f"{where}: an effectful step declares creates or probe.exists (I1)")
    if kind == "service_unit":
        service = step.get("service") or {}
        if service.get("bind") not in BINDS:
            errors.append(f"{where}: bind {service.get('bind')!r} is not closed (S2)")
        if step.get("where") not in LIVE_ROOTS:
            errors.append(f"{where}: a service runs from a release or an owned venv (S1)")
        template = templates.get(service.get("template"))
        if template is None:
            errors.append(f"{where}: unknown unit template {service.get('template')!r}")
        elif template.get("bind") and template["bind"] != service.get("bind"):
            errors.append(f"{where}: template bind differs from the step bind")
    if kind == "ensure_toolchain" and "toolchain" not in step:
        errors.append(f"{where}: ensure_toolchain needs toolchain")
    if kind == "harness_plugin" and not step.get("harness"):
        errors.append(f"{where}: harness_plugin needs harness")
    if kind == "harness_plugin" and step.get("where") not in LIVE_ROOTS:
        errors.append(f"{where}: a harness plugin links a release or an owned venv, "
                      f"not {step.get('where')!r} (S1)")
    if "target_where" in step and (kind != "write_file" or step["target_where"] not in LIVE_ROOTS):
        errors.append(f"{where}: target_where is for write_file and must be release or venv (S1)")
    if step.get("harness") in never:
        errors.append(f"{where}: names `configure: never` harness {step['harness']} (P1)")
    for cond in step.get("when") or []:
        if not re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)*", str(cond.get("fact", ""))):
            errors.append(f"{where}: when fact {cond.get('fact')!r} is not a fact path")
        elif snap is not None and fact_error(cond["fact"], snap):
            errors.append(f"{where}: when fact {cond['fact']!r}: {fact_error(cond['fact'], snap)}")
    leftovers = [p for p in leftover_placeholders(expand_step(step, _dummy_context(cid)))
                 if "{" + p + "}" not in LIST_PLACEHOLDERS]
    if leftovers:
        errors.append(f"{where}: unknown placeholders {sorted(set(leftovers))}")
    return errors


def auto_target_set(snap: dict) -> list:
    out = []
    for profile in ("core", "personal"):
        if profile in regsnap.profiles(snap):
            out.extend(regsnap.resolve_profile(snap, profile))
    out.extend(regsnap.profile_policy(snap).get("auto_supplementals") or [])
    return list(dict.fromkeys(out))


def check(snap: dict, raw_texts: dict, template_texts: dict) -> list:
    """All onboarding rule violations; `raw_texts` maps registry file -> text."""
    errors: list = []
    comps = regsnap.components(snap)
    harnesses = regsnap.harnesses(snap)
    onboarding = regsnap.onboarding(snap)
    never = {hid for hid, row in harnesses.items()
             if (row.get("policy") or {}).get("configure") == "never"}
    templates = onboarding.get("templates") or {}
    hub_ids = {s["id"] for s in (onboarding.get("hub") or {}).get("steps") or []}
    all_ids = set(hub_ids)
    for cid, comp in comps.items():
        for step in (comp.get("onboard") or {}).get("steps") or []:
            all_ids.add(step.get("id"))

    for cid, comp in comps.items():
        block = comp.get("onboard")
        if block is None:
            errors.append(f"component {cid}: no onboard block")
            continue
        steps = block.get("steps") or []
        seen = set()
        for step in steps:
            errors.extend(check_step(cid, step, never, templates, snap))
            if step.get("id") in seen:
                errors.append(f"component {cid}: duplicate step id {step.get('id')}")
            seen.add(step.get("id"))
            for need in step.get("needs") or []:
                if need not in all_ids and not str(need).startswith("toolchain."):
                    errors.append(f"component {cid} step {step.get('id')}: unknown need {need}")
        for field, verify in (("install", False), ("verify", True)):
            legacy = str(((comp.get(field) or {}).get("command")) or "").strip()
            projected = projection(steps, verify)
            if projected != legacy and not (not projected and (not legacy or (
                    not verify and legacy.startswith("echo ")))):
                errors.append(f"component {cid}: R-sync {field}.command {legacy!r} != "
                              f"projection {projected!r}")
        for tier in (block.get("acceptance") or {}).get("tiers") or []:
            for check_id in tier.get("checks") or []:
                kinds = {s.get("id"): s.get("kind") for s in steps}
                if kinds.get(check_id) != "check":
                    errors.append(f"component {cid}: acceptance names {check_id}, not a check step")
        if block.get("gate") not in (None, "generic", "dash", "z0int"):
            errors.append(f"component {cid}: unknown gate {block.get('gate')!r}")
    for cid in auto_target_set(snap):
        if cid not in comps:
            errors.append(f"auto target {cid} is not a component")
        elif not ((comps[cid].get("onboard") or {}).get("acceptance") or {}).get("tiers"):
            errors.append(f"component {cid}: in the auto target set but has no acceptance")

    for hid, row in harnesses.items():
        policy = row.get("policy") or {}
        if "detect" not in row or "policy" not in row:
            errors.append(f"harness {hid}: needs detect and policy blocks")
        if policy.get("configure") not in POLICIES:
            errors.append(f"harness {hid}: policy.configure must be one of {POLICIES}")
        if hid in ("grok", "cursor-agent") and any(policy.get(key) != "never" for key in
                                                   ("configure", "offload", "exec_probe")):
            errors.append(f"harness {hid}: configure/offload/exec_probe must be never (P1)")

    llm = onboarding.get("llm") or {}
    forbidden = set(llm.get("forbidden") or [])
    if not {"grok", "cursor"} <= forbidden:
        errors.append("onboarding.llm.forbidden must name grok and cursor (P1)")
    for provider in llm.get("providers") or []:
        if provider.get("id") in forbidden:
            errors.append(f"onboarding.llm: forbidden provider {provider.get('id')} listed (P1)")
    if not set(onboarding.get("bind_classes") or []) <= set(BINDS):
        errors.append("onboarding.bind_classes must be within {loopback, tailnet_ipv4} (S2)")

    for tool, spec in (regsnap.toolchains(snap).get("tools") or {}).items():
        install = spec.get("install")
        if install:
            if not install.get("version") or "latest" in str(install.get("version")):
                errors.append(f"toolchain {tool}: install needs a pinned version")
            for target, row in (install.get("targets") or {}).items():
                if not _SHA.match(str(row.get("sha256", ""))):
                    errors.append(f"toolchain {tool} {target}: sha256 missing or malformed")

    literals = ((onboarding.get("denylists") or {}).get("redaction")) or []
    for name, text in sorted(raw_texts.items()):
        body = _strip_denylist(text) if name.endswith("onboarding.yaml") else text
        for lit in scan_literals(body, literals):
            errors.append(f"{name}: denylisted literal {lit!r} (H2)")
    for name, text in sorted(template_texts.items()):
        for lit in scan_literals(text, literals):
            errors.append(f"{name}: denylisted literal {lit!r} (H2)")
    return errors


def check_repo_setup(snap: dict, cid: str, setup: dict) -> list:
    """A repo's `zer0.repo.yaml setup:` block (§2.6) against the registry.

    The registry wins on a duplicate step id, so a repo step that repeats a registry
    step under another id would run twice: same argv, different id is an error. Every
    step passes the registry step rules, and every `when` fact must exist.
    """
    errors = []
    comps = regsnap.components(snap)
    if cid not in comps:
        return [f"setup: {cid!r} is not a registry component"]
    onboarding = regsnap.onboarding(snap)
    never = {hid for hid, row in regsnap.harnesses(snap).items()
             if (row.get("policy") or {}).get("configure") == "never"}
    registry_steps = (comps[cid].get("onboard") or {}).get("steps") or []
    by_argv = {tuple(s["argv"]): s["id"] for s in registry_steps if s.get("argv")}
    for step in (setup or {}).get("steps") or []:
        sid = step.get("id", "?")
        body = {key: value for key, value in step.items() if key != "component"}
        if step.get("component", cid) != cid:
            errors.append(f"setup step {sid}: component must be {cid}")
        errors.extend(check_step(cid, body, never, onboarding.get("templates") or {}, snap,
                                 repo=True))
        twin = by_argv.get(tuple(step.get("argv") or ()))
        if twin and twin != sid:
            errors.append(f"setup step {sid}: same argv as registry step {twin}; use the "
                          "registry id (a different id would run it twice)")
    for tier in (setup or {}).get("tiers") or []:
        for cond in tier.get("when") or []:
            if fact_error(cond.get("fact", ""), snap):
                errors.append(f"setup tier {tier.get('id')}: when fact {cond.get('fact')!r}: "
                              f"{fact_error(cond.get('fact', ''), snap)}")
    return errors


def _strip_denylist(text: str) -> str:
    """onboarding.yaml declares the literals; its `redaction:` list is not a use of them."""
    out, skipping = [], False
    for line in text.splitlines():
        if re.match(r"^\s+redaction:\s*$", line):
            skipping = True
            continue
        if skipping and re.match(r"^\s+- ", line):
            continue
        skipping = False
        out.append(line)
    return "\n".join(out)


def load_texts(root: Path = ROOT) -> tuple:
    raw = {f"registry/{p.name}": p.read_text(encoding="utf-8")
           for p in sorted((root / "registry").glob("*.yaml"))}
    templates = {}
    if (root / "templates").is_dir():
        for path in sorted((root / "templates").rglob("*")):
            if path.is_file():
                templates[str(path.relative_to(root))] = path.read_text(encoding="utf-8",
                                                                        errors="replace")
    return raw, templates
