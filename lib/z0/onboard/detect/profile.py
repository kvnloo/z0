"""Contributor profile detector with consent tiers T0-T3 (contributor spec §3.2, §3.7).

Writes `profile.json` (schemas/profile.schema.json). Stdlib only, read-only except
for that one file, never raises, and `$HOME` is written as `~`.

Tiers and their signals (closed: nothing else is read):
- T0, always: OS, arch, RAM, GPU class and VRAM; toolchains present (a binary exists
  on the search dirs; nothing is executed); harnesses present (a binary or config dir
  exists); harness instruction files (exists, size, mtime date: `stat` only).
- T1, `t1.*` items: the top-level key NAMES of the Claude `settings.json` and the
  Codex `config.toml`, plus MCP server NAMES (never a value, never an env table);
  whether `git config` user.name and user.email are set (booleans; values discarded).
- T2, `t2.*` items, explicit consent only: a language histogram of local repos from
  file NAMES (extensions and marker files, depth <= 3, no file is opened); the
  language and push recency of the user's public non-fork GitHub repos via `gh api`,
  only when `gh` is logged in.
- T3, `t3.*` items, explicit consent per item: public repo names, repo topics (also
  mapped to closed domain tags), starred repos' languages, instruction-file text.
  T3 data stays under `t3` in the local file: `public_view()` drops it, and it never
  goes into an LLM prompt or a receipt (§3.4, §3.7).

Never touched (not opened, not listed): credentials, transcripts and history
(NEVER_TOUCH plus the registry's read denylist). Consent comes from the caller
(`consent_for`): an LLM is never a consent source, and T2/T3 items are never on
without an explicit yes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import datetime as _dt
import fnmatch
import json
import os
import re
import tempfile
from typing import Optional

SCHEMA = "z0.contribute.profile.v1"
DEFAULT_PATH = "~/.z0int/contribute/profile.json"
TIERS = ("T0", "T1", "T2", "T3")

# Consent items (§3.2). T0 has no item: it is always on.
ITEMS = {
    "t1.harness_keys": ("T1", "key and MCP server names of ~/.claude/settings.json and ~/.codex/config.toml"),
    "t1.git_identity": ("T1", "whether git user.name and user.email are set (yes/no only)"),
    "t2.local_languages": ("T2", "language histogram of your local repos (file names only)"),
    "t2.github_languages": ("T2", "language and recency of your public GitHub repos (gh api)"),
    "t3.repo_names": ("T3", "names of your public GitHub repos"),
    "t3.topics": ("T3", "topics of your public GitHub repos"),
    "t3.starred_languages": ("T3", "languages of the repos you starred"),
    "t3.instruction_text": ("T3", "the text of your harness instruction files"),
}
T1_ITEMS = frozenset(i for i, (tier, _) in ITEMS.items() if tier == "T1")
SOURCES = ("default", "flag", "tty")

# Never opened or listed, whatever the tier (§3.2 never-touch list, G4).
NEVER_TOUCH = (
    "~/.claude*/.credentials*", "~/.claude*/history.jsonl", "~/.claude*/projects",
    "~/.claude*/projects/*", "~/.claude*/file-history*", "~/.claude*/paste-cache*",
    "~/.claude*/todos*", "~/.claude*/shell-snapshots*", "~/.claude.json",
    "~/.codex/auth*", "~/.codex/attachments*", "~/.codex/history*", "~/.codex/sessions*",
    "*dictation-history*", "*mcp-oauth-locks*", "~/.ssh", "~/.ssh/*", "~/.gnupg*",
    "~/.config/gh", "~/.config/gh/*", "~/.git-credentials", "~/.netrc", "~/.aws*",
    "*.env", "~/.z0int/shadow*", "~/.hermes/*",
)

INSTRUCTION_FILES = {
    "claude": ("CLAUDE_CONFIG_DIR", "~/.claude", "CLAUDE.md"),
    "codex": ("CODEX_HOME", "~/.codex", "AGENTS.md"),
    "gemini": (None, "~/.gemini", "GEMINI.md"),
    "opencode": (None, "~/.config/opencode", "AGENTS.md"),
}
HARNESS_CONFIG = {
    "claude": ("CLAUDE_CONFIG_DIR", "~/.claude", "settings.json"),
    "codex": ("CODEX_HOME", "~/.codex", "config.toml"),
}

# Toolchain tags: binary -> tag. Presence only; nothing is executed.
TOOLCHAINS = {
    "python3": "python", "uv": "uv", "node": "node", "bun": "bun", "deno": "deno",
    "pnpm": "pnpm", "cargo": "cargo", "rustc": "rust", "go": "go", "java": "java",
    "gcc": "gcc", "clang": "clang", "cmake": "cmake", "ruby": "ruby", "zig": "zig",
    "dotnet": "dotnet", "swift": "swift", "ghc": "ghc", "julia": "julia", "R": "r",
    "nvcc": "cuda",
}
TOOL_DIRS = ("~/.cargo/bin", "~/.bun/bin", "~/.deno/bin", "~/.local/bin", "~/go/bin",
             "/usr/local/go/bin", "/usr/local/cuda/bin", "/opt/homebrew/bin", "/usr/local/bin")

# Harness id (registry) -> profile tag, and the fallback when the registry has no rows.
HARNESS_TAG = {"claude-code": "claude", "cursor-agent": "cursor"}
HARNESS_FALLBACK = {
    "claude-code": (["claude"], ["~/.claude"]), "codex": (["codex"], ["~/.codex"]),
    "gemini": (["gemini"], ["~/.gemini"]), "opencode": (["opencode"], ["~/.config/opencode"]),
}

LANGUAGES = ("python", "typescript", "javascript", "rust", "go", "c", "cpp", "java", "kotlin",
             "swift", "ruby", "shell", "lua", "zig", "haskell", "ocaml", "elixir", "csharp",
             "php", "scala", "julia", "r", "dart", "nix", "cuda", "html", "css", "sql")
EXTENSIONS = {
    ".py": "python", ".pyi": "python", ".ipynb": "python",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".vue": "javascript", ".svelte": "javascript",
    ".rs": "rust", ".go": "go", ".c": "c", ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift", ".rb": "ruby",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".lua": "lua", ".zig": "zig",
    ".hs": "haskell", ".ml": "ocaml", ".mli": "ocaml", ".ex": "elixir", ".exs": "elixir",
    ".cs": "csharp", ".php": "php", ".scala": "scala", ".jl": "julia", ".r": "r",
    ".dart": "dart", ".nix": "nix", ".cu": "cuda", ".cuh": "cuda",
    ".html": "html", ".htm": "html", ".css": "css", ".scss": "css", ".sql": "sql",
}
MARKERS = {
    "Cargo.toml": "rust", "package.json": "javascript", "tsconfig.json": "typescript",
    "deno.json": "typescript", "pyproject.toml": "python", "setup.py": "python",
    "requirements.txt": "python", "go.mod": "go", "CMakeLists.txt": "cpp",
    "build.gradle": "java", "pom.xml": "java", "Gemfile": "ruby", "mix.exs": "elixir",
    "build.zig": "zig", "Package.swift": "swift",
}
GITHUB_LANGUAGES = {
    "Python": "python", "Jupyter Notebook": "python", "TypeScript": "typescript",
    "JavaScript": "javascript", "Vue": "javascript", "Svelte": "javascript", "Rust": "rust",
    "Go": "go", "C": "c", "C++": "cpp", "Java": "java", "Kotlin": "kotlin", "Swift": "swift",
    "Ruby": "ruby", "Shell": "shell", "Lua": "lua", "Zig": "zig", "Haskell": "haskell",
    "OCaml": "ocaml", "Elixir": "elixir", "C#": "csharp", "PHP": "php", "Scala": "scala",
    "Julia": "julia", "R": "r", "Dart": "dart", "Nix": "nix", "Cuda": "cuda", "HTML": "html",
    "CSS": "css", "SCSS": "css",
}
# Fixed topic -> domain table (T3 only); no free-text inference.
TOPIC_DOMAINS = {
    "machine-learning": "ml", "deep-learning": "ml", "pytorch": "ml", "ml": "ml",
    "llm": "llm", "llms": "llm", "benchmark": "benchmarking", "benchmarking": "benchmarking",
    "evals": "benchmarking", "evaluation": "benchmarking", "frontend": "frontend",
    "react": "frontend", "webdev": "frontend", "systems": "systems", "compiler": "systems",
    "performance": "latency", "latency": "latency", "cli": "tooling", "devtools": "tooling",
    "agents": "agents", "ai-agents": "agents",
}
SKIP_DIRS = {"node_modules", "__pycache__", "venv", "Library", "snap", "go", "Trash",
             "target", "dist", "build", "vendor"}
MAX_DEPTH = 3
MAX_ENTRIES = 50000
MAX_CONFIG_BYTES = 1 << 20
MAX_TEXT_BYTES = 16384
NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
TAG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
REPOS_BUCKETS = ((0, "0"), (4, "1-4"), (19, "5-19"), (100, "20-100"))
RECENCY = ((30, "active_30d"), (180, "active_180d"), (365, "active_1y"))


# --- consent -----------------------------------------------------------------------
@dataclass(frozen=True)
class Consent:
    """The consent items granted for this run. T0 is always on."""
    granted: frozenset = frozenset()
    source: str = "default"

    def __post_init__(self):
        unknown = set(self.granted) - set(ITEMS)
        if unknown:
            raise ValueError(f"unknown consent items: {sorted(unknown)}")
        if self.source not in SOURCES:  # L-LLM: an LLM answer is never a consent source
            raise ValueError(f"consent source must be one of {SOURCES}")
        object.__setattr__(self, "granted", frozenset(self.granted))

    def allows(self, item: str) -> bool:
        return item in self.granted

    @property
    def tier(self) -> str:
        return max((ITEMS[i][0] for i in self.granted), default="T0", key=TIERS.index)


def consent_lines() -> list:
    """(item, text) for the T2 and T3 lines a TTY shows once ("Allow? [y/N]")."""
    return [(item, text) for item, (tier, text) in ITEMS.items() if tier in ("T2", "T3")]


def consent_for(flag: Optional[str] = None, answers: Optional[dict] = None) -> Consent:
    """§3.2 consent UX. `flag` is --profile (none|minimal|full); `answers` maps T2/T3
    items to the user's TTY answer and is None without a TTY. Only an explicit True
    answer grants a T2/T3 item; without a TTY and a grant the result is T0+T1."""
    if flag not in (None, "none", "minimal", "full"):
        raise ValueError("--profile must be none, minimal or full")
    if flag == "none":
        return Consent(frozenset(), "flag")
    if flag == "minimal":
        return Consent(T1_ITEMS, "flag")
    if answers is None:
        return Consent(T1_ITEMS, "flag" if flag else "default")
    yes = {item for item, answer in answers.items()
           if answer is True and item in ITEMS and ITEMS[item][0] in ("T2", "T3")}
    return Consent(T1_ITEMS | yes, "tty")


# --- safe local access ---------------------------------------------------------------
def _never(ctx, path: str) -> bool:
    form = ctx.tilde(path)
    return ctx.denied(path) or any(fnmatch.fnmatch(form, pat) for pat in NEVER_TOUCH)


def _read(ctx, path: str, limit: int) -> Optional[str]:
    """A bounded read of one listed signal file; never a never-touch path."""
    if _never(ctx, path) or not os.path.isfile(path):
        return None
    size = os.path.getsize(path)
    if size > limit:
        ctx.warn(f"profile: {ctx.tilde(path)} is larger than {limit} bytes; skipped")
        return None
    return ctx.read_text(path, limit)


def _dir_of(ctx, env_name, default) -> str:
    value = ctx.env.get(env_name) if env_name else None
    return ctx.expand(value) if value else ctx.expand(default)


def _search_dirs(ctx) -> list:
    dirs = [ctx.expand(d) for d in TOOL_DIRS] + list(ctx.search_dirs())
    return list(dict.fromkeys(d for d in dirs if d and not _never(ctx, d)))


# --- T0 ------------------------------------------------------------------------------
def _hw(ctx, host: Optional[dict], test_hw_root: Optional[str]) -> dict:
    override = _test_hw(ctx, test_hw_root)
    if override is not None:
        return override
    if host and host.get("hardware"):
        os_name = (host.get("os") or {}).get("os", "unknown")
        arch = (host.get("os") or {}).get("arch", "unknown")
        ram, gpu = host["hardware"].get("ram_gib", 0), host["hardware"].get("gpu") or {}
    else:
        from . import hardware
        sysname, machine = ctx.uname
        os_name = {"Linux": "linux", "Darwin": "darwin"}.get(sysname, "unknown")
        arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64",
                "aarch64": "arm64"}.get(machine, "unknown")
        ram = hardware._ram(ctx, os_name) if os_name != "unknown" else 0
        gpu = hardware._gpu(ctx, os_name, arch) if os_name != "unknown" else {"class": "cpu"}
    return _hw_record(os_name, arch, ram, gpu)


def _hw_record(os_name, arch, ram, gpu) -> dict:
    out = {"os": os_name if os_name in ("linux", "darwin") else "unknown",
           "arch": arch if arch in ("x86_64", "arm64") else "unknown",
           "ram_gib": round(float(ram or 0), 1),
           "gpu": {"class": gpu.get("class") if gpu.get("class") in
                   ("nvidia", "amd", "apple", "intel_mac", "cpu") else "cpu"}}
    if isinstance(gpu.get("vram_gib"), (int, float)):
        out["gpu"]["vram_gib"] = round(float(gpu["vram_gib"]), 1)
    return out


def _test_hw(ctx, test_hw_root: Optional[str]):
    """Z0_TEST_HW is honoured only with Z0_TEST_MODE=1, a test root the caller passes
    explicitly, and a fixture under that root. Production never passes a root (H-T)."""
    path = ctx.env.get("Z0_TEST_HW")
    if not (path and test_hw_root and ctx.env.get("Z0_TEST_MODE") == "1"):
        return None
    real, root = os.path.realpath(path), os.path.realpath(test_hw_root)
    if not real.startswith(root + os.sep):
        return None
    with open(real, encoding="utf-8") as fh:
        data = json.load(fh)
    return _hw_record(data.get("os"), data.get("arch"), data.get("ram_gib"), data.get("gpu") or {})


def _toolchains(ctx) -> list:
    dirs = _search_dirs(ctx)
    return sorted({tag for binary, tag in TOOLCHAINS.items() if ctx.which(binary, dirs)})


def _harnesses(ctx, host: Optional[dict]) -> list:
    if host and isinstance(host.get("harnesses"), dict):
        return sorted({HARNESS_TAG.get(hid, hid) for hid, entry in host["harnesses"].items()
                       if (entry or {}).get("state") in ("installed", "config_only")
                       and TAG.match(HARNESS_TAG.get(hid, hid))})
    rows = (ctx.registry.get("harnesses") or {}).get("harnesses") or {}
    table = {hid: ((row.get("detect") or {}).get("binaries") or [],
                   [d for d in (row.get("detect") or {}).get("config_dirs") or []
                    if isinstance(d, str)])
             for hid, row in rows.items() if row.get("detect")} or HARNESS_FALLBACK
    dirs, found = _search_dirs(ctx), set()
    for hid, (binaries, config_dirs) in table.items():
        present = any(ctx.which(b, dirs) for b in binaries) or any(
            os.path.isdir(ctx.expand(d)) for d in config_dirs if not _never(ctx, ctx.expand(d)))
        tag = HARNESS_TAG.get(hid, hid)
        if present and TAG.match(tag):
            found.add(tag)
    return sorted(found)


def _instruction_files(ctx) -> dict:
    out = {}
    for harness, (env_name, default, name) in INSTRUCTION_FILES.items():
        path = os.path.join(_dir_of(ctx, env_name, default), name)
        info = None if _never(ctx, path) else ctx.stat(path)
        if info is None or not os.path.isfile(path):
            out[harness] = {"exists": False}
            continue
        mtime = _dt.datetime.fromtimestamp(info.st_mtime, _dt.timezone.utc).date().isoformat()
        out[harness] = {"exists": True, "size": int(info.st_size), "mtime": mtime}
    return out


# --- T1 ------------------------------------------------------------------------------
def _names(values) -> list:
    return sorted({str(v) for v in values if isinstance(v, str) and NAME.match(v)})


def json_names(text: str) -> tuple:
    """(top-level key names, MCP server names) of a Claude settings.json; values dropped."""
    try:
        data = json.loads(text)
    except ValueError:
        return [], []
    if not isinstance(data, dict):
        return [], []
    servers = data.get("mcpServers")
    result = _names(data.keys()), _names(servers.keys() if isinstance(servers, dict) else [])
    del data, servers
    return result


_HEADER = re.compile(r"^\s*\[\[?\s*([A-Za-z0-9_.\-\"' ]+?)\s*\]\]?\s*(?:#.*)?$")
_KEY = re.compile(r"^\s*([A-Za-z0-9_-]+(?:\s*\.\s*[A-Za-z0-9_-]+)*)\s*=\s*(.*)$")


def _parts(dotted: str) -> list:
    return [p.strip().strip("\"'") for p in dotted.split(".")]


def toml_names(text: str) -> tuple:
    """(top-level key names, MCP server names) of a TOML file, by line scan.

    Only table headers and the key part of `key = value` lines are kept; every value
    (including all of `[mcp_servers.*.env]`) is skipped unparsed and never stored."""
    keys, servers, table, closing = set(), set(), [], None
    for line in text.splitlines():
        if closing:  # inside a multi-line string value
            if closing in line:
                closing = None
            continue
        header = _HEADER.match(line)
        if header:
            table = _parts(header.group(1))
            keys.add(table[0])
            if table[0] == "mcp_servers" and len(table) > 1:
                servers.add(table[1])
            continue
        key = _KEY.match(line)
        if not key:
            continue
        rest = key.group(2).lstrip()
        for quote in ('"""', "'''"):
            if rest.startswith(quote) and rest.count(quote) == 1:
                closing = quote
        path = table + _parts(key.group(1))
        if not table:
            keys.add(path[0])
        if path[0] == "mcp_servers" and len(path) > 2:
            servers.add(path[1])
    return _names(keys), _names(servers)


