"""Harness detection from registry/harnesses.yaml `detect:` rows (§2.3, §4).

- installed: the binary resolves; config_only: a config dir exists but no binary.
- Config and session dirs: existence only, never opened.
- `version_cmd` runs only when `policy.exec_probe: allowed` (grok, cursor: never).
- Allowed harness bin dirs join the prepared PATH; `configure: never` ones do not. Each
  installed allowed harness records its `path`; each policy-excluded binary records its
  `bin_dir`, so the plan can keep a shared dir that holds it off the PATH (P1).
"""
from __future__ import annotations

import os

from ..util import version_tuple

OVERRIDES = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR", "HERMES_HOME")


def _config_dirs(ctx, entries) -> tuple:
    found, overrides = [], {}
    for entry in entries or []:
        if isinstance(entry, dict):
            name = entry.get("env")
            value = ctx.env.get(name or "")
            if not value:
                continue
            path = ctx.expand(value)
            if name in OVERRIDES:
                overrides[name] = ctx.tilde(path)
        else:
            path = ctx.expand(str(entry))
        if os.path.isdir(path) and path not in found:
            found.append(path)
    return found, overrides


def _insert_dir(ctx, directory: str) -> None:
    if directory in ctx.prepared_path:
        return
    tail = 0
    for d in reversed(ctx.prepared_path):
        if d in ctx.system_dirs:
            tail += 1
        else:
            break
    ctx.prepared_path.insert(len(ctx.prepared_path) - tail, directory)


def detect(ctx, dirs_by_source: dict) -> dict:
    rows = (ctx.registry.get("harnesses") or {}).get("harnesses") or {}
    search = (dirs_by_source["well_known_dir"] + dirs_by_source["version_manager"]
              + dirs_by_source["path"] + dirs_by_source["system"])
    result, forbidden_bins = {}, []
    for hid, row in rows.items():
        det = row.get("detect")
        if not det:
            continue
        policy = row.get("policy") or {}
        never = policy.get("configure") == "never"
        binary = None
        for name in det.get("binaries") or []:
            binary = ctx.which(name, search)
            if binary:
                if never:
                    forbidden_bins.append(name)
                else:
                    _insert_dir(ctx, os.path.dirname(binary))
                break
        dirs, overrides = _config_dirs(ctx, det.get("config_dirs"))
        entry: dict = {"state": "installed" if binary else ("config_only" if dirs else "absent")}
        if binary:
            entry["bin_dir" if never else "path"] = ctx.tilde(os.path.dirname(binary) if never
                                                              else binary)
        if dirs:
            entry["config_dirs"] = [ctx.tilde(d) for d in dirs]
        if overrides:
            entry["overrides"] = overrides
        stores = det.get("session_stores") or []
        if stores and dirs:
            present = [d for d in dirs for store in stores
                       if os.path.isdir(store.replace("{config}", d))]
            entry["sessions_present"] = bool(present)
            if det.get("pick") == "has_child:projects" and len(set(present)) > 1:
                ctx.unknown({"id": f"{hid}.config_dir", "kind": "config_dir_pick",
                             "facts": {"dirs": sorted({ctx.tilde(d) for d in present})},
                             "candidates": sorted({ctx.tilde(d) for d in present}) + ["all"],
                             "safe_default": "all"})
        if never:
            entry["policy_excluded"] = True
        elif binary and policy.get("exec_probe") == "allowed" and det.get("version_cmd"):
            cmd = det["version_cmd"]
            run = ctx.run([binary, *cmd[1:]], timeout=5)
            parsed = version_tuple(run.out) if run.ok else None
            if parsed:
                entry["version"] = ".".join(str(p) for p in parsed)
        result[hid] = entry
    for name in forbidden_bins:
        if ctx.which(name, ctx.prepared_path):
            ctx.warn(f"prepared PATH dir also holds policy-excluded `{name}`; the plan "
                     "replaces that dir with $Z0_HOME/bin/links (P1)")
    return result
