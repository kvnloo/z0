"""Existing checkouts and pin evidence (§4, §6.2, spec z0 §8).

Finds `.git` at depth <= 3 under the configured roots, keeps only checkouts whose
GitHub `origin` is a registry repo (other repos are never listed), and asks git only
read-only questions: `--no-optional-locks status`, `rev-parse`, `cat-file -e`,
`merge-base --is-ancestor`, `for-each-ref --contains`, `ls-tree`. Adopted trees are
never written to. A z0 origin mirror ($Z0_HOME/cache/git/<name>.git), when present,
is the strongest evidence that a pin exists on origin (dash gates D1/D2).
"""
from __future__ import annotations

import os
import re

MAX_DEPTH = 3
SKIP = {"node_modules", ".git", ".cache", ".npm", ".cargo", ".rustup", ".bun", ".venv", "venv",
        "__pycache__", ".z0int", ".hermes", ".ssh", ".gnupg", "Library", "snap", ".mozilla",
        "go", ".pyenv", ".nvm", ".local", ".Trash", "Trash"}
_ORIGIN = re.compile(r'\[remote "origin"\]([^\[]*)', re.S)
_URL = re.compile(r"^\s*url\s*=\s*(\S+)", re.M)
_GH = re.compile(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                 r"([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


def normalize_origin(url: str):
    match = _GH.match(url.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _git_config(path: str) -> str:
    """Path of the config holding remotes, for a normal checkout or a worktree."""
    dot = os.path.join(path, ".git")
    if os.path.isdir(dot):
        return os.path.join(dot, "config")
    try:
        with open(dot, encoding="utf-8") as fh:
            gitdir = fh.read(4096).strip()
    except OSError:
        return ""
    if not gitdir.startswith("gitdir:"):
        return ""
    gitdir = gitdir.split(":", 1)[1].strip()
    gitdir = gitdir if os.path.isabs(gitdir) else os.path.join(path, gitdir)
    common = os.path.join(gitdir, "commondir")
    try:
        with open(common, encoding="utf-8") as fh:
            rel = fh.read(4096).strip()
        gitdir = rel if os.path.isabs(rel) else os.path.normpath(os.path.join(gitdir, rel))
    except OSError:
        pass
    return os.path.join(gitdir, "config")


def _origin(ctx, path: str):
    text = ctx.read_text(_git_config(path), 65536) or ""
    block = _ORIGIN.search(text)
    url = _URL.search(block.group(1)) if block else None
    return normalize_origin(url.group(1)) if url else None


def walk(ctx, roots) -> list:
    found, seen = [], set()
    for root in roots:
        start = ctx.expand(root)
        if not os.path.isdir(start):
            continue
        frontier = [(start, 0)]
        while frontier:
            current, depth = frontier.pop(0)
            real = os.path.realpath(current)
            if real in seen:
                continue
            seen.add(real)
            if os.path.exists(os.path.join(current, ".git")) and current != ctx.home:
                found.append(current)
                continue
            if depth >= MAX_DEPTH:
                continue
            try:
                entries = sorted(os.scandir(current), key=lambda e: e.name)
            except OSError:
                continue
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False) or entry.name in SKIP:
                        continue
                except OSError:
                    continue
                if ctx.denied(entry.path):
                    continue
                frontier.append((entry.path, depth + 1))
    return found


def _pins(comp: dict) -> list:
    pins = []
    ref = (comp.get("install") or {}).get("ref")
    if ref:
        pins.append(str(ref))
    for rev in ((comp.get("onboard") or {}).get("revs") or {}).values():
        if rev and str(rev) not in pins:
            pins.append(str(rev))
    return pins


def _flavour(ctx, git: list, sha: str, marker: str) -> str:
    """dash R0.3: the current flavour has bridge/src/acp (bridge rev) and app/modules
    (app rev); legacy (GitHub main d5d191b) has neither and is refused (D2)."""
    listing = ctx.run([*git, "ls-tree", "-d", "--name-only", sha, marker])
    if not listing.ok:
        return "unknown"
    return "current" if marker in listing.out.split() else "legacy"


def _markers(comp: dict) -> dict:
    revs = (comp.get("onboard") or {}).get("revs") or {}
    out = {}
    if revs.get("app"):
        out[str(revs["app"])] = "app/modules"
    if revs.get("bridge"):
        out[str(revs["bridge"])] = "bridge/src/acp"
    ref = str((comp.get("install") or {}).get("ref") or "")
    out.setdefault(ref, "bridge/src/acp")
    return out


def _merge(revs: dict, sha: str, repo: str, on_origin: str, evidence: str, flavour: str) -> None:
    rank = {"yes": 2, "no": 1, "unknown": 0}
    prev = revs.get(sha)
    if prev is None or rank[on_origin] > rank[prev["on_origin"]]:
        revs[sha] = {"repo": repo, "on_origin": on_origin, "evidence": evidence,
                     "flavour": flavour if flavour != "unknown" or prev is None else prev["flavour"]}
    elif flavour != "unknown" and prev.get("flavour") == "unknown":
        prev["flavour"] = flavour


def _inspect(ctx, path: str, origin: str, comps: list) -> tuple:
    """Per-checkout read-only facts; returns (entry, {pin: present})."""
    git = ["git", "-C", path]
    status = ctx.run([*git, "--no-optional-locks", "status", "--porcelain", "--ignore-submodules"],
                     timeout=20)
    entry = {"path": ctx.tilde(path), "origin": origin,
             "dirty": len([l for l in status.out.splitlines() if l.strip()]) if status.ok else 1}
    branch = ctx.run([*git, "symbolic-ref", "--short", "-q", "HEAD"])
    if branch.ok and branch.out.strip():
        entry["branch"] = branch.out.strip()
    head = ctx.run([*git, "rev-parse", "HEAD"])
    if head.ok and re.fullmatch(r"[0-9a-f]{40}", head.out.strip()):
        entry["head"] = head.out.strip()
    present = {}
    for cid, comp in comps:
        for index, pin in enumerate(_pins(comp)):
            if pin not in present:
                present[pin] = ctx.run([*git, "cat-file", "-e", f"{pin}^{{commit}}"]).ok
            if index == 0:
                entry["pin_present"] = present[pin]
                entry["pin_is_ancestor"] = present[pin] and ctx.run(
                    [*git, "merge-base", "--is-ancestor", pin, "HEAD"]).ok
    return entry, present


def detect(ctx) -> tuple:
    """Returns (checkouts, revs)."""
    from concurrent.futures import ThreadPoolExecutor

    comps = (ctx.registry.get("components") or {}).get("components") or {}
    by_repo: dict = {}
    for cid, comp in comps.items():
        if comp.get("repo"):
            by_repo.setdefault(str(comp["repo"]).lower(), []).append((cid, comp))
    roots = (ctx.registry.get("onboarding") or {}).get("checkout_roots") or ["~/workspace"]
    matched = []
    for path in walk(ctx, roots):
        origin = _origin(ctx, path)
        if origin and origin.lower() in by_repo:
            matched.append((path, origin))
    with ThreadPoolExecutor(max_workers=8) as pool:
        inspected = list(pool.map(lambda item: _inspect(ctx, item[0], item[1],
                                                        by_repo[item[1].lower()]), matched))
    revs: dict = {}
    for cid, comp in comps.items():
        name = str(comp.get("repo") or "").split("/", 1)[-1]
        dash = (comp.get("onboard") or {}).get("gate") == "dash"
        mirror = ctx.expand(f"$Z0_HOME/cache/git/{name}.git")
        markers = _markers(comp)
        holders = [path for (path, origin), (_, present) in zip(matched, inspected)
                   if origin.lower() == str(comp.get("repo") or "").lower()]
        for pin in _pins(comp):
            if os.path.isdir(mirror):
                git = ["git", "--git-dir", mirror]
                if ctx.run([*git, "cat-file", "-e", f"{pin}^{{commit}}"]).ok:
                    _merge(revs, pin, comp["repo"], "yes", "mirror",
                           _flavour(ctx, git, pin, markers[pin]) if dash else "unknown")
                    continue
            having = [p for p, (_, present) in zip(matched, inspected)
                      if p[0] in holders and present.get(pin)]
            flavour = "unknown"
            for path, _origin_name in having[:3]:
                git = ["git", "-C", path]
                if dash and flavour == "unknown":
                    flavour = _flavour(ctx, git, pin, markers[pin])
                contains = ctx.run([*git, "for-each-ref", "--contains", pin, "--count=1",
                                    "--format=%(refname)", "refs/remotes/origin"], timeout=20)
                if contains.ok and contains.out.strip():
                    _merge(revs, pin, comp["repo"], "yes", "checkout", flavour)
                    break
            _merge(revs, pin, comp["repo"], "unknown", "none", flavour)
    checkouts = sorted((entry for entry, _ in inspected), key=lambda c: c["path"])
    return checkouts, dict(sorted(revs.items()))