_SECTION = re.compile(r"^\s*\[\s*([A-Za-z0-9.-]+)(?:\s+\"[^\"]*\")?\s*\]")
_USER_KEY = re.compile(r"^\s*(name|email)\s*=", re.I)


def git_identity_names(text: str) -> set:
    """Which of user.name / user.email a gitconfig sets. Values are never captured."""
    found, section = set(), ""
    for line in text.splitlines():
        header = _SECTION.match(line)
        if header:
            section = header.group(1).lower()
            continue
        key = _USER_KEY.match(line)
        if section == "user" and key:
            found.add(key.group(1).lower())
    return found


def _harness_config(ctx) -> dict:
    out = {}
    for harness, (env_name, default, name) in HARNESS_CONFIG.items():
        text = _read(ctx, os.path.join(_dir_of(ctx, env_name, default), name), MAX_CONFIG_BYTES)
        if text is None:
            continue
        keys, servers = json_names(text) if name.endswith(".json") else toml_names(text)
        del text
        out[harness] = {"keys": keys, "mcp_servers": servers}
    return out


def _git_identity(ctx) -> dict:
    found = set()
    xdg = ctx.env.get("XDG_CONFIG_HOME")
    for path in (ctx.expand("~/.gitconfig"),
                 os.path.join(ctx.expand(xdg) if xdg else ctx.expand("~/.config"), "git/config")):
        text = _read(ctx, path, MAX_CONFIG_BYTES)
        if text is not None:
            found |= git_identity_names(text)
            del text
    return {"name": "name" in found, "email": "email" in found}


