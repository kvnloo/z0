"""PLAN (design §6.1): a pure function plan(host, registry, answers, mode, grants).

No I/O, no clock, no environment: the same inputs give the same bytes and the same
plan_hash. Every refuse / ask / allow comes from kernel.py; this module only maps
facts to kernel enums, degrades (`unavailable`, `blocked`) and orders.

Step `where` (closed set, §2.5): `mirror` = z0's origin mirror; `build` = the
component's z0 work tree (its build tree when it has one, else the adopt_or_clone
tree: a clean adopted checkout used in place, or the z0-owned clone); `release` =
a stamped release dir; `venv` = an owned venv; `home` = a user-scoped file.
"""
from __future__ import annotations

import copy
import heapq
from typing import Iterable, Optional

from . import kernel as k
from . import regsnap, repo_setup
from .expand import component_context, expand_step, hw_class, select_tree, z0_disk_gib
from .util import canonical_json, norm_key, parse_requirement, sha256_text, version_ge
from .when import describe, first_failure

STATUS_OF_KIND = {k.Kind.ASK: "ask", k.Kind.UNAVAILABLE: "unavailable", k.Kind.REFUSE: "refused"}
NOT_OK = ("ask", "unavailable", "refused", "blocked")
WHERE_ROOT = {"release": k.RootKind.RELEASE, "venv": k.RootKind.OWNED_VENV,
              "build": k.RootKind.BUILD_TREE, "mirror": k.RootKind.CHECKOUT,
              "home": k.RootKind.OTHER}
EFFECTFUL = ("ensure_toolchain", "adopt_or_clone", "build_tree", "stage_release", "swap_current",
             "venv", "pip_install", "run", "write_file", "service_unit", "harness_plugin", "delegate")
# S1: what these kinds point live code at must be a release, an owned venv or a toolchain.
EXEC_ROOT_KINDS = ("service_unit", "harness_plugin")
OK = ("todo", "already_satisfied")
PYTHON_TOOLS = ("python", "python3")
# P1: a shared bin dir that also holds a `configure: never` harness is replaced on the
# prepared PATH by this z0-owned dir of links to the allowed tools that resolved there.
LINK_DIR = "$Z0_HOME/bin/links"


class PlanError(Exception):
    """Invalid inputs (unknown profile or component id)."""


def reason_name(reason: Optional[k.Reason]) -> str:
    return reason.name.lower() if reason is not None else ""


def _state(verdict: k.Verdict) -> dict:
    return {"status": STATUS_OF_KIND[verdict.kind], "reason": reason_name(verdict.reason)}


# --- facts -----------------------------------------------------------------------

def facts_of(host: dict, mode: str, profile: Optional[str]) -> dict:
    facts = copy.deepcopy(host)
    facts["harnesses"] = {norm_key(h): v for h, v in (host.get("harnesses") or {}).items()}
    facts["toolchains"] = {norm_key(t): v for t, v in (host.get("toolchains") or {}).items()}
    facts["mode"], facts["profile"] = mode, profile
    installed = {h for h, v in facts["harnesses"].items() if v.get("state") == "installed"}
    facts["derived"] = {"acp_harness": bool(installed & {"claude_code", "codex"})}
    return facts


def ram_tier(host: dict) -> k.RamTier:
    return k.ram_tier(float((host.get("hardware") or {}).get("ram_gib", 0)))


def py_window(host: dict) -> k.PyWindow:
    raw = str(host.get("python_window") or "impossible").upper()
    return k.PyWindow[raw] if raw in k.PyWindow.__members__ else k.PyWindow.IMPOSSIBLE


def maturity(comp: dict) -> k.Maturity:
    if comp.get("status") == "idea":
        return k.Maturity.IDEA
    if comp.get("execution") == "shadow":
        return k.Maturity.SHADOW
    return k.Maturity.STABLE


def gate(comp: dict) -> k.Gate:
    raw = str((comp.get("onboard") or {}).get("gate") or "generic")
    return {"dash": k.Gate.DASH, "z0int": k.Gate.Z0INT}.get(raw, k.Gate.GENERIC)


def pins(comp: dict) -> list:
    out = []
    ref = (comp.get("install") or {}).get("ref")
    if ref:
        out.append(str(ref))
    for rev in ((comp.get("onboard") or {}).get("revs") or {}).values():
        if rev and str(rev) not in out:
            out.append(str(rev))
    return out


def rev_evidence(comp: dict, host: dict, warnings: list, cid: str) -> tuple:
    """(kernel.RevOrigin, flavour). Any pin disproven on origin -> NO; else any pin not
    checked -> UNKNOWN; else YES. The kernel decides what UNKNOWN means per gate (D1)."""
    revs = host.get("revs") or {}
    states, flavour = [], k.Flavour.CURRENT
    for pin in pins(comp):
        fact = revs.get(pin) or {}
        states.append(fact.get("on_origin", "unknown"))
        if fact.get("on_origin", "unknown") == "unknown" and gate(comp) is not k.Gate.DASH:
            warnings.append(f"{cid}: pin {pin[:12]} not verified on origin (no mirror or "
                            "checkout evidence)")
        if fact.get("flavour") == "legacy":
            flavour = k.Flavour.LEGACY
    if "no" in states:
        return k.RevOrigin.NO, flavour
    if "unknown" in states:
        return k.RevOrigin.UNKNOWN, flavour
    return k.RevOrigin.YES, flavour


