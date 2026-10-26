"""Detected-only providers, ordered by onboarding.llm.providers; stdlib transports.

No local model is started or downloaded. Credentials are never part of a prompt,
argv, URL, returned exception, or transcript. HTTP redirects are not followed.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .. import kernel as k

MAX_BYTES = 65536
ANSWER_SCHEMA = {
    "type": "object", "properties": {"answer": {"type": "string"},
                                      "need_probe": {"type": "string"}},
    "additionalProperties": False,
    "oneOf": [{"required": ["answer"]}, {"required": ["need_probe"]}],
}


class ProviderError(Exception):
    """Only fixed reason codes cross the transport boundary."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_json(url, body, timeout, headers=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
    # Never forward a local prompt or a credential via a proxy from the environment.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ProviderError("response_too_large")
        return json.loads(data)
    except (TimeoutError, subprocess.TimeoutExpired):
        raise TimeoutError("provider_timeout") from None
    except Exception:
        raise ProviderError("transport_error") from None


def local_endpoints(env):
    """Observe running server argv only. Never execute an unregistered binary.

    Loopback and standard server ports below are public defaults, not host settings.
    A process must explicitly bind IPv4 loopback; wildcard/default binds are ignored.
    """
    try:
        result = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True,
                                timeout=2, env={"PATH": os.defpath}, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    endpoints = []
    for line in result.stdout.splitlines():
        try:
            args = shlex.split(line)
        except ValueError:
            continue
        if not args or Path(args[0]).name not in ("llama-server", "ollama"):
            continue
        if Path(args[0]).name == "ollama":
            # Ollama defaults to loopback. No inherited OLLAMA_HOST assumption:
            # verify the detected endpoint by GET /api/tags before a send.
            if args[1:] == ["serve"] and not env.get("OLLAMA_HOST"):
                endpoints.append(("http://127.0.0.1:11434", "ollama"))
            continue
        def flag(name):
            for index, arg in enumerate(args):
                if arg.startswith(name + "="):
                    return arg.split("=", 1)[1]
                if arg == name and index + 1 < len(args):
                    return args[index + 1]
            return ""
        host, port = flag("--host"), flag("--port") or "8080"
        if host == "127.0.0.1" and port.isdecimal() and 0 < int(port) < 65536:
            endpoints.append((f"http://127.0.0.1:{port}", "llama"))
    return list(dict.fromkeys(endpoints))


@dataclass
class Provider:
    id: str
    model: str
    row: dict = field(default_factory=dict)
    env: dict = field(default_factory=lambda: dict(os.environ), repr=False)
    endpoint: str = ""
    protocol: str = ""
    executable: str = ""

    def available(self, timeout=2):
        if k.decide_provider(k.provider_from_id(self.id)).kind is k.Kind.REFUSE:
            return False
        if self.id == "local":
            for endpoint, protocol in local_endpoints(self.env):
                try:
                    data = http_json(endpoint + ("/api/tags" if protocol == "ollama" else "/v1/models"),
                                     None, timeout)
                    models = data.get("models" if protocol == "ollama" else "data", [])
                    model = next((m.get("name" if protocol == "ollama" else "id") for m in models
                                  if m.get("name" if protocol == "ollama" else "id")), None)
                    if model:
                        self.endpoint, self.protocol, self.model = endpoint, protocol, model
                        return True
                except (ProviderError, TimeoutError):
                    continue
            return False
        if self.id in ("claude", "codex"):
            self.executable = shutil.which(self.id, path=self.env.get("PATH", os.defpath)) or ""
            return bool(self.executable)
        key_name = self.row.get("key_name")
        # A model must be explicitly the free route; never fall through to a paid one.
        return (key_name in self.env and bool(self.env.get(key_name))
                and (self.model == "openrouter/free" or self.model.endswith(":free")))

    def send(self, prompt, timeout):
        if k.decide_provider(k.provider_from_id(self.id)).kind is k.Kind.REFUSE:
            raise ProviderError("forbidden_provider")
        if self.id in ("claude", "codex"):
            return self._cli(prompt, timeout)
        headers = {}
        if self.id == "local":
            if not self.endpoint:
                raise ProviderError("not_detected")
            url = self.endpoint + ("/api/chat" if self.protocol == "ollama" else "/v1/chat/completions")
        else:
            url = {"openrouter-free": "https://openrouter.ai/api/v1/chat/completions",
                   "vercel-free": "https://ai-gateway.vercel.sh/v1/chat/completions"}.get(self.id)
            if not url or not self.available():
                raise ProviderError("not_available")
            headers["Authorization"] = "Bearer " + self.env[self.row["key_name"]]
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "stream": False}
        if self.id == "local" and self.protocol == "ollama":
            body["format"] = ANSWER_SCHEMA
        else:
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "onboard_answer", "strict": True, "schema": ANSWER_SCHEMA}}
            body["max_tokens"] = 256
        data = http_json(url, body, timeout, headers)
        try:
            return (data["message"]["content"] if self.protocol == "ollama"
                    else data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise ProviderError("response_schema") from None

    def _cli(self, prompt, timeout):
        # Private empty cwd: no repository instructions/config are in the working dir.
        # Prompt via stdin, never argv. Raw stdout/stderr never escape this function.
        with tempfile.TemporaryDirectory(prefix="z0-llm-") as directory:
            root = Path(directory)
            config = root / "mcp.json"
            config.write_text('{"mcpServers": {}}', encoding="utf-8")
            schema = root / "answer.schema.json"
            schema.write_text(json.dumps(ANSWER_SCHEMA), encoding="utf-8")
            output = root / "answer.json"
            if self.id == "claude":
                argv = [self.executable, "-p", "--output-format", "json", "--model", self.model,
                        "--strict-mcp-config", "--mcp-config", str(config), "--tools", "",
                        "--max-turns", "1"]
            else:
                argv = [self.executable, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
                        "-m", self.model, "--output-schema", str(schema),
                        "--output-last-message", str(output), "-"]
            try:
                result = subprocess.run(argv, input=prompt, text=True, capture_output=True,
                                        timeout=timeout, cwd=directory, env=self.env, check=False)
                if result.returncode:
                    raise ProviderError("provider_failed")
                if self.id == "claude":
                    data = json.loads(result.stdout)
                    return data["result"]
                if output.stat().st_size > MAX_BYTES:
                    raise ProviderError("response_too_large")
                return output.read_text(encoding="utf-8")
            except subprocess.TimeoutExpired:
                raise TimeoutError("provider_timeout") from None
            except (OSError, ValueError, KeyError):
                raise ProviderError("provider_failed") from None


def configured(snap, env=None):
    policy = (snap.get("onboarding") or {}).get("llm") or {}
    out = []
    for row in sorted(policy.get("providers") or [], key=lambda r: r.get("order", 0)):
        pid = row["id"]
        model = (policy.get(pid + "_model") or row.get("model") or
                 {"claude": "haiku", "codex": "gpt-6.1-sol", "openrouter-free": "openrouter/free"}.get(pid, ""))
        out.append(Provider(pid, model, row, dict(os.environ) if env is None else env))
    return out