# --- T2 / T3 -------------------------------------------------------------------------
def _histogram(counts: dict) -> dict:
    total = sum(counts.values())
    if not total:
        return {}
    shares = {lang: round(n / total, 2) for lang, n in counts.items()}
    return {lang: share for lang, share in sorted(shares.items()) if share >= 0.01}


def local_language_counts(ctx, roots) -> dict:
    """Count file extensions and marker files by NAME under `roots` (depth <= 3).
    Dot dirs, SKIP_DIRS and never-touch paths are not entered; no file is opened."""
    counts, seen, entries = {}, set(), 0
    for root in roots:
        start = ctx.expand(root)
        if not os.path.isdir(start) or _never(ctx, start):
            continue
        frontier = [(start, 0)]
        while frontier and entries < MAX_ENTRIES:
            current, depth = frontier.pop(0)
            real = os.path.realpath(current)
            if real in seen:
                continue
            seen.add(real)
            try:
                listing = sorted(os.scandir(current), key=lambda e: e.name)
            except OSError:
                continue
            for entry in listing:
                entries += 1
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if (depth < MAX_DEPTH and not entry.name.startswith(".")
                                and entry.name not in SKIP_DIRS and not _never(ctx, entry.path)):
                            frontier.append((entry.path, depth + 1))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                lang = MARKERS.get(entry.name) or EXTENSIONS.get(os.path.splitext(entry.name)[1].lower())
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1
    return counts


