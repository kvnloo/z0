"""`harness_plugin` (§2.5, §8.4): install a component's plugin into one detected harness.

- the harness must be detected as installed and its registry policy must allow
  configuring it (grok and cursor-agent never: law P1, checked here again);
- for Claude Code and Codex the component's stamped release is first added as a local
  plugin marketplace (`<harness> plugin marketplace add <release>`), then the step's argv
  installs the plugin from it; other harnesses run the step's argv in the release dir;
- harness state lives in the harness's own config dir, which z0 does not journal file by
  file: success writes the stamp `$Z0_HOME/onboard/stamps/<step id>` (the probe), and
  rollback/undo is `uninstall` (`<harness> plugin uninstall|remove <plugin>`), listed in
  the report;
- harness logins are never automatic (§9): a harness that is not logged in still gets
  its plugin files; nothing here starts a session.
"""
from __future__ import annotations

import os

from .base import ActionCtx, ActionError, Outcome

HARNESS_BIN = {"claude-code": "claude", "codex": "codex", "omp": "omp"}
MARKETPLACE_FILE = {"claude-code": os.path.join(".claude-plugin", "marketplace.json"),
                    "codex": os.path.join(".agents", "plugins", "marketplace.json")}


def _policy(ctx: ActionCtx, harness: str) -> str:
    rows = (ctx.snap.get("harnesses") or {}).get("harnesses") or {}
    return ((rows.get(harness) or {}).get("policy") or {}).get("configure", "ask")


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    harness = step.get("harness")
    if not harness:
        raise ActionError("harness_plugin needs `harness`")
    if _policy(ctx, harness) == "never":
        raise ActionError(f"{harness} is policy-excluded (P1); never configured")
    entry = (ctx.host.get("harnesses") or {}).get(harness) or {}
    if entry.get("state") != "installed":
        raise ActionError(f"{harness} is not installed on this host")
    cwd = ctx.workdir(step)
    env = ctx.env_for(step)
    # the harness binary detect found, even when its dir is not on the prepared PATH
    if entry.get("path"):
        directory = os.path.dirname(ctx.expand(entry["path"]))
        if directory not in env["PATH"].split(os.pathsep):
            env["PATH"] = env["PATH"] + os.pathsep + directory
    for key in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
        if ctx.base_env.get(key):
            env[key] = ctx.base_env[key]
    exe = HARNESS_BIN.get(harness)
    market = MARKETPLACE_FILE.get(harness)
    if market:
        if not os.path.isfile(os.path.join(cwd, market)):
            raise ActionError(f"{ctx.form(cwd)} has no {market}; nothing to install")
        result = ctx.exec([exe, "plugin", "marketplace", "add", cwd], cwd=cwd, env=env, timeout=300,
                          label=f"{step['id']}.marketplace")
        if result.rc != 0 and "already" not in result.out.lower():
            raise ActionError(f"`{exe} plugin marketplace add <release>` exited {result.rc}")
    result = ctx.exec(list(step["argv"]), cwd=cwd, env=env, timeout=step.get("timeout_s", 600))
    if result.rc != 0 and "already" not in result.out.lower():
        raise ActionError(f"`{' '.join(step['argv'])}` exited {result.rc}")
    stamp = ctx.expand(f"$Z0_HOME/onboard/stamps/{step['id']}")
    ctx.write_file(stamp, f"{step['id']} {ctx.run_id}\n".encode("utf-8"), 0o600)
    return Outcome(True, f"{harness}: {' '.join(step['argv'][1:])}", ctx.tail(result.out))