def prepared_path(host: dict, snap: dict) -> tuple:
    """(prepared PATH, links) for the plan (§4, P1).

    Every non-system bin dir that holds a `configure: never` harness binary (all of
    detect's `bin_dirs`, not only the first hit) is dropped;
    LINK_DIR takes its place, with one link per allowed registry tool or harness that
    resolved there. A system dir cannot be dropped: that case stays a warning.
    """
    rows = regsnap.harnesses(snap)
    never = {hid for hid, row in rows.items() if (row.get("policy") or {}).get("configure") == "never"}
    system = set((regsnap.toolchains(snap).get("detect") or {}).get("system_dirs") or ["/usr/bin", "/bin"])
    harnesses = host.get("harnesses") or {}
    shared = {directory for hid, entry in harnesses.items() if hid in never
              for directory in (entry.get("bin_dirs") or [entry.get("bin_dir")]) if directory} - system
    out, links = [], []
    for directory in host.get("prepared_path") or []:
        if directory not in shared:
            out.append(directory)
            continue
        if LINK_DIR not in out:
            out.append(LINK_DIR)
        found = [entry.get("path") for entry in (host.get("toolchains") or {}).values()
                 if entry.get("state") == "present"]
        found += [entry.get("path") for hid, entry in harnesses.items()
                  if hid not in never and entry.get("state") == "installed"]
        for path in sorted({p for p in found if p and p.rsplit("/", 1)[0] == directory}):
            links.append({"link": f"{LINK_DIR}/{path.rsplit('/', 1)[1]}", "target": path})
    return out, links


# --- registry -> step list ---------------------------------------------------------

def _tool_specs(snap: dict) -> dict:
    return regsnap.toolchains(snap).get("tools") or {}


def _canonical_tool(tool: str, specs: dict) -> str:
    if tool in PYTHON_TOOLS:
        return "python3"
    provider = (specs.get(tool) or {}).get("provided_by")
    return provider or tool


def toolchain_steps(targets: list, comps: dict, snap: dict, host: dict) -> tuple:
    """Shared `toolchain.<tool>` steps for every required tool, plus the needs edges."""
    specs = _tool_specs(snap)
    minimums: dict = {}
    users: dict = {}
    def add(tool, minimum):
        if minimum and (minimums.get(tool) is None or version_ge(minimum, minimums[tool])):
            minimums[tool] = minimum
        minimums.setdefault(tool, None)

    for cid in targets:
        block = comps[cid].get("onboard") or {}
        requires = block.get("requires") or {}
        for req in requires.get("tools") or []:
            tool, minimum = parse_requirement(str(req))
            tool = "python-window" if tool == "python-window" else _canonical_tool(tool, specs)
            users.setdefault(tool, []).append(cid)
            add(tool, minimum)
        # An optional tool is planned only when a step names it in `needs`; it then
        # blocks that step alone, not the whole component.
        wanted = {n.split(".", 1)[1] for s in block.get("steps") or []
                  for n in s.get("needs") or [] if str(n).startswith("toolchain.")}
        for req in requires.get("optional") or []:
            tool, minimum = parse_requirement(str(req))
            tool = _canonical_tool(tool, specs)
            if tool in wanted:
                users.setdefault(tool, [])
                add(tool, minimum)
    steps = []
    for tool in sorted(minimums):
        spec = specs.get("python3" if tool == "python-window" else tool) or {}
        install = spec.get("install") or {}
        step = {"id": f"toolchain.{tool}", "component": "z0", "kind": "ensure_toolchain",
                "consent": {"class": "C0"}}
        if tool == "python-window":
            step["toolchain"] = {"tool": "python", "version": str((spec.get("via_uv") or {})
                                                                 .get("z0int_prefer", "3.11"))}
            step["consent"] = {"class": "C1", "bundle": "toolchains"}
            step["network"] = True
        elif tool == "python3":
            step["toolchain"] = {"tool": "python", "version": str((spec.get("via_uv") or {})
                                                                 .get("version", "3.12"))}
            step["consent"] = {"class": "C1", "bundle": "toolchains"}
            step["network"] = True
        elif install.get("version"):
            version = str(install["version"])
            step["toolchain"] = {"tool": tool, "version": version}
            step["consent"] = {"class": "C1", "bundle": "toolchains"}
            step["network"] = True
            step["creates"] = [f"$Z0_HOME/toolchains/{tool}/{version}"]
            step["undo"] = {"kind": "remove_owned"}
        else:
            step["toolchain"] = {"tool": tool, "version": "system"}
        steps.append((step, minimums[tool], sorted(set(users.get(tool, [])))))
    return steps


