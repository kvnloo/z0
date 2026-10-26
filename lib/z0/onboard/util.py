"""Small pure helpers shared by detect, plan and registry-check (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_LOOSE = re.compile(r"^\D*?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def canonical_json(obj: Any) -> str:
    """The byte-stable JSON form that plan_hash is taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def version_tuple(text: Any, loose: bool = False) -> Optional[tuple]:
    """First dotted version in `text` as a tuple of ints, or None.

    `loose` also accepts a bare major ("20") at the start: for registry minimums and
    `when` values, never for parsing tool output (where "x86_64" would match).
    """
    if text is None:
        return None
    match = _VERSION.search(str(text))
    if match is None and loose:
        match = _LOOSE.match(str(text).strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups() if part is not None)


def version_ge(have: Any, want: Any) -> bool:
    a, b = version_tuple(have, loose=True), version_tuple(want, loose=True)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) >= b + (0,) * (width - len(b))


def tilde(path: str, home: str) -> str:
    """Write $HOME as ~ (design §4): no absolute home path leaves detect."""
    home = home.rstrip("/")
    if home and (path == home or path.startswith(home + "/")):
        return "~" + path[len(home):]
    return path


def norm_key(name: str) -> str:
    """Registry ids may hold '-', fact names may not (`when` grammar)."""
    return name.replace("-", "_")


def parse_requirement(text: str) -> tuple[str, Optional[str]]:
    """'bun>=1.4.3' -> ('bun', '1.4.3'); 'git' -> ('git', None)."""
    if ">=" in text:
        tool, minimum = text.split(">=", 1)
        return tool.strip(), minimum.strip()
    return text.strip(), None
