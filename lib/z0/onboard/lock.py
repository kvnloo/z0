"""`$Z0_HOME/onboard/.lock` (design §1.4): an fcntl lock that stops concurrent runs.

APPLY, VERIFY and ROLLBACK hold it for their whole run. A second run fails fast
(non-blocking) instead of waiting, so two onboarders never interleave effects.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
from pathlib import Path


class LockHeld(Exception):
    """Another onboard run holds the lock."""


@contextlib.contextmanager
def hold(z0_home):
    directory = Path(z0_home) / "onboard"
    old = os.umask(0o077)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(directory / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    finally:
        os.umask(old)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LockHeld(f"another z0 onboard run holds {directory / '.lock'}") from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