def target_set(snap: dict, profile: Optional[str], mode: str, with_ids: Iterable[str],
               without_ids: Iterable[str]) -> list:
    comps = regsnap.components(snap)
    policy = regsnap.profile_policy(snap)
    chosen = regsnap.resolve_profile(snap, profile) if profile else []
    for cid in policy.get("auto_supplementals") or []:
        if cid not in chosen:
            chosen.append(cid)
    for cid in with_ids:
        if cid not in comps:
            raise PlanError(f"unknown component: {cid}")
        if cid not in chosen:
            chosen.append(cid)
    for cid in without_ids:
        if cid not in comps:
            raise PlanError(f"unknown component: {cid}")
    return [cid for cid in chosen if cid not in set(without_ids)]


def component_order(snap: dict, targets: list) -> list:
    """depends_on first (O1), then the §8.1 order hint, then registry order."""
    comps = regsnap.components(snap)
    hint = regsnap.profile_policy(snap).get("order") or ["*"]
    registry_index = {cid: i for i, cid in enumerate(comps)}

    def rank(cid):
        position = hint.index(cid) if cid in hint else hint.index("*") if "*" in hint else len(hint)
        return (position, registry_index.get(cid, 0))

    ordered, placed = [], set()
    pending = sorted(targets, key=rank)
    while pending:
        for cid in pending:
            deps = [d for d in comps[cid].get("depends_on") or [] if d in targets]
            if all(d in placed for d in deps):
                ordered.append(cid)
                placed.add(cid)
                pending.remove(cid)
                break
        else:
            raise PlanError(f"depends_on cycle among {pending}")
    return ordered


def topo(steps: list, edges: dict) -> list:
    """Stable topological order: among ready steps, the earliest declared goes first."""
    index = {s["id"]: i for i, s in enumerate(steps)}
    indegree = {s["id"]: 0 for s in steps}
    children: dict = {s["id"]: [] for s in steps}
    for sid, deps in edges.items():
        for dep in deps:
            if dep in index and sid in index and dep != sid:
                indegree[sid] += 1
                children[dep].append(sid)
    ready = [(index[sid], sid) for sid, deg in indegree.items() if deg == 0]
    heapq.heapify(ready)
    out = []
    while ready:
        _, sid = heapq.heappop(ready)
        out.append(sid)
        for child in children[sid]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, (index[child], child))
    if len(out) != len(steps):
        raise PlanError("cycle in step needs")
    by_id = {s["id"]: s for s in steps}
    return [by_id[sid] for sid in out]


# --- states ----------------------------------------------------------------------

def _tool_satisfied(step: dict, minimum: Optional[str], host: dict) -> bool:
    tool = step["id"].split(".", 1)[1]
    if tool == "python-window":
        return host.get("python_window") == "present"
    # python3 (T1): the interpreter the steps run must itself be present, resolve under
    # the prepared PATH and meet the requirement. A window python elsewhere (python3.12
    # off the PATH, or z0int's) does not make `python3` work.
    fact = (host.get("toolchains") or {}).get(tool) or {}
    if fact.get("state") != "present" or fact.get("sh_resolves") is False:
        return False
    return minimum is None or version_ge(fact.get("version"), minimum)


def _satisfied(step: dict, host: dict, owned: set, comp_tree: dict) -> bool:
    kind = step["kind"]
    if kind == "adopt_or_clone" and comp_tree.get("adopted"):
        return True
    probe = (step.get("probe") or {}).get("exists")
    paths = [probe] if probe else list(step.get("creates") or [])
    return bool(paths) and all(path in owned for path in paths)


def _bind_ip(host: dict) -> k.IpSource:
    return k.IpSource.CURRENT if (host.get("tailscale") or {}).get("ipv4") else k.IpSource.NONE


def _adopted_unit(step: dict, host: dict) -> Optional[dict]:
    unit = (step.get("service") or {}).get("unit")
    for entry in (host.get("services") or {}).get("units") or []:
        if unit and entry.get("name") == unit:
            return entry
    return None


def _z0_mount(host: dict) -> str:
    disks = (host.get("hardware") or {}).get("disks") or []
    for disk in disks:
        if "z0_home" in (disk.get("role") or []):
            return str(disk.get("mount", "$Z0_HOME"))
    return str(disks[0].get("mount", "$Z0_HOME")) if disks else "$Z0_HOME"


# What the plan tells a zero-context reader for each unavailable reason (§1.2).
REASON_TEXT = {
    "rev_not_on_origin": "the pinned revs are not on origin yet (maintainer must push them)",
    "rev_unverified": "could not check the pinned revs on origin; re-run `./z0 onboard plan` "
                      "with network so z0 can fetch them into its mirror",
    "legacy_flavour": "the pinned rev is the legacy flavour (0.0.0.0 bind, Expo Go); never deployed",
    "intel_mac": "no torch 2.10 wheel for Intel macOS",
    "python_window": "no python in [3.10, 3.14) is present or can be made",
    "ram_low": "needs at least 8 GiB RAM",
    "idea": "status idea; never installed",
    "no_tailnet": "no tailnet IPv4 on this host",
    "host_mismatch": "host.json was recorded on another host",
    "through_checkout": "would run live code from a checkout or build tree (S1)",
    "outside_roots": "would point live code outside releases, owned venvs and toolchains (S1)",
    "open_bind": "bind outside loopback and the current tailnet IPv4 (S2)",
    "forbidden_provider": "grok and cursor are never configured (P1)",
    "c2_never_auto": "never automatic in --auto",
    "c2_confirm": "needs your per-step confirmation",
    "shadow": "shadow component",
}


