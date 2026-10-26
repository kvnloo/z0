"""Redaction (design §9): runs on every captured stdout/stderr before it reaches the
journal, a log, the terminal or a receipt.

It masks every registered secret value (values live only in process memory: they are
registered, never written), these patterns: `sk-...`, `ghp_...` (and the other GitHub
token prefixes), `xox?-...`, `Bearer ...`, and runs of >= 20 hex/base64 characters
next to `token|key|secret`. `$HOME` becomes `~` (no absolute home path is written).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

MASK = "[redacted]"
PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{8,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{6,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"(?i)\b(token|key|secret)\b(['\"]?\s*[:=]\s*['\"]?|\s+)[A-Za-z0-9+/=_-]{20,}"),
)
MIN_SECRET = 6  # shorter values would mask ordinary words


class Redactor:
    def __init__(self, home: Optional[str] = None, values: Iterable[str] = ()):
        self.home = (home or "").rstrip("/")
        self._values: set = set()
        for value in values:
            self.register(value)

    def register(self, value: Optional[str]) -> None:
        if value and len(value) >= MIN_SECRET:
            self._values.add(value)

    @property
    def values(self) -> frozenset:
        return frozenset(self._values)

    def __call__(self, text: str) -> str:
        if not text:
            return text
        for value in sorted(self._values, key=len, reverse=True):
            text = text.replace(value, MASK)
        for rx in PATTERNS:
            text = rx.sub(MASK, text)
        if self.home:
            text = re.sub(re.escape(self.home) + r"(?=/|\b|$)", "~", text)
        return text

    def found_in(self, data: bytes) -> bool:
        """Whether any registered secret value occurs in `data` (the canary scan)."""
        return any(value.encode("utf-8") in data for value in self._values)


def secret_names(snap: dict) -> list:
    """Every env-kind secret name the registry declares (names only, §9)."""
    names = set()
    comps = (snap.get("components") or {}).get("components") or {}
    for comp in comps.values():
        for secret in (comp.get("onboard") or {}).get("secrets") or []:
            if secret.get("kind") == "env" and secret.get("name"):
                names.add(str(secret["name"]))
    for provider in ((snap.get("onboarding") or {}).get("llm") or {}).get("providers") or []:
        if provider.get("key_name"):
            names.add(str(provider["key_name"]))
    return sorted(names)


def from_env(snap: dict, env: dict, home: Optional[str] = None) -> Redactor:
    """A redactor that knows the values of the registry's secret env vars, read from this
    process's own environment into memory only (never from a file)."""
    redactor = Redactor(home)
    for name in secret_names(snap):
        redactor.register(env.get(name))
    return redactor
