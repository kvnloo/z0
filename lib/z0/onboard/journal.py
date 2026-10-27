"""The run journal (design §1.4, §6.3, §6.5): `runs/<id>/journal.jsonl`.

One JSON object per line, appended and fsync'd per line, so a crash leaves every effect
that happened on disk. APPLY records each effect right after it happens; ROLLBACK
replays the effects in reverse and records an `undo` line per effect, so a second
rollback skips what the first one already undid (it is itself journaled).

Paths in the journal are in plan form (`~/...` or `$Z0_HOME/...`): no absolute home
path is written (§4). Effect kinds:

  mkdir    a directory this run created as a parent; undo: rmdir if empty
  dir      a directory this run created and marked `.z0-owned` (run id); undo: remove
           it only while the marker still names this run (law R1)
  file     a file this run created, with its sha256; undo: delete if the hash is unchanged
  replace  a file this run overwrote, with the new sha256 and a 0600 backup of the old
           bytes under runs/<id>/backups/; undo: restore the backup if the hash is unchanged
  symlink  a link this run pointed at `target` (previous target in `prior`, or none);
           undo: restore `prior` if the link still points at `target`
  adopted  an existing checkout used in place; never undone (adopted trees are never
           touched)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Optional

MARKER = ".z0-owned"
EFFECT_KINDS = ("mkdir", "dir", "file", "replace", "symlink", "adopted")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path) -> Optional[str]:
    """sha256 of a regular file's bytes (symlinks are not followed), or None."""
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def marker_owner(directory) -> Optional[str]:
    """The run id in a directory's `.z0-owned` marker, or None."""
    try:
        with open(os.path.join(directory, MARKER), encoding="utf-8") as fh:
            return fh.read(256).strip() or None
    except OSError:
        return None


class Journal:
    """Append-only, fsync per line, mode 0600."""

    def __init__(self, path, run_id: str, clock: Callable[[], str] = utc_now):
        self.path = Path(path)
        self.run_id = run_id
        self.clock = clock
        self._seq = max((int(e.get("seq", 0)) for e in read(self.path) if e.get("event") == "effect"),
                        default=0)

    def write(self, event: str, **fields) -> dict:
        entry = {"ts": self.clock(), "run": self.run_id, "event": event, **fields}
        line = json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return entry

    def effect(self, step: str, effect: dict) -> dict:
        if effect.get("kind") not in EFFECT_KINDS:
            raise ValueError(f"unknown effect kind: {effect.get('kind')}")
        self._seq += 1
        return self.write("effect", step=step, seq=self._seq, effect=effect)

    def entries(self) -> list:
        return read(self.path)


def read(path) -> list:
    """Every complete line of a journal (a torn last line from a crash is skipped)."""
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def effects(entries: list) -> list:
    return [e for e in entries if e.get("event") == "effect"]


def undone(entries: list) -> set:
    return {int(e["seq"]) for e in entries if e.get("event") == "undo" and "seq" in e}


def step_results(entries: list) -> dict:
    """{step id: last recorded result entry} from an apply journal."""
    out: dict = {}
    for entry in entries:
        if entry.get("event") == "step" and entry.get("status") not in (None, "begin"):
            out[entry["step"]] = entry
    return out
