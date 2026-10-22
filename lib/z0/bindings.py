"""Native config reconciliation and observations. No service or stage mutation."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import difflib
import io
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import tempfile
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ruamel.yaml import YAML
import tomlkit
import yaml

from . import registry

HARNESSES = ("hermes", "claude", "codex", "omp")
MCP_KEYS = {"hermes": "mcp_servers", "claude": "mcpServers",
            "codex": "mcp_servers", "omp": "mcpServers"}
VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
SENSITIVE = re.compile(r"token|secret|password|credential|api[_-]?key|authorization", re.I)


@dataclass(frozen=True)
class Target:
    harness: str
    profile: str
    path: Path

    @property
    def label(self) -> str:
        return f"{self.harness}/{self.profile}"


@dataclass
class Plan:
    target: Target
    original: str
    rendered: str
    diff: str
    changed: bool
    existed: bool
    signature: tuple[int, int, int, int] | None


def local_host(host: str | None) -> str:
    actual = socket.gethostname()
    if host and host not in {actual, actual.split(".")[0], socket.getfqdn(), "localhost"}:
        raise ValueError("--host must name this host; remote config access is not supported")
    return actual


def targets(home: Path, harness: str | None = None,
            harness_profile: str | None = None) -> list[Target]:
    if harness and harness not in HARNESSES:
        raise ValueError("unsupported harness")
    if harness_profile and harness != "hermes":
        raise ValueError("--harness-profile requires --harness hermes")
    result = []
    for hid in (harness,) if harness else HARNESSES:
        if hid == "hermes":
            result.append(Target(hid, "default", home / ".hermes/config.yaml"))
            result.extend(Target(hid, path.parent.name, path)
                          for path in sorted((home / ".hermes/profiles").glob("*/config.yaml")))
        else:
            path = {"claude": ".claude.json", "codex": ".codex/config.toml",
                    "omp": ".omp/agent/mcp.json"}[hid]
            result.append(Target(hid, "global", home / path))
    # A named Hermes profile called default can exist independently of the root config.
    result = [target for target in result
              if not harness_profile or target.profile == harness_profile]
    if not result:
        raise ValueError("no config found for --harness-profile")
    return result


class Intent:
    """Explicit desired state, never inferred from observed config or service state."""

    def __init__(self, *, host: str, profile: str | None = None,
                 components: str | None = None, host_profile: str | None = None):
        if sum(value is not None for value in (profile, components, host_profile)) > 1:
            raise ValueError("choose one of --profile, --components or --host-profile")
        self.spec: dict[str, Any] = {}
        if host_profile:
            try:
                data = yaml.safe_load(Path(host_profile).read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                raise ValueError("cannot read host-profile YAML") from None
            if not isinstance(data, dict):
                raise ValueError("host-profile must be a mapping")
            if "hosts" in data:
                hosts = data["hosts"]
                if not isinstance(hosts, dict) or host not in hosts:
                    raise ValueError("host-profile has no entry for this host")
                data = hosts[host]
            if not isinstance(data, dict) or data.get("host", host) != host:
                raise ValueError("host-profile does not name this host")
            self.spec = data
        elif components is not None:
            self.spec = {"components": [cid.strip() for cid in components.split(",") if cid.strip()]}
        elif profile:
            self.spec = {"profile": profile}
        else:
            workspace_profile = registry.load_workspace().get("profile")
            if workspace_profile:
                self.spec = {"profile": workspace_profile}
        self._validate_spec(self.spec)

    def _selection(self, spec: dict[str, Any]) -> list[str] | None:
        if "profile" in spec and "components" in spec:
            raise ValueError("intent must use either profile or components")
        if "components" in spec:
            ids = spec["components"]
            if not isinstance(ids, list) or any(not isinstance(cid, str) or not cid for cid in ids):
                raise ValueError("intent components must be a list of component ids")
        elif "profile" in spec:
            if not isinstance(spec["profile"], str):
                raise ValueError("intent profile must be a z0 profile name")
            try:
                ids = registry.resolve_profile(spec["profile"])
            except KeyError:
                raise ValueError("unknown z0 profile in intent") from None
        else:
            return None
        if set(ids) - registry.components().keys():
            raise ValueError("intent contains unregistered components")
        return list(dict.fromkeys(ids))

    def _validate_spec(self, spec: dict[str, Any], level: int = 0) -> None:
        if not isinstance(spec, dict):
            raise ValueError("intent sections must be mappings")
        allowed = {"host", "profile", "components", "harnesses"} if level == 0 else (
            {"profile", "components", "profiles"} if level == 1 else {"profile", "components"})
        if spec.keys() - allowed:
            raise ValueError("unknown host-profile intent fields")
        self._selection(spec)
        if level == 0:
            children = spec.get("harnesses", {})
            if not isinstance(children, dict) or children.keys() - set(HARNESSES):
                raise ValueError("intent harnesses must use supported harness ids")
        elif level == 1:
            children = spec.get("profiles", {})
            if not isinstance(children, dict) or any(not isinstance(key, str) for key in children):
                raise ValueError("intent profiles must map native profile names to selections")
        else:
            children = {}
        for child in children.values():
            self._validate_spec(child, level + 1)

    def desired(self, target: Target) -> list[str] | None:
        harness = self.spec.get("harnesses", {}).get(target.harness, {})
        profile = harness.get("profiles", {}).get(target.profile, {})
        for section in (profile, harness, self.spec):
            selection = self._selection(section)
            if selection is not None:
                return selection
        return None


def recipe(meta: dict[str, Any], harness: str) -> dict[str, Any]:
    bindings = meta.get("bindings", {})
    if harness not in bindings.get("harnesses", []):
        return {}
    override = bindings.get(harness, {})
    result = {}
    mcp = override.get("mcp", bindings.get("mcp"))
    if mcp is not None:
        result["mcp"] = copy.deepcopy(mcp)
    if harness == "hermes" and "memory_provider" in override:
        result["memory_provider"] = override["memory_provider"]
    return result


def native_mcp(mcp: dict[str, Any], harness: str) -> dict[str, Any]:
    result = copy.deepcopy(mcp)
    if "url" in result:
        if harness == "codex" and "headers" in result:
            result["http_headers"] = result.pop("headers")
        if harness in {"claude", "omp"}:
            result["type"] = "http"
    elif harness in {"claude", "omp"}:
        result["type"] = "stdio"
    return result


def expand(value: Any, *, strict: bool = False) -> Any:
    if isinstance(value, dict):
        return {key: expand(item, strict=strict) for key, item in value.items()}
    if isinstance(value, list):
        return [expand(item, strict=strict) for item in value]
    if not isinstance(value, str):
        return value
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in os.environ and strict:
            raise ValueError("a binding environment variable is unset; no configs were written")
        return os.environ.get(name, match.group(0))
    return VARIABLE.sub(replace, value)


def read_config(target: Target) -> tuple[str, Any]:
    text = target.path.read_text(encoding="utf-8") if target.path.exists() else ""
    try:
        if target.harness == "hermes":
            parser = YAML()
            parser.preserve_quotes = True
            data = parser.load(text) if text.strip() else parser.load("{}")
        elif target.harness == "codex":
            data = tomlkit.parse(text)
        else:
            data = json.loads(text) if text.strip() else {}
    except Exception:
        # Parser exceptions can include source lines with credentials.
        raise ValueError(f"invalid {target.harness} config: {target.path}") from None
    if not isinstance(data, dict):
        raise ValueError(f"config root must be a mapping: {target.path}")
    for key in (MCP_KEYS[target.harness], "memory") if target.harness == "hermes" else (MCP_KEYS[target.harness],):
        if key in data and not isinstance(data[key], dict):
            raise ValueError(f"config section must be a mapping: {target.path} ({key})")
    return text, data


def serialize(target: Target, data: Any) -> str:
    if target.harness == "hermes":
        stream = io.StringIO()
        parser = YAML()
        parser.preserve_quotes = True
        parser.dump(data, stream)
        return stream.getvalue()
    if target.harness == "codex":
        return tomlkit.dumps(data)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def mask(value: Any, key: str = "") -> Any:
    """Mask credentials before display. Never pass a raw config to print()."""
    if key.lower() in {"env", "headers", "http_headers", "auth", "oauth"} and isinstance(value, dict):
        return {name: "<set>" for name in value}
    if SENSITIVE.search(key):
        return "<set>"
    if isinstance(value, dict):
        return {name: mask(item, name) for name, item in value.items()}
    if isinstance(value, list):
        # Arbitrary command arguments can contain positional or flag credentials.
        return ["<set>" for _ in value] if key == "args" else [mask(item) for item in value]
    if isinstance(value, str) and "://" in value:
        try:
            url = urlsplit(value)
            netloc = url.netloc.rsplit("@", 1)[-1]
            if "@" in url.netloc:
                netloc = "<set>@" + netloc
            query = urlencode([(name, "<set>") for name, _ in parse_qsl(url.query)])
            return urlunsplit((url.scheme, netloc, url.path, query, "<set>" if url.fragment else ""))
        except ValueError:
            return "<set>"
    return value


def project(data: Any, target: Target, recipes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    key = MCP_KEYS[target.harness]
    result: dict[str, Any] = {}
    names = [cid for cid, spec in recipes.items() if "mcp" in spec]
    if names:
        servers = data.get(key, {})
        result[key] = {cid: plain(servers[cid]) for cid in names if cid in servers}
    if any("memory_provider" in spec for spec in recipes.values()):
        if "provider" in data.get("memory", {}):
            result["memory"] = {"provider": data["memory"]["provider"]}
    return result


def signature(path: Path) -> tuple[int, int, int, int] | None:
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def detached(value: Any) -> Any:
    """Copy an owned mapping without reusing explicit YAML anchor names."""
    result = copy.deepcopy(value)
    visited: set[int] = set()
    def clear_anchors(node: Any) -> None:
        if id(node) in visited:
            return
        visited.add(id(node))
        if hasattr(node, "yaml_set_anchor"):
            node.yaml_set_anchor(None)
        if isinstance(node, dict):
            for key, item in node.items():
                clear_anchors(key)
                clear_anchors(item)
        elif isinstance(node, list):
            for item in node:
                clear_anchors(item)
    clear_anchors(result)
    return result


def make_plan(target: Target, desired: list[str], comps: dict[str, Any], *, strict: bool = False) -> Plan:
    before_signature = signature(target.path)
    original, data = read_config(target)
    recipes = {cid: expand(recipe(comps[cid], target.harness), strict=strict) for cid in desired}
    providers = [spec["memory_provider"] for spec in recipes.values() if "memory_provider" in spec]
    if len(set(providers)) > 1:
        raise ValueError(f"conflicting Hermes memory providers for {target.label}")
    before = project(data, target, recipes)
    key = MCP_KEYS[target.harness]
    # YAML aliases can share these mappings with unrelated sections. Detach before mutation.
    if any("mcp" in spec for spec in recipes.values()) and key in data:
        data[key] = detached(data[key])
    if providers and "memory" in data:
        data["memory"] = detached(data["memory"])
    for cid, spec in recipes.items():
        if "mcp" in spec:
            if key not in data:
                data[key] = {}
            data[key][cid] = native_mcp(spec["mcp"], target.harness)
        if "memory_provider" in spec:
            if "memory" not in data:
                data["memory"] = {}
            data["memory"]["provider"] = spec["memory_provider"]
    after = project(data, target, recipes)
    changed = before != after
    rendered = serialize(target, data) if changed else original
    # Print only owned fragments. Unrelated account/provider credentials never enter the diff.
    def display(fragment: Any) -> list[str]:
        return serialize(target, mask(fragment)).splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(display(before), display(after),
                                     fromfile=f"{target.path} (owned, observed)",
                                     tofile=f"{target.path} (owned, desired)"))
    if changed and not diff:
        diff = "  Owned values differ beneath <set> redaction.\n"
    if before_signature != signature(target.path):
        raise ValueError("config changed during planning; no configs were written")
    return Plan(target, original, rendered, diff, changed, before_signature is not None, before_signature)


def write_plan(plan: Plan) -> Path | None:
    if not plan.changed:
        return None
    path = plan.target.path
    if signature(path) != plan.signature:
        raise ValueError("config changed after planning; write refused")
    if path.is_symlink():
        raise ValueError("config symlink write refused")
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if plan.existed:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = path.with_name(f"{path.name}.z0-backup-{stamp}")
        # Backups can contain credentials. Create them with owner-only permissions.
        with backup.open("xb") as handle:
            os.chmod(backup, 0o600)
            handle.write(plan.original.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.z0-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(plan.rendered)
            handle.flush()
            os.fsync(handle.fileno())
        if plan.existed:
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        if signature(path) != plan.signature:
            raise ValueError("config changed before replacement; write refused")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def cmd_apply(*, dry_run: bool = False, apply: bool = False, yes: bool = False,
              host: str | None = None, harness: str | None = None,
              harness_profile: str | None = None, profile: str | None = None,
              components: str | None = None, host_profile: str | None = None) -> int:
    if apply and not yes:
        print("Refused: --apply requires --yes. No configs were written.")
        return 2
    try:
        actual = local_host(host)
        intent = Intent(host=actual, profile=profile, components=components, host_profile=host_profile)
        selected = targets(Path.home(), harness, harness_profile)
        comps = registry.components()
        plans = []
        notices = []
        for target in selected:
            desired = intent.desired(target)
            if desired is None:
                raise ValueError("desired state is unknown; pass --profile, --components or --host-profile")
            for cid in desired:
                if not recipe(comps[cid], target.harness):
                    notices.append(f"{target.label}: {cid}: no supported native binding; no keys owned")
            plans.append(make_plan(target, desired, comps, strict=apply))
        # Preflight every target before the first backup/write.
        if any(signature(plan.target.path) != plan.signature for plan in plans):
            raise ValueError("config changed after planning; no configs were written")
        if apply and any(plan.changed and plan.target.path.is_symlink() for plan in plans):
            raise ValueError("config symlink write refused; no configs were written")
        print(f"Bindings {'apply' if apply else 'dry-run'}: {actual}")
        print("Only owned fragments appear below. Environment, header and argument values are masked.")
        for notice in notices:
            print(f"  {notice}")
        for plan in plans:
            print(f"\n[{plan.target.label}] {plan.target.path}")
            print(plan.diff if plan.changed else "  No changes.", end="" if plan.diff.endswith("\n") else "\n")
            if apply:
                backup = write_plan(plan)
                if backup:
                    print(f"  Backup: {backup}")
                elif plan.changed:
                    print("  Created new config (no previous file to back up).")
        return 0
    except (OSError, ValueError) as exc:
        # OS errors contain paths, not file content. Parser errors were sanitized above.
        print(f"Error: {exc}")
        return 2


def service_state(unit: str) -> str:
    try:
        result = subprocess.run(["systemctl", "--user", "is-active", "--", unit],
                                text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    state = result.stdout.strip()
    return state if state in {"active", "inactive", "failed", "activating", "deactivating", "unknown"} else "unknown"


def enabled(server: Any) -> bool:
    return isinstance(server, dict) and server.get("enabled", True) is not False and server.get("disabled", False) is not True


def observe(target: Target, desired: list[str] | None, comps: dict[str, Any],
            services: dict[str, str]) -> dict[str, Any]:
    record: dict[str, Any] = {"harness": target.harness, "profile": target.profile,
                              "path": str(target.path), "mtime_ns": None,
                              "desired": desired, "bound": [], "findings": []}
    before = signature(target.path)
    record["mtime_ns"] = before[-1] if before else None
    try:
        _, data = read_config(target)
    except (OSError, ValueError):
        record["findings"].append({"kind": "unreadable-config"})
        return record
    servers = data.get(MCP_KEYS[target.harness], {})
    provider = data.get("memory", {}).get("provider") if target.harness == "hermes" else None
    bound = {cid for cid, server in servers.items() if enabled(server)}
    providers = {meta.get("bindings", {}).get("hermes", {}).get("memory_provider"): cid
                 for cid, meta in comps.items()
                 if meta.get("bindings", {}).get("hermes", {}).get("memory_provider")}
    if provider:
        bound.add(providers.get(provider, f"memory.provider:{provider}"))
    record["bound"] = sorted(bound)
    def finding(kind: str, cid: str, **extra: Any) -> None:
        record["findings"].append({"kind": kind, "component": cid, **extra})
    def recipe_present(cid: str, spec: dict[str, Any]) -> bool:
        mcp_present = "mcp" not in spec or enabled(servers.get(cid))
        memory_present = "memory_provider" not in spec or provider == spec["memory_provider"]
        return bool(spec) and mcp_present and memory_present
    for cid in sorted(bound):
        if cid not in comps:
            finding("bound-but-unregistered", cid)
            continue
        unit = comps[cid].get("service", {}).get("unit")
        if unit:
            if unit not in services:
                services[unit] = service_state(unit)
            if services[unit] != "active":
                finding("bound-but-service-not-running", cid, unit=unit, state=services[unit])
    for cid, meta in sorted(comps.items()):
        spec = recipe(meta, target.harness)
        declared = target.harness in meta.get("bindings", {}).get("harnesses", [])
        if declared and not spec:
            finding("binding-not-observable", cid)
        elif spec and not recipe_present(cid, spec):
            finding("registered-but-unbound", cid)
        if "mcp" in spec and enabled(servers.get(cid)):
            expected = native_mcp(expand(spec["mcp"]), target.harness)
            # Presence does not imply the native recipe matches. Extra native options are allowed.
            if any(plain(servers[cid].get(key)) != value for key, value in expected.items()):
                finding("binding-mismatch", cid)
    if desired is not None:
        for cid in desired:
            spec = recipe(comps[cid], target.harness)
            satisfied = recipe_present(cid, spec) if spec else cid in bound
            if not satisfied:
                finding("missing-desired-component", cid,
                        reason="not-bound" if spec else "no-supported-native-binding")
    if before != signature(target.path):
        record["findings"].append({"kind": "config-changed-during-observation"})
    return record


def cmd_doctor(*, host: str | None = None, harness: str | None = None,
               harness_profile: str | None = None, profile: str | None = None,
               components: str | None = None, host_profile: str | None = None,
               receipt: str | None = None) -> int:
    try:
        actual = local_host(host)
        intent = Intent(host=actual, profile=profile, components=components, host_profile=host_profile)
        comps = registry.components()
        services: dict[str, str] = {}
        records = [observe(target, intent.desired(target), comps, services)
                   for target in targets(Path.home(), harness, harness_profile)]
        observed_names = {cid for record in records for cid in record["bound"]}
        unbound = sorted(cid for cid, meta in comps.items()
                         if "bindings" in meta and not meta["bindings"].get("harnesses")
                         and cid not in observed_names)
        timestamp = datetime.now(timezone.utc)
        report = {"kind": "binding-observation", "host": actual,
                  "timestamp": timestamp.isoformat(), "services": services, "configs": records,
                  "registered_without_native_binding": unbound}
        destination = Path(receipt) if receipt else registry.z0_home() / "observations" / (
            "bindings-" + timestamp.strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
        # An explicit receipt must never overwrite a config, registry or old observation.
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2) + "\n")
        print(f"Binding observation: {actual} at {timestamp.isoformat()}")
        print("Configured does not mean running or verified. This report never promotes a stage.")
        if unbound:
            print("\n[registry/inspected-native-scope]")
            for cid in unbound:
                print(f"  registered-but-unbound: {cid} (no declared harness binding)")
        for record in records:
            print(f"\n[{record['harness']}/{record['profile']}] {record['path']}")
            print("  configured: " + (", ".join(record["bound"]) or "none"))
            if record["desired"] is None:
                print("  desired: unknown (pass --profile, --components or --host-profile)")
            else:
                print("  desired: " + (", ".join(record["desired"]) or "none"))
            for finding in record["findings"]:
                detail = finding.get("component", "")
                if "unit" in finding:
                    detail += f" ({finding['unit']}: {finding['state']})"
                if "reason" in finding:
                    detail += f" ({finding['reason']})"
                print(f"  {finding['kind']}: {detail}".rstrip())
            if not record["findings"]:
                print("  No binding drift observed.")
        print(f"\nObservation receipt: {destination}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2