def explain(reason: str, host: dict) -> str:
    """One line for a state reason (kernel codes, hardware gaps, conditions)."""
    if reason.startswith("hardware:disk<"):
        need = reason.split("<", 1)[1].replace("GiB", "")
        return (f"disk < {need} GiB free at {_z0_mount(host)}; free space or set Z0_HOME "
                "on a larger volume")
    if reason.startswith("hardware:ram<"):
        return f"needs at least {reason.split('<', 1)[1].replace('GiB', '')} GiB RAM"
    if reason.startswith("hardware:"):
        return f"not supported on this {reason[len('hardware:'):]}"
    if reason.startswith("condition:"):
        return f"condition not met: {reason[len('condition:'):]}"
    if reason.startswith("missing_tool:"):
        return f"{reason.split(':', 1)[1]} is not installed"
    return REASON_TEXT.get(reason, reason)


def _c1_reason(step: dict) -> str:
    """One line for an ungranted C1 step: what it writes and that it needs consent."""
    kind, bundle = step["kind"], step["consent"].get("bundle", "")
    if kind == "ensure_toolchain":
        tool, version = step["toolchain"]["tool"], step["toolchain"]["version"]
        if tool == "python":
            what = f"user-local CPython {version} (via uv) under $Z0_HOME/toolchains"
        else:
            what = f"user-local download of {tool} {version} into $Z0_HOME/toolchains"
    elif kind == "harness_plugin":
        what = (f"{step.get('harness')} integration for {step['component']} "
                "(the harness config is backed up first)")
    elif kind == "service_unit":
        service = step.get("service") or {}
        what = f"user service {service.get('unit', step['id'])} on {service.get('bind')}:{service.get('port')}"
    elif kind == "write_file":
        what = f"writes {(step.get('creates') or [step['id']])[0]}"
    elif kind == "swap_current":
        what = f"points {(step.get('creates') or [step['id']])[0]} at the new release"
    elif kind == "pip_install":
        what = f"installs {' '.join((step.get('argv') or [])[2:])} into the {step['component']} venv"
    else:
        what = f"runs {' '.join(step.get('argv') or [kind])} for {step['component']}"
    return f"{what} (needs consent: {bundle} bundle)"


def _hardware_gap(comp: dict, host: dict) -> Optional[str]:
    hw = (comp.get("onboard") or {}).get("hardware") or {}
    osinfo = host.get("os") or {}
    if hw.get("os") and osinfo.get("os") not in hw["os"]:
        return f"hardware:os {osinfo.get('os')}"
    if hw.get("arch") and osinfo.get("arch") not in hw["arch"]:
        return f"hardware:arch {osinfo.get('arch')}"
    if hw.get("min_disk_gib") and z0_disk_gib(host) < float(hw["min_disk_gib"]):
        return f"hardware:disk<{hw['min_disk_gib']}GiB"
    ram = float((host.get("hardware") or {}).get("ram_gib", 0))
    if hw.get("min_ram_gib") and ram < float(hw["min_ram_gib"]) and gate(comp) is not k.Gate.Z0INT:
        return f"hardware:ram<{hw['min_ram_gib']}GiB"
    return None


def component_steps(cid: str, comp: dict, setups: dict, pin: str) -> tuple:
    """(raw steps, conflicts, warnings): the registry's steps plus the repo-local
    `zer0.repo.yaml setup:` steps read at the pin (§2.6; the registry wins)."""
    steps = list((comp.get("onboard") or {}).get("steps") or [])
    entry = setups.get(cid)
    if not entry:
        return steps, [], []
    if entry.get("ref") != pin:
        return steps, [], [f"{cid}: zer0.repo.yaml setup was read at {str(entry.get('ref'))[:12]}, "
                           f"not at the pin {pin[:12]}; ignored"]
    errors = [f"{cid}: zer0.repo.yaml setup: {error}" for error in entry.get("errors") or []]
    if not repo_setup.usable(entry, pin):
        return steps, [], errors
    added, conflicts, warnings = repo_setup.merge(cid, steps, entry)
    return steps + added, conflicts, warnings + errors


def collect_questions(host: dict, snap: dict) -> list:
    """Unknowns from DETECT, closed against registry evidence; no provider I/O."""
    from .llm.questions import collect
    return collect(host, snap)