def _gh(ctx):
    """The gh binary when it is installed and logged in, else (None, reason)."""
    gh = ctx.which("gh", _search_dirs(ctx))
    if gh is None:
        return None, "gh not installed"
    status = ctx.run([gh, "auth", "status", "--hostname", "github.com"], timeout=15)
    if not status.ok:
        return None, "gh not logged in"
    return gh, None


def _gh_values(ctx, gh, endpoint: str, jq: str, paginate: bool = True):
    argv = [gh, "api", *(["--paginate"] if paginate else []), endpoint, "--jq", jq]
    result = ctx.run(argv, timeout=60)
    if not result.ok:
        ctx.warn(f"profile: gh api {endpoint.split('?')[0]} failed")
        return None
    values = []
    for line in result.out.splitlines():
        try:
            values.append(json.loads(line))
        except ValueError:
            continue
    return values


OWN_REPOS = "user/repos?visibility=public&affiliation=owner&per_page=100"
PUBLIC_SOURCE = "select((.fork | not) and (.private | not))"


def _parse_time(text):
    try:
        return _dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _recency(pushed: list, now: _dt.datetime) -> Optional[str]:
    times = [t for t in (_parse_time(p) for p in pushed if p) if t is not None]
    if not times:
        return None
    days = (now - max(times)).days
    for limit, label in RECENCY:
        if days <= limit:
            return label
    return "dormant"


