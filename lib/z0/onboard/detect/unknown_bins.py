"""Unregistered executables in ~/.local/bin and ~/.bun/bin (§4, §7 harness_classify).

Name, symlink target and shebang line only. Never executed, never read past the
first line, and nothing under a denylisted path is opened.
"""
from __future__ import annotations

import os

DIRS = ("~/.local/bin", "~/.bun/bin")
LIMIT = 100


def _known(ctx) -> set:
    known = set()
    for row in ((ctx.registry.get("harnesses") or {}).get("harnesses") or {}).values():
        known.update((row.get("detect") or {}).get("binaries") or [])
    for spec in ((ctx.registry.get("toolchains") or {}).get("tools") or {}).values():
        known.update(spec.get("binaries") or [])
        known.update(spec.get("window_binaries") or [])
    known.update({"bunx", "uvx", "python3", "pip", "pip3"})
    return known


def _shebang(ctx, path: str) -> str:
    if ctx.denied(path) or ctx.denied(os.path.realpath(path)):
        return ""
    try:
        with open(path, "rb") as fh:
            head = fh.read(128)
    except OSError:
        return ""
    if not head.startswith(b"#!"):
        return ""
    return head.split(b"\n", 1)[0].decode("utf-8", "replace")


def detect(ctx) -> None:
    harness_ids = sorted(((ctx.registry.get("harnesses") or {}).get("harnesses") or {}))
    known = _known(ctx)
    entries = []
    for directory in DIRS:
        root = ctx.expand(directory)
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for name in names:
            path = os.path.join(root, name)
            if name in known or name.startswith(".") or not os.path.isfile(path) \
                    or not os.access(path, os.X_OK):
                continue
            facts = {"name": name, "dir": directory}
            if os.path.islink(path):
                facts["symlink_target"] = ctx.tilde(os.path.realpath(path))
            shebang = _shebang(ctx, path)
            if shebang:
                facts["shebang"] = ctx.tilde(shebang)
            entries.append(facts)
    for facts in entries[:LIMIT]:
        ctx.unknown({"id": f"bin.{facts['name']}", "kind": "harness_classify", "facts": facts,
                     "candidates": harness_ids + ["unsupported"], "safe_default": "unsupported"})
    if len(entries) > LIMIT:
        ctx.warn(f"unknown_bins: {len(entries) - LIMIT} more unregistered executables not listed")