def plan(host: dict, snap: dict, *, mode: str = "auto", profile: Optional[str] = None,
         with_ids: Iterable[str] = (), without_ids: Iterable[str] = (),
         grants: Optional[dict] = None, pin_policy: str = "pinned", llm: str = "local",
         answers: Optional[dict] = None, repo_setups: Optional[dict] = None) -> dict:
    """`repo_setups`: {component: vetted setup entry} from the origin mirrors (§2.6);
    defaults to the snapshot's `repo_setups` (filled by the CLI after the fetch)."""
    with_ids, without_ids = list(with_ids), list(without_ids)
    setups = (snap.get("repo_setups") or {}) if repo_setups is None else repo_setups
    grants = grants or {"bundles": [], "source": "none"}
    comps = regsnap.components(snap)
    onboarding = regsnap.onboarding(snap)
    kmode = k.Mode.AUTO if mode == "auto" else k.Mode.GUIDED
    warnings: list = []

    host_verdict = k.decide_host(k.HostMatch[str((host.get("workspace") or {})
                                                 .get("host_match", "fresh")).upper()])
    if profile is None:
        decided = k.decide_profile(ram_tier(host), k.disk_tier(z0_disk_gib(host)), hw_class(host),
                                   py_window(host))
        profile = {k.Profile.PERSONAL: "personal", k.Profile.CORE: "core"}.get(decided)
        if profile is None:
            warnings.append("profile: refused (disk < 3 GiB at $Z0_HOME); free space or pass --profile")
    if profile and profile not in regsnap.profiles(snap):
        raise PlanError(f"unknown profile: {profile}")
    if profile in ("research", "full") and ram_tier(host) in (k.RamTier.R8_16, k.RamTier.R4_8,
                                                             k.RamTier.LT4):
        warnings.append(f"profile {profile}: RAM below 16 GiB")
    targets = component_order(snap, target_set(snap, profile, mode, with_ids, without_ids))
    facts = facts_of(host, mode, profile)
    owned = set((host.get("workspace") or {}).get("owned") or [])

    # component verdicts (kernel) and per-component contexts
    verdicts, trees, contexts, summary = {}, {}, {}, {}
    path_dirs, path_links = prepared_path(host, snap)
    path_text = ":".join(path_dirs)
    for cid in targets:
        comp = comps[cid]
        rev, flavour = rev_evidence(comp, host, warnings, cid)
        verdict = k.decide_component(gate(comp), rev, flavour, maturity(comp),
                                     hw_class(host), py_window(host), ram_tier(host))
        dep_bad = [d for d in comp.get("depends_on") or [] if d in verdicts
                   and verdicts[d].kind in (k.Kind.REFUSE, k.Kind.UNAVAILABLE)]
        verdicts[cid] = verdict
        contexts[cid] = component_context(cid, comp, host, onboarding, profile)
        contexts[cid]["prepared_path"] = path_text
        trees[cid] = select_tree(comp, host)
        entry = {"verdict": verdict.kind.name.lower()}
        if verdict.reason is not None:
            entry["reason"] = reason_name(verdict.reason)
        if dep_bad:
            entry["blocked_by"] = dep_bad[0]
        if comp.get("onboard", {}).get("steps"):
            entry["tree"] = trees[cid]["tree"]
            entry["adopted"] = trees[cid]["adopted"]
        summary[cid] = entry
        if trees[cid]["dirty_candidates"] and not trees[cid]["adopted"]:
            warnings.append(f"{cid}: {trees[cid]['dirty_candidates']} existing checkout(s) are "
                            "dirty or off-origin; a separate z0 clone is planned instead")

    # steps: hub, toolchains, components
    steps, minimums, owner = [], {}, {}
    edges: dict = {}
    hub = ((onboarding.get("hub") or {}).get("steps") or [])
    if path_links:
        steps.append({"id": "z0.path_links", "component": "z0", "kind": "write_file",
                      "consent": {"class": "C0"}, "where": "home", "creates": [LINK_DIR],
                      "effects": [{"path": link["link"], "kind": "symlink"} for link in path_links],
                      "undo": {"kind": "remove_owned"}})
        owner["z0.path_links"] = None
        warnings.append(f"prepared PATH: {', '.join(sorted({l['target'].rsplit('/', 1)[0] for l in path_links}))} "
                        f"also holds a policy-excluded harness; {LINK_DIR} replaces it (P1)")
    for raw in hub:
        step = expand_step(raw, {"profile": profile or "", "prepared_path": path_text})
        step["component"] = "z0"
        steps.append(step)
        owner[step["id"]] = None
    tool_steps = toolchain_steps(targets, comps, snap, host)
    tool_users: dict = {}
    for step, minimum, users in tool_steps:
        steps.append(step)
        minimums[step["id"]] = minimum
        owner[step["id"]] = None
        for cid in users:
            tool_users.setdefault(cid, []).append(step["id"])
    conflicts: list = []
    provenance = dict(snap.get("files") or {})
    for cid in targets:
        raws, found, notes_setup = component_steps(cid, comps[cid], setups, contexts[cid]["pin"])
        conflicts += found
        warnings += notes_setup
        if repo_setup.usable(setups.get(cid), contexts[cid]["pin"]) and setups[cid].get("sha256"):
            provenance[repo_setup.source_key(setups[cid])] = setups[cid]["sha256"]
        for raw in raws:
            step = expand_step(raw, contexts[cid])
            step["component"] = cid
            steps.append(step)
            owner[step["id"]] = cid
    ids = {s["id"] for s in steps}
    first_of = {}
    for step in steps:
        cid = owner[step["id"]]
        needs = [n for n in step.get("needs") or [] if n in ids]
        if cid is not None:
            # fetching a component's source needs only git: an ungranted runtime toolchain
            # (python window, bun, node) must not stop the C0 clone (degrade, don't fail)
            tools = tool_users.get(cid, [])
            if step["kind"] == "adopt_or_clone":
                tools = [t for t in tools if t == "toolchain.git"]
            needs += tools
            first_of.setdefault(cid, step["id"])
        edges[step["id"]] = needs
    # depends_on: a dependency's steps all precede the dependent's (ordering only).
    comp_steps: dict = {}
    for step in steps:
        if owner[step["id"]] is not None:
            comp_steps.setdefault(owner[step["id"]], []).append(step["id"])
    ordering = {sid: list(deps) for sid, deps in edges.items()}
    for cid in targets:
        for dep in comps[cid].get("depends_on") or []:
            for sid in comp_steps.get(cid, []):
                ordering[sid] = ordering[sid] + comp_steps.get(dep, [])
    ordered = topo(steps, ordering)

    # states
    states: dict = {}
    effective_class: dict = {}
    notes: dict = {}
    grant_source = {"tty": k.Source.TTY, "flag": k.Source.FLAG}.get(grants.get("source"),
                                                                    k.Source.FLAG)
    kinds = {s["id"]: s["kind"] for s in steps}
    # Per-step C2 confirmations from a guided TTY run (answers.yaml `confirmed_steps`).
    confirmed = set((answers or {}).get("confirmed_steps") or []) if "llm" not in (answers or {}) else set()
    dep_blocker: dict = {}

    def dependency_blocker(cid: str) -> Optional[str]:
        """§3/§6.1 blocked(dep) over depends_on: a dependency whose acceptance checks
        cannot run (or, without acceptance, none of whose effectful steps can) blocks
        its dependents. Its steps all precede the dependent's in `ordered`."""
        if cid not in dep_blocker:
            dep_blocker[cid] = None
            for dep in comps[cid].get("depends_on") or []:
                own = comp_steps.get(dep) or []
                checks = [sid for tier in ((comps[dep].get("onboard") or {}).get("acceptance")
                                           or {}).get("tiers") or []
                          for sid in tier.get("checks") or [] if sid in own]
                if checks:
                    bad = [sid for sid in checks if states[sid]["status"] not in OK]
                    if bad:
                        dep_blocker[cid] = bad[0]
                        break
                    continue
                effectful = [sid for sid in own if kinds[sid] in EFFECTFUL]
                if effectful and not any(states[sid]["status"] in OK for sid in effectful):
                    dep_blocker[cid] = effectful[0]
                    break
        return dep_blocker[cid]

    for step in ordered:
        sid, cid = step["id"], owner[step["id"]]
        comp = comps.get(cid) if cid else None
        cls = k.ConsentClass[step["consent"]["class"]]
        state = None
        if host_verdict.kind is not k.Kind.ALLOW:
            state = _state(host_verdict)
        elif comp is not None and verdicts[cid].kind is not k.Kind.ALLOW:
            state = _state(verdicts[cid])
        elif comp is not None and summary[cid].get("blocked_by"):
            state = {"status": "blocked", "reason": "dependency", "blocked_by":
                     first_of.get(summary[cid]["blocked_by"], summary[cid]["blocked_by"])}
        elif comp is not None and _hardware_gap(comp, host):
            state = {"status": "unavailable", "reason": _hardware_gap(comp, host)}
        elif comp is not None and dependency_blocker(cid):
            state = {"status": "blocked", "reason": "dependency", "blocked_by": dependency_blocker(cid)}
        # S1: units, plugins and the env/shim files that point at live code resolve only
        # into releases, owned venvs or toolchains (decide_exec_root), never a checkout.
        roots = []
        if step["kind"] in EXEC_ROOT_KINDS:
            roots.append(step.get("where"))
        if step["kind"] == "write_file" and step.get("target_where"):
            roots.append(step["target_where"])
        checks = [k.decide_exec_root(WHERE_ROOT.get(root, k.RootKind.OTHER)) for root in roots]
        if step["kind"] == "service_unit":
            service = step.get("service") or {}
            bind = {"loopback": k.BindClass.LOOPBACK,
                    "tailnet_ipv4": k.BindClass.TAILNET_IPV4}.get(service.get("bind"),
                                                                 k.BindClass.WILDCARD)
            checks.append(k.decide_bind(bind, _bind_ip(host)))
        for verdict in checks if state is None else ():
            if verdict.kind is not k.Kind.ALLOW:
                state = _state(verdict)
                break
        if state is None and step.get("harness"):
            provider = k.provider_from_id(step["harness"])
            if provider in k.FORBIDDEN_PROVIDERS:
                state = _state(k.decide_provider(provider))
        if state is None:
            failed = first_failure(step.get("when"), facts)
            if failed is not None:
                state = {"status": "unavailable", "reason": f"condition:{describe(failed)}"}
        if state is None:
            for dep in edges.get(sid, []):
                if states.get(dep, {}).get("status") in NOT_OK:
                    state = {"status": "blocked", "reason": "dependency", "blocked_by": dep}
                    break
        if state is None and step["kind"] == "ensure_toolchain":
            if _tool_satisfied(step, minimums.get(sid), host):
                state = {"status": "already_satisfied"}
            elif step["toolchain"]["version"] == "system":
                state = {"status": "unavailable", "reason": f"missing_tool:{step['toolchain']['tool']}"}
            elif sid in ("toolchain.python-window", "toolchain.python3") \
                    and host.get("python_window") == "impossible":
                state = {"status": "unavailable", "reason": "python_window"}
        # S3: an existing unit with the same name is adopted (kept) or asked, never
        # created again. The kernel decides (decide_adopt); its probe path existing says
        # nothing about which SHA runs, so the `_satisfied` probe check is skipped.
        unit = _adopted_unit(step, host) if step["kind"] == "service_unit" else None
        if state is None and unit is not None:
            target = contexts[cid]["rev_bridge"] if gate(comp) is k.Gate.DASH else contexts[cid]["pin"]
            deployed = str(unit.get("deployed_sha") or "")
            adopt = k.decide_adopt(True, bool(deployed) and target.startswith(deployed))
            if adopt.kind is k.Kind.ALLOW:
                state = {"status": "already_satisfied"}
            else:
                cls = k.ConsentClass.C2  # redeploying an adopted unit at another SHA
                step["consent"] = {"class": "C2"}
                notes[sid] = (f"adopted {unit.get('name')} runs "
                              f"{deployed[:12] or 'an unknown SHA'}; redeploying it is C2")
        if state is None and unit is None and step["kind"] in EFFECTFUL \
                and _satisfied(step, host, owned, trees.get(cid) or {}):
            state = {"status": "already_satisfied"}
        if state is None and step["kind"] == "ask":
            state = {"status": "ask", "reason": "manual"}
            cls = k.ConsentClass.C2
        if state is None and step["kind"] != "check":
            if cls is k.ConsentClass.C2:
                # §3: C2 is confirmed per step on a TTY, never by a bundle grant.
                granted = grants.get("source") == "tty" and sid in confirmed
            else:
                granted = (step["consent"].get("bundle") in (grants.get("bundles") or [])
                           and ("steps" not in grants or sid in grants["steps"]))
            verdict = k.decide_consent(kmode, cls, granted, grant_source)
            if verdict.kind is not k.Kind.ALLOW:
                state = _state(verdict)
        states[sid] = state or {"status": "todo"}
        effective_class[sid] = cls.value

    for cid, blocker in dep_blocker.items():
        if blocker:
            summary[cid].setdefault("blocked_by", owner[blocker])

    # asks, ranked by impact (how many steps wait on them)
    dependents: dict = {sid: set() for sid in states}
    for sid, deps in edges.items():
        for dep in deps:
            if dep in dependents:
                dependents[dep].add(sid)

    def impact(sid):
        seen, stack = set(), [sid]
        while stack:
            for child in dependents.get(stack.pop(), ()):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return len(seen) + 1

    def root_of(sid: str) -> str:
        """Follow blocked_by to the step that is not itself blocked."""
        seen = set()
        while states[sid]["status"] == "blocked" and states[sid].get("blocked_by") in states \
                and sid not in seen:
            seen.add(sid)
            sid = states[sid]["blocked_by"]
        return sid

    def askable(sid: str) -> bool:
        """An ask resolves it: consent, a system package, or `tailscale up`."""
        state = states[sid]
        return state["status"] == "ask" or (state["status"] == "unavailable" and (
            state["reason"].startswith("missing_tool:") or state["reason"] == "no_tailnet"))

    # A component none of whose steps can run, for a reason no ask would fix (§1.2
    # "What is unavailable, and why"). Waiting on an ask is not unavailable.
    unavailable = []
    dead = set()
    for cid in targets:
        own = comp_steps.get(cid) or []
        if not own or any(states[sid]["status"] in OK or states[sid]["status"] == "ask"
                          for sid in own):
            continue
        roots = [root_of(sid) for sid in own]
        if any(askable(root) for root in roots):
            continue
        dead.add(cid)
        # The first step's root cause is why nothing of the component can run.
        state = states[own[0]]
        if state["status"] == "blocked":
            root = roots[0]
            detail = (f"blocked: needs {root} ({states[root]['status']}: "
                      f"{explain(states[root].get('reason', ''), host)})")
            reason = "dependency"
        else:
            reason = state["reason"]
            detail = explain(reason, host)
        unavailable.append({"id": cid, "status": state["status"], "reason": reason,
                            "detail": detail})

    pkg_cmds = regsnap.toolchains(snap).get("system_pkg_commands") or {}
    pkg_mgr = (host.get("os") or {}).get("pkg_manager", "none")
    users: dict = {}
    for sid, deps in edges.items():
        for dep in deps:
            if dep.startswith("toolchain.") and owner.get(sid):
                users.setdefault(dep, set()).add(owner[sid])
    asks, seen_component = [], set()
    by_id = {s["id"]: s for s in ordered}
    for sid, state in states.items():
        step, cid = by_id[sid], owner[sid]
        if sid.startswith("toolchain.") and users.get(sid) and users[sid] <= dead:
            continue  # every user of this tool is unavailable anyway: no ask
        if state["status"] == "ask":
            if cid is not None and verdicts[cid].kind is k.Kind.ASK:
                if cid in seen_component:
                    continue
                seen_component.add(cid)
                asks.append({"id": cid, "consent": "C2",
                             "reason": f"{reason_name(verdicts[cid].reason)}: never installed "
                                       "automatically (C2)",
                             "command": f"manual: review https://github.com/{comps[cid].get('repo')} "
                                        "and install it yourself if you need it",
                             "impact": len(comp_steps.get(cid, []))})
                continue
            consent = "C2" if effective_class[sid] == "C2" else "C1"
            entry = {"id": sid, "consent": consent, "impact": impact(sid)}
            if step["kind"] == "ask":
                text = " ".join(step.get("argv", [])[1:]) if step.get("argv") else sid
                entry.update(reason="manual step, never automatic (C2)", command=f"manual: {text}")
            elif consent == "C1":
                bundle = step["consent"].get("bundle", "")
                entry.update(reason=_c1_reason(step),
                             command=f"./z0 onboard --accept {bundle}   (or --yes for every bundle)")
            elif sid in notes:
                entry.update(reason=f"{notes[sid]} (C2)",
                             command="manual: keep the running unit, or redeploy it yourself "
                                     "at the pinned SHA")
            else:
                entry.update(reason=f"{explain(state['reason'], host)} (C2)",
                             command=f"manual: {sid} is never automatic; do it yourself if you want it")
            asks.append(entry)
        elif state["status"] == "unavailable" and state["reason"].startswith("missing_tool:"):
            tool = state["reason"].split(":", 1)[1]
            pkg = ((_tool_specs(snap).get(tool) or {}).get("system_pkg") or {}).get(pkg_mgr, tool)
            command = str(pkg_cmds.get(pkg_mgr, pkg_cmds.get("none", "install {pkg}"))).format(pkg=pkg)
            asks.append({"id": sid, "reason": f"{tool} is not installed (system package, C2)",
                         "consent": "C2", "command": command, "impact": impact(sid)})
        elif state["status"] == "unavailable" and state["reason"] == "no_tailnet":
            asks.append({"id": sid, "reason": "no tailnet IPv4 on this host (C2)", "consent": "C2",
                         "command": "tailscale up, then re-run ./z0 onboard",
                         "impact": impact(sid)})
    asks.sort(key=lambda a: (-a["impact"], a["id"]))

    result = {
        "version": 1,
        "host_id": host.get("host_id", "0" * 16),
        "mode": mode,
        "profile": profile or "",
        "pin_policy": pin_policy,
        "llm": llm,
        "grants": {"bundles": sorted(set(grants.get("bundles") or [])),
                   "source": grants.get("source", "none"),
                   **({"steps": sorted(set(grants["steps"]))} if "steps" in grants else {})},
        "registry": dict(sorted(provenance.items())),
        "targets": targets,
        "components": summary,
        "prepared_path": path_dirs,
        "steps": [{"step": step, "state": states[step["id"]]} for step in ordered],
        "asks": asks,
        "unavailable": unavailable,
        "warnings": sorted(set(warnings)),
    }
    if path_links:
        result["path_links"] = path_links
    if conflicts:
        result["conflicts"] = sorted(conflicts, key=lambda c: (c["component"], c["id"]))
    if grants.get("llm_providers"):
        result["grants"]["llm_providers"] = sorted(set(grants["llm_providers"]))
    if (answers or {}).get("llm"):
        from .llm.resolve import validate_record
        questions = {q.id: q for q in collect_questions(host, snap)}
        records = (answers or {})["llm"]
        if any(qid not in questions or not validate_record(questions[qid], row)
               for qid, row in records.items()):
            raise PlanError("invalid LLM answers")
        # Advisory only: answers cannot mutate host facts, steps, paths or states.
        result["llm_decisions"] = [copy.deepcopy(records[qid]) for qid in sorted(records)]
    if answers:
        result["answers_sha256"] = sha256_text(canonical_json(answers))
    result["plan_hash"] = plan_hash(result)
    return result


def plan_hash(plan_obj: dict) -> str:
    body = {key: value for key, value in plan_obj.items() if key != "plan_hash"}
    return sha256_text(canonical_json(body))


def todo_ids(plan_obj: dict, effectful_only: bool = True) -> list:
    """Steps still to do. Checks write nothing, so law I1 counts effectful steps only."""
    return [entry["step"]["id"] for entry in plan_obj["steps"]
            if entry["state"]["status"] == "todo"
            and (not effectful_only or entry["step"]["kind"] in EFFECTFUL)]


def exit_code(plan_obj: dict) -> int:
    """4 when a law refused the run as a whole (host mismatch, no profile possible)."""
    if any(entry["state"].get("reason") == "host_mismatch" for entry in plan_obj["steps"]):
        return 4
    if not plan_obj.get("profile"):
        return 4
    return 0
