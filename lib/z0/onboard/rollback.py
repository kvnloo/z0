"""ROLLBACK (design §6.5): replay a run's journal in reverse.

Order: (1) restore symlinks, so live links return to the previous release; (2) stop
and remove new units (none until Z3/Z4); (3) restore overwritten files from their
backups, only if the file still has the hash the run wrote; (4) delete owned artifacts:
a dir only while its `.z0-owned` marker names this run, a file only while its hash is
unchanged, a parent dir only while empty (law R1). Changed files are kept and reported.

Never deleted: adopted checkouts (nothing under an adopted tree is touched), the
release a `*-current` link points at, and the `cache/` mirrors (unless `--purge`).
Stage 0's bootstrap (`$Z0_HOME/{bootstrap,venv}`) goes only with `--purge-bootstrap`.
Every undo is journaled, so running rollback twice is safe.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Callable

from . import journal as journal_mod, lock as lock_mod
from .journal import marker_owner, sha256_file

PHASES = (("symlink",), ("unit",), ("replace",), ("file", "dir", "mkdir"))


class _Paths:
    def __init__(self, z0_home: str, home: str):
        self.z0_home, self.home = str(z0_home).rstrip("/"), str(home).rstrip("/")

    def expand(self, text: str) -> str:
        if text == "~" or text.startswith("~/"):
            return self.home + text[1:]
        if text == "$Z0_HOME" or text.startswith("$Z0_HOME/"):
            return self.z0_home + text[len("$Z0_HOME"):]
        return text


def _under(path: str, root: str) -> bool:
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


def _adopted(paths: _Paths, run: Path, effects: list) -> list:
    trees = [paths.expand(e["effect"]["path"]) for e in effects if e["effect"]["kind"] == "adopted"]
    for name in ("plan.replan.json", "plan.json"):
        try:
            plan_obj = json.loads((run / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        trees += [paths.expand(c["tree"]) for c in (plan_obj.get("components") or {}).values()
                  if c.get("adopted") and c.get("tree")]
        break
    return sorted(set(trees))


def _current_targets(path: str) -> bool:
    """Whether a `*-current` link next to this release (or one level up) points at it."""
    real = os.path.realpath(path)
    for directory in (os.path.dirname(path), os.path.dirname(os.path.dirname(path))):
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            link = os.path.join(directory, name)
            if name.endswith("current") and os.path.islink(link) and os.path.realpath(link) == real:
                return True
    return False


def undo_one(effect: dict, paths: _Paths, run: Path, run_id: str, adopted: list,
             kept: tuple = ()) -> tuple:
    """(result, detail). result: removed | restored | missing | kept_changed |
    kept_adopted | kept_current | kept_not_empty | kept."""
    kind, path = effect["kind"], paths.expand(effect["path"])
    if kind == "adopted":
        return "kept_adopted", "adopted checkout (never touched)"
    if any(_under(path, tree) for tree in adopted):
        return "kept_adopted", "inside an adopted checkout (never touched)"
    if kind == "symlink":
        if not os.path.islink(path):
            return ("missing", "") if not os.path.lexists(path) else ("kept_changed", "no longer a symlink")
        if os.readlink(path) not in (effect["target"], paths.expand(effect["target"])):
            return "kept_changed", "the link was repointed since"
        prior = effect.get("prior")
        if prior:
            tmp = f"{path}.z0-undo-{os.getpid()}"
            if os.path.lexists(tmp):
                os.unlink(tmp)
            os.symlink(paths.expand(prior), tmp)
            os.replace(tmp, path)
            return "restored", f"-> {prior}"
        os.unlink(path)
        return "removed", ""
    if kind == "replace":
        if sha256_file(path) != effect.get("sha256"):
            return "kept_changed", "changed since the run wrote it"
        backup = run / effect["backup"]
        if not backup.is_file():
            return "kept", "backup missing"
        tmp = f"{path}.z0-undo-{os.getpid()}"
        shutil.copyfile(backup, tmp)
        os.chmod(tmp, int(effect.get("prior_mode") or 0o600))
        os.replace(tmp, path)
        return "restored", "from backup"
    if kind == "file":
        if not os.path.lexists(path):
            return "missing", ""
        if sha256_file(path) != effect.get("sha256"):
            return "kept_changed", "changed since the run wrote it"
        os.unlink(path)
        return "removed", ""
    if kind == "dir":
        if not os.path.lexists(path):
            return "missing", ""
        if os.path.islink(path) or marker_owner(path) != effect.get("marker", run_id):
            return "kept_changed", "its .z0-owned marker does not name this run"
        inside = [k for k in kept if _under(k, path)]
        if inside:
            return "kept_changed", f"holds {len(inside)} changed file(s) the run wrote"
        if _current_targets(path):
            return "kept_current", "a *-current link points at it"
        shutil.rmtree(path)
        return "removed", ""
    if kind == "mkdir":
        if not os.path.isdir(path) or os.path.islink(path):
            return ("missing", "") if not os.path.lexists(path) else ("kept", "not a dir")
        try:
            os.rmdir(path)
        except OSError:
            return "kept_not_empty", "not empty"
        return "removed", ""
    return "kept", f"unknown effect kind {kind}"


def rollback_run(run: Path, z0_home: str, home: str, *, out: Callable = print) -> dict:
    """Undo one run. Returns {result: count}."""
    paths = _Paths(z0_home, home)
    counts: dict = {}
    with lock_mod.hold(z0_home):
        journal = journal_mod.Journal(run / "journal.jsonl", run.name)
        entries = journal.entries()
        effects = journal_mod.effects(entries)
        done = journal_mod.undone(entries)
        adopted = _adopted(paths, run, effects)
        journal.write("rollback_start")
        pending = [e for e in reversed(effects) if int(e["seq"]) not in done]
        kept: list = []
        for kinds in PHASES:
            for entry in pending:
                if entry["effect"]["kind"] not in kinds and not (
                        kinds == PHASES[-1] and entry["effect"]["kind"] == "adopted"):
                    continue
                try:
                    result, detail = undo_one(entry["effect"], paths, run, run.name, adopted,
                                              tuple(kept))
                except OSError as exc:
                    result, detail = "error", f"{exc.__class__.__name__}: {exc.strerror}"
                journal.write("undo", seq=entry["seq"], step=entry.get("step"),
                              path=entry["effect"]["path"], result=result, detail=detail)
                counts[result] = counts.get(result, 0) + 1
                if result in ("kept_changed", "kept", "error"):
                    kept.append(paths.expand(entry["effect"]["path"]))
                if result.startswith("kept") and result != "kept_adopted" or result == "error":
                    out(f"  {result:15} {entry['effect']['path']}: {detail}")
        journal.write("rollback_done", counts=counts)
    return counts


def purge(z0_home: str, what: str, *, out: Callable = print) -> list:
    """`--purge` (cache mirrors) and `--purge-bootstrap` (stage 0's venv and bootstrap):
    removed only when they carry a z0 marker."""
    removed = []
    root = Path(z0_home)
    if what == "cache":
        cache = root / "cache" / "git"
        for mirror in sorted(cache.glob("*.git")) if cache.is_dir() else []:
            if (mirror / ".z0-owned").is_file():
                shutil.rmtree(mirror)
                removed.append(f"$Z0_HOME/cache/git/{mirror.name}")
    elif what == "bootstrap":
        for name in ("venv", "bootstrap"):
            target = root / name
            if target.is_dir() and marker_owner(target) == "stage0":
                shutil.rmtree(target)
                removed.append(f"$Z0_HOME/{name}")
            elif target.exists():
                out(f"  kept $Z0_HOME/{name}: no stage 0 marker")
    return removed
