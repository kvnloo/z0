"""Origin mirrors (design §6.2): `plan` fetches each registry pin into a bare mirror.

`$Z0_HOME/cache/git/<repo>.git` is a z0-private (C0) write that law P0 allows `plan`
to make. It answers the R0/D1 question "is this pinned SHA on origin?" for a stranger
who has no checkout yet; `detect/checkouts.py` then reads the mirror (cat-file, and
ls-tree for the dash flavour) like any other evidence. Adopted checkouts are never
touched. `plan --stdout` and `plan --host` never fetch (they write nothing).

Per pin: already in the mirror -> yes; else a shallow, blob-less fetch of that SHA
from the registry clone URL: success -> yes; the server says the object is not
there -> no; anything else (offline, DNS, TLS, timeout) -> unknown.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Optional

from . import regsnap

# git/upload-pack wording when the SHA is not reachable on the remote.
NOT_ON_ORIGIN = ("not our ref", "couldn't find remote ref", "no such remote ref",
                 "unadvertised object", "not a valid object", "did not send all necessary objects")
ENV_KEEP = ("HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "HTTPS_PROXY", "https_proxy",
            "HTTP_PROXY", "http_proxy", "NO_PROXY", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR")


def pins(comp: dict) -> list:
    out = []
    ref = (comp.get("install") or {}).get("ref")
    if ref:
        out.append(str(ref))
    for rev in ((comp.get("onboard") or {}).get("revs") or {}).values():
        if rev and str(rev) not in out:
            out.append(str(rev))
    return out


def _run(argv: list, env: dict, timeout: float) -> tuple:
    try:
        proc = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return proc.returncode, proc.stderr


def _env(base: dict) -> dict:
    env = {key: base[key] for key in ENV_KEEP if key in base}
    env.update({"PATH": base.get("PATH") or "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
                "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": "",
                "GIT_CONFIG_NOSYSTEM": "1"})
    return env


def ensure(snap: dict, z0_home: str, env: Optional[dict] = None, *,
           urls: Optional[dict] = None, run: Callable = _run, timeout: float = 120.0) -> dict:
    """Fetch every registry pin into its mirror. Returns {sha: "yes"|"no"|"unknown"}.

    `urls` maps a registry repo (owner/name) to a clone URL (tests use file:// origins).
    """
    env = _env(dict(os.environ if env is None else env))
    git = shutil.which("git", path=env["PATH"] + os.pathsep + "/usr/bin:/bin")
    if git is None:
        return {}
    cache = Path(z0_home) / "cache" / "git"
    jobs = []
    for comp in regsnap.components(snap).values():
        if comp.get("status") == "idea":
            continue  # M1: never planned, so never fetched
        repo = str(comp.get("repo") or "")
        url = (urls or {}).get(repo) or (comp.get("install") or {}).get("clone")
        if repo and url and pins(comp):
            jobs.append((repo, str(url), pins(comp)))

    def one(job):
        repo, url, shas = job
        mirror = cache / f"{repo.split('/', 1)[-1]}.git"
        out = {}
        if not (mirror / "HEAD").is_file():
            old = os.umask(0o077)
            try:
                cache.mkdir(parents=True, exist_ok=True)
                rc, _ = run([git, "init", "--bare", "-q", str(mirror)], env, 30)
                if rc != 0:
                    return {sha: "unknown" for sha in shas}
                (mirror / ".z0-owned").write_text("z0 onboard plan: origin mirror (§6.2)\n")
            finally:
                os.umask(old)
        for sha in shas:
            have, _ = run([git, "--git-dir", str(mirror), "cat-file", "-e", f"{sha}^{{commit}}"],
                          env, 30)
            if have == 0:
                out[sha] = "yes"
                continue
            rc, err = run([git, "--git-dir", str(mirror), "fetch", "-q", "--no-tags", "--depth=1",
                           "--filter=blob:none", url, sha], env, timeout)
            if rc == 0:
                out[sha] = "yes"
            elif rc is not None and any(text in err.lower() for text in NOT_ON_ORIGIN):
                out[sha] = "no"
            else:
                out[sha] = "unknown"
        return out

    results: dict = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            for out in pool.map(one, jobs):
                results.update(out)
    return dict(sorted(results.items()))


def merge(host: dict, outcomes: dict, snap: dict) -> None:
    """Record a definite `no` from the fetch in host.revs (a `yes` is already there:
    detect read it from the mirror)."""
    repo_of = {sha: comp.get("repo") for comp in regsnap.components(snap).values()
               for sha in pins(comp)}
    revs = host.setdefault("revs", {})
    for sha, state in outcomes.items():
        fact = revs.get(sha) or {"repo": repo_of.get(sha, ""), "flavour": "unknown"}
        if state == "no" and fact.get("on_origin") != "yes":
            fact.update(on_origin="no", evidence="mirror")
            revs[sha] = fact