def _bucket(n: int) -> str:
    for limit, label in REPOS_BUCKETS:
        if n <= limit:
            return label
    return "101+"


def _now(ctx) -> _dt.datetime:
    if ctx.now:
        parsed = _parse_time(ctx.now)
        if parsed is not None:
            return parsed
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


# --- profile ---------------------------------------------------------------------------
def _guard(ctx, name, fn, default):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - detectors never raise (§4, §3.6 fallback 4)
        ctx.warn(f"profile: {name} failed: {type(exc).__name__}")
        return default


def detect(ctx, consent: Optional[Consent] = None, host: Optional[dict] = None,
           interests=(), contrib_done: int = 0, test_hw_root: Optional[str] = None) -> dict:
    """The profile for `consent` (default: T0 only). Never raises."""
    consent = consent or Consent()
    now = _now(ctx)
    profile = {"schema": SCHEMA, "tier": "T0",
               "detected_at": now.isoformat().replace("+00:00", "Z"),
               "consent": {"granted": sorted(consent.granted), "source": consent.source}}
    profile["hw"] = _guard(ctx, "hw", lambda: _hw(ctx, host, test_hw_root),
                           _hw_record("unknown", "unknown", 0, {"class": "cpu"}))
    profile["toolchains"] = _guard(ctx, "toolchains", lambda: _toolchains(ctx), [])
    profile["harnesses"] = _guard(ctx, "harnesses", lambda: _harnesses(ctx, host), [])
    profile["instruction_files"] = _guard(ctx, "instruction_files", lambda: _instruction_files(ctx), {})
    used = {"T0"}
    if consent.allows("t1.harness_keys"):
        profile["harness_config"] = _guard(ctx, "harness_config", lambda: _harness_config(ctx), {})
        used.add("T1")
    if consent.allows("t1.git_identity"):
        profile["git_identity"] = _guard(ctx, "git_identity", lambda: _git_identity(ctx),
                                         {"name": False, "email": False})
        used.add("T1")
    experience = {"contrib_done": max(0, int(contrib_done or 0))}
    sources, histograms = [], []
    if consent.allows("t2.local_languages"):
        roots = (ctx.registry.get("onboarding") or {}).get("checkout_roots") or ["~/workspace"]
        counts = _guard(ctx, "local_languages", lambda: local_language_counts(ctx, roots), {})
        histograms.append(_histogram(counts))
        sources.append("local_repos")
        used.add("T2")
    github_items = [i for i in ("t2.github_languages", "t3.repo_names", "t3.topics",
                                "t3.starred_languages") if consent.allows(i)]
    gh = None
    if github_items:
        gh, why = _guard(ctx, "gh", lambda: _gh(ctx), (None, "gh failed"))
        if gh is None:
            ctx.warn(f"profile: {why}; GitHub signals skipped")
    if gh and consent.allows("t2.github_languages"):
        rows = _guard(ctx, "github_languages", lambda: _gh_values(
            ctx, gh, OWN_REPOS, f".[] | {PUBLIC_SOURCE} | [.language, .pushed_at] | @json"), None)
        if rows is not None:
            rows = [r for r in rows if isinstance(r, list) and len(r) == 2]
            tally = {}
            for language, _ in rows:
                tag = GITHUB_LANGUAGES.get(language)
                if tag:
                    tally[tag] = tally.get(tag, 0) + 1
            histograms.append(_histogram(tally))
            sources.append("github")
            recency = _recency([p for _, p in rows], now)
            if recency:
                profile["recency"] = recency
            experience["repos_bucket"] = _bucket(len(rows))
            used.add("T2")
    if histograms:
        merged = {}
        for hist in histograms:
            for lang, share in hist.items():
                merged[lang] = merged.get(lang, 0) + share
        profile["languages"] = _histogram({k: v for k, v in merged.items() if k in LANGUAGES})
        profile["language_sources"] = sources
    tags = {t for t in interests or () if isinstance(t, str) and TAG.match(t)}
    t3 = {}
    if gh and consent.allows("t3.repo_names"):
        names = _guard(ctx, "repo_names", lambda: _gh_values(
            ctx, gh, OWN_REPOS, f".[] | {PUBLIC_SOURCE} | .name | @json"), None)
        if names is not None:
            t3["repo_names"] = sorted({n for n in names if isinstance(n, str) and NAME.match(n)})
    if gh and consent.allows("t3.topics"):
        topics = _guard(ctx, "topics", lambda: _gh_values(
            ctx, gh, OWN_REPOS, f".[] | {PUBLIC_SOURCE} | (.topics // []) | @json"), None)
        if topics is not None:
            flat = sorted({t for row in topics if isinstance(row, list) for t in row
                           if isinstance(t, str) and TAG.match(t)})
            t3["topics"] = flat
            tags |= {TOPIC_DOMAINS[t] for t in flat if t in TOPIC_DOMAINS}
    if gh and consent.allows("t3.starred_languages"):
        starred = _guard(ctx, "starred", lambda: _gh_values(
            ctx, gh, "user/starred?per_page=100", ".[] | .language | @json", paginate=False), None)
        if starred is not None:
            tally = {}
            for language in starred:
                tag = GITHUB_LANGUAGES.get(language)
                if tag:
                    tally[tag] = tally.get(tag, 0) + 1
            t3["starred_languages"] = _histogram(tally)
    if consent.allows("t3.instruction_text"):
        texts = {}
        for harness, (env_name, default, name) in INSTRUCTION_FILES.items():
            text = _guard(ctx, "instruction_text", lambda: _read(
                ctx, os.path.join(_dir_of(ctx, env_name, default), name), MAX_TEXT_BYTES), None)
            if text is not None:
                texts[harness] = text
        t3["instruction_text"] = texts
    if t3:
        profile["t3"] = t3
        used.add("T3")
    profile["interests"] = sorted(tags)
    profile["experience"] = experience
    profile["tier"] = max(used, key=TIERS.index)
    profile["warnings"] = sorted(w for w in ctx.warnings if w.startswith("profile:"))
    return profile


