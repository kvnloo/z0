"""Hand-off files other tools read after an onboarding run (contributor spec CW7).

- `$Z0_HOME/onboard/state` (JSON, 0600): the last verified run. `z0int contribute` reads
  it at S1 (`ok: true` means host onboarding succeeded). `ok` is true when VERIFY
  exited 0, or 3 with no failed step (only C1/C2 asks left: spec A1).
- `$Z0_HOME/onboard/profile.json` (0600): the contributor profile from
  `detect/profile.py` with the default consent (T0 + T1 names only; T2/T3 need an explicit
  TTY yes, never an LLM: law L-LLM). `z0int contribute` merges it for T2/T3 only.

Both are written with the redactor's canary check: a file that would carry a secret
value the process holds is not written (X1).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Optional

SCHEMA = "z0.onboard.state.v1"


def _z0_sha(repo_root: str) -> Optional[str]:
    if not os.path.exists(os.path.join(repo_root, ".git")):
        return None
    try:
        out = subprocess.run(["git", "-C", repo_root, "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) == 40 else None


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".z0-tmp-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def state_record(run: Path, receipt: dict, repo_root: str) -> dict:
    failed = [s["id"] for s in receipt.get("steps") or [] if s.get("status") == "failed"]
    code = int(receipt.get("exit_code", 1))
    ok = (code == 0 or code == 3) and not failed and not (receipt.get("secrets_scan") or {}).get("canary_found")
    return {
        "schema": SCHEMA, "ok": ok,
        "status": "success" if ok and code == 0 else ("partial" if ok else "failed"),
        "exit_code": code, "run_id": run.name, "plan_hash": receipt.get("plan_hash"),
        "z0_sha": _z0_sha(repo_root), "failed": failed,
        "acceptance": receipt.get("acceptance") or {},
        "asks": [a.get("id") for a in receipt.get("asks") or []],
        "receipt": str(run / "receipt.json"),
    }


def write_state(z0_home: str, run: Path, receipt: dict, repo_root: str, redactor=None) -> dict:
    record = state_record(run, receipt, repo_root)
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if redactor is not None and redactor.found_in(text.encode("utf-8")):
        raise ValueError("onboard state would carry a secret value; not written")
    _write_private(Path(z0_home) / "onboard" / "state", text)
    return record


def mark_rolled_back(z0_home: str, run_id: str) -> None:
    """After a rollback the last run no longer stands: state says so (ok: false)."""
    path = Path(z0_home) / "onboard" / "state"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if record.get("run_id") != run_id:
        return
    record.update({"ok": False, "status": "rolled_back"})
    _write_private(path, json.dumps(record, indent=2, sort_keys=True) + "\n")


def write_profile(z0_home: str, host: Optional[dict], snap: dict, redactor=None) -> Optional[str]:
    """The contributor profile with the default consent. Never raises: a failure is a
    warning, and z0int falls back to its own T0 probe."""
    try:
        from .detect import Ctx
        from .detect import profile as profile_mod
        from .cli import sandbox_from_env

        ctx = Ctx(registry=snap, **sandbox_from_env(os.environ))
        prof = profile_mod.detect(ctx, profile_mod.consent_for(None), host)
        text = json.dumps(prof, indent=2, sort_keys=True) + "\n"
        if redactor is not None and redactor.found_in(text.encode("utf-8")):
            return None
        path = Path(z0_home) / "onboard" / "profile.json"
        _write_private(path, text)
        return str(path)
    except Exception:  # noqa: BLE001 - the hand-off is best effort; contribute has a T0 fallback
        return None
