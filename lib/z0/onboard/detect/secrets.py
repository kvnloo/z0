"""Secret presence by NAME only (§4, §9). Values are never read, stored or printed.

Env vars: present means set and non-empty; the value never leaves os.environ.
Files: `stat` only (existence and mode); the token files are never opened.
"""
from __future__ import annotations

import stat as stat_mod

FILES = {
    "dash_token": ("~/.dash/token", 0o600),
    "dash_bootstrap_token": ("~/.dash/bootstrap-token", 0o600),
    "dash_dir": ("~/.dash", 0o700),
}


def names(registry: dict) -> list:
    found = set()
    for comp in ((registry.get("components") or {}).get("components") or {}).values():
        for secret in (comp.get("onboard") or {}).get("secrets") or []:
            if secret.get("kind") == "env":
                found.add(secret["name"])
    for provider in ((registry.get("onboarding") or {}).get("llm") or {}).get("providers") or []:
        if provider.get("key_name"):
            found.add(provider["key_name"])
    return sorted(found)


def detect(ctx) -> dict:
    result = {}
    for name in names(ctx.registry):
        result[name] = {"present": bool(ctx.env.get(name))}
    for key, (path, mode) in FILES.items():
        st = ctx.stat(ctx.expand(path))
        entry = {"present": st is not None}
        if st is not None:
            entry["mode_ok"] = stat_mod.S_IMODE(st.st_mode) == mode
        result[key] = entry
    return result