def public_view(profile: dict) -> dict:
    """The profile without T3 data: the only form an LLM prompt or a receipt may use."""
    return {k: v for k, v in profile.items() if k != "t3"}


def minimal_profile(ctx) -> dict:
    """§3.6 fallback 4: T0 without any probe, when detection itself failed."""
    return {"schema": SCHEMA, "tier": "T0",
            "detected_at": _now(ctx).isoformat().replace("+00:00", "Z"),
            "consent": {"granted": [], "source": "default"},
            "hw": _hw_record("unknown", "unknown", 0, {"class": "cpu"}),
            "toolchains": [], "harnesses": [], "instruction_files": {}, "interests": [],
            "experience": {"contrib_done": 0},
            "warnings": ["profile: detection failed; T0 fallback"]}


def write(profile: dict, path: str) -> str:
    """Atomically write `profile` to `path` with mode 0600 (directory 0700)."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".profile-", suffix=".json", dir=folder)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    os.chmod(path, 0o600)
    return path


def run(ctx, consent: Optional[Consent] = None, host: Optional[dict] = None,
        out: Optional[str] = None, **kwargs) -> dict:
    """Detect and always write profile.json (default ~/.z0int/contribute/profile.json)."""
    try:
        profile = detect(ctx, consent, host, **kwargs)
    except Exception:  # noqa: BLE001 - detect already guards; this is the last resort
        profile = minimal_profile(ctx)
    write(profile, out or ctx.expand(DEFAULT_PATH))
    return profile
