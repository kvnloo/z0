"""`check` (§2.5): a read-only acceptance probe. One of:
- argv (run in the step's `where`, venv bin first when the component has one), passing
  on exit code `verify.expect_exit` (default 0);
- `verify.http`: GET on loopback or the *current* tailnet IPv4 (never another address,
  law S2), passing on `expect_status`;
- `verify.exists`: the path exists;
- `verify.serve`: start a server in the background bound to loopback (a free port, a
  fresh state dir under the run dir), GET until `expect_status`, then stop it. This is
  the no-tailnet self-test (§8.3): nothing is installed and nothing keeps running.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request

from .base import ActionCtx, ActionError, Outcome


def _http(ctx: ActionCtx, spec: dict) -> Outcome:
    bind = spec.get("bind", "loopback")
    if bind == "loopback":
        host = "127.0.0.1"
    else:
        host = (ctx.host.get("tailscale") or {}).get("ipv4")
        if not host:
            raise ActionError("no tailnet IPv4 from the current detection")
    url = f"http://{host}:{int(spec['port'])}{spec.get('path', '/')}"
    request = urllib.request.Request(url, headers={"Host": f"{host}:{int(spec['port'])}",
                                                   "User-Agent": "z0-onboard"})
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310 - closed binds only
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except OSError as exc:
        raise ActionError(f"GET {spec.get('path', '/')} on port {spec['port']}: {exc.__class__.__name__}")
    if status != int(spec["expect_status"]):
        raise ActionError(f"GET {spec.get('path', '/')} returned {status}, want {spec['expect_status']}")
    return Outcome(True, f"HTTP {status}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(ctx: ActionCtx, step: dict, spec: dict) -> Outcome:
    port = _free_port()
    tmp = ctx.run_dir / "serve" / step["id"]
    tmp.mkdir(parents=True, exist_ok=True, mode=0o700)
    base = ctx.workdir(step)
    cwd = os.path.join(base, spec["cwd"]) if spec.get("cwd") else base
    env = ctx.env_for(step, venv=ctx.venv_of(step))
    for key, value in (spec.get("env") or {}).items():
        env[key] = str(value).replace("@port@", str(port)).replace("@tmp@", str(tmp))
    argv = [ctx.expand(a) for a in spec["argv"]]
    exe = ctx.resolve(argv[0], cwd, env)
    if exe is None:
        raise ActionError(f"{argv[0]}: not found on the prepared PATH")
    if not os.path.isdir(cwd):
        raise ActionError(f"{ctx.form(cwd)} does not exist")
    raw = tmp / "server.out"   # raw output stays in the disposable dir; only a redacted
    log = open(raw, "wb")       # tail reaches the run log
    proc = subprocess.Popen([exe, *argv[1:]], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic() + int(spec.get("timeout_s", 60))
    last = "no answer"
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise ActionError(f"the server exited with {proc.returncode} before answering")
            try:
                outcome = _http(ctx, {"bind": "loopback", "port": port, "path": spec.get("path", "/"),
                                      "expect_status": spec["expect_status"]})
                return Outcome(True, f"loopback self-test: {outcome.detail}")
            except ActionError as exc:
                last = str(exc)
                time.sleep(1)
        raise ActionError(f"loopback self-test timed out: {last}")
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        log.close()
        try:
            text = raw.read_bytes().decode("utf-8", "replace")
        except OSError:
            text = ""
        # anything the server wrote into its disposable state dir (tokens) is registered
        # with the redactor, then the dir is removed
        for root, _dirs, files in os.walk(tmp):
            for name in files:
                if os.path.join(root, name) == str(raw):
                    continue
                try:
                    with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
                        for value in re.findall(r"[A-Za-z0-9_+/=.-]{16,}", fh.read(65536)):
                            ctx.redactor.register(value)
                except OSError:
                    pass
        shutil.rmtree(tmp, ignore_errors=True)
        ctx.log(step["id"], f"$ {' '.join(spec['argv'])}  (serve on a loopback port)\n{ctx.tail(text)}\n")


def execute(ctx: ActionCtx, step: dict) -> Outcome:
    verify = step.get("verify") or {}
    if verify.get("serve"):
        return _serve(ctx, step, verify["serve"])
    if step.get("argv"):
        cwd = ctx.workdir(step)
        result = ctx.exec(list(step["argv"]), cwd=cwd, env=ctx.env_for(step, venv=ctx.venv_of(step)),
                          timeout=step.get("timeout_s", 900))
        want = int(verify.get("expect_exit", 0))
        if result.rc != want:
            raise ActionError(f"`{' '.join(step['argv'])}` exited {result.rc}, want {want}")
        return Outcome(True, "passed", ctx.tail(result.out))
    if verify.get("http"):
        return _http(ctx, verify["http"])
    if verify.get("exists"):
        if os.path.lexists(ctx.expand(verify["exists"])):
            return Outcome(True, "exists")
        raise ActionError(f"{verify['exists']} does not exist")
    raise ActionError("check has no argv and no verify probe")
