"""A fake HOME for the contributor profile privacy tests (contributor spec §4.1, §4.3 G1-G5).

Every private file holds a distinct canary. Fixture repos hold marker files and empty
source files only. Every binary on the fake PATH is a stub that records an execution,
and `gh` is a fake that replays fixture lines for read-only `gh api` calls and logs
every call (any other verb is logged as a WRITE and fails).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CANARIES = {
    "settings_env": "Z0CANARY-settings-env-1f9a",
    "settings_mcp_env": "Z0CANARY-settings-mcp-env-77c2",
    "mcp_env": "Z0CANARY-mcp-env-value-5b0e",
    "mcp_env_key": "Z0CANARY_MCP_ENV_KEY",
    "codex_value": "Z0CANARY-codex-value-91d4",
    "codex_multiline": "Z0CANARY_MULTILINE_TABLE",
    "instruction": "Z0CANARY-instruction-text-2c8d",
    "credentials": "Z0CANARY-credentials-6a1b",
    "history": "Z0CANARY-history-0d3e",
    "transcript": "Z0CANARY-transcript-8e5f",
    "file_history": "Z0CANARY-file-history-4a7c",
    "paste_cache": "Z0CANARY-paste-cache-3b9d",
    "codex_auth": "Z0CANARY-codex-auth-5c2a",
    "attachments": "Z0CANARY-attachments-1e6f",
    "dictation": "Z0CANARY-dictation-7f0b",
    "oauth_locks": "Z0CANARY-oauth-locks-2d4c",
    "gh_token": "Z0CANARY-gh-token-9a8b",
    "ssh": "Z0CANARY-ssh-key-6c3d",
    "git_name": "Z0CANARY-git-name-4e1a",
    "git_email": "z0canary-git-email@example.com",
    "dotenv": "Z0CANARY-dotenv-8b2c",
}

# Never-touch paths of the spec (§3.2), relative to HOME.
NEVER_TOUCH = {
    ".claude/.credentials.json": "credentials",
    ".claude/history.jsonl": "history",
    ".claude/projects/-workspace-app/session.jsonl": "transcript",
    ".claude/file-history/abc/1": "file_history",
    ".claude/paste-cache/p1.txt": "paste_cache",
    ".codex/auth.json": "codex_auth",
    ".codex/attachments/a1.txt": "attachments",
    ".codex/dictation-history/d1.txt": "dictation",
    ".codex/mcp-oauth-locks/l1.lock": "oauth_locks",
    ".config/gh/hosts.yml": "gh_token",
    ".ssh/id_ed25519": "ssh",
    "workspace/web-app/.env": "dotenv",
}

CODEX_CONFIG = f'''# codex config fixture
model = "{CANARIES["codex_value"]}"
approval_policy = "never"
notes = """
[{CANARIES["codex_multiline"]}]
hidden = "not a table"
"""

[mcp_servers.z0int]
command = "z0int"
args = ["mcp"]

[mcp_servers.z0int.env]
{CANARIES["mcp_env_key"]} = "{CANARIES["mcp_env"]}"

[mcp_servers.other]
command = "other"
env = {{ KEY = "{CANARIES["mcp_env"]}" }}

[profiles.fast]
model = "{CANARIES["codex_value"]}"
'''

FAKE_GH = r'''#!/bin/sh
root="__ROOT__"
out() { while IFS= read -r line; do printf '%s\n' "$line"; done < "$root/gh/$1"; }
printf '%s\n' "$*" >> "$root/gh.log"
case "$1" in
  auth)
    [ "$2" = status ] && [ -e "$root/gh-logged-in" ] && exit 0
    exit 1 ;;
  api)
    shift
    for arg in "$@"; do
      case "$arg" in -X|--method|-f|-F|--field|--raw-field|--input)
        echo "WRITE $*" >> "$root/gh.log"; exit 1 ;; esac
    done
    all="$*"
    case "$all" in
      *user/starred*) out starred.lines ;;
      *pushed_at*) out languages.lines ;;
      *topics*) out topics.lines ;;
      *.name*) out names.lines ;;
      *) exit 1 ;;
    esac ;;
  *)
    echo "WRITE $*" >> "$root/gh.log"; exit 1 ;;
esac
'''

GH_LINES = {
    "languages.lines": ['["TypeScript","2026-10-20T00:00:00Z"]', '["Python","2026-01-01T00:00:00Z"]',
                        '[null,"2025-01-01T00:00:00Z"]'],
    "names.lines": ['"web-app"', '"ml-thing"', '"tiny"'],
    "topics.lines": ['["react","benchmark"]', '["machine-learning"]', '[]'],
    "starred.lines": ['"Rust"', '"Go"', '"Rust"', 'null'],
}

REPOS = {
    "workspace/web-app": ["package.json", "tsconfig.json", "src/a.ts", "src/b.tsx", "src/c.js"],
    "workspace/ml": ["pyproject.toml", "train.py", "notebooks/explore.ipynb"],
    "workspace/rs": ["Cargo.toml", "src/main.rs"],
    "workspace/.hidden": ["skip.py"],
    "workspace/web-app/node_modules/dep": ["index.js", "more.js"],
}

TOOLS = ("python3", "node", "cargo", "claude", "codex")


def _stub(path: Path, root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\ntouch "{root}/{path.name}-was-executed"\n')
    path.chmod(0o755)


def build(root: Path, logged_in: bool = True, with_gh: bool = True) -> dict:
    root = Path(root)
    home, bin_dir, sysroot = root / "home", root / "bin", root / "sysroot"
    for directory in (home, bin_dir, sysroot / "usr/bin", root / "gh"):
        directory.mkdir(parents=True, exist_ok=True)
    claude = home / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps({
        "model": "opus", "env": {"ANTHROPIC_API_KEY": CANARIES["settings_env"]},
        "permissions": {"allow": ["Bash(ls:*)"]},
        "mcpServers": {"z0": {"command": "z0", "env": {"TOKEN": CANARIES["settings_mcp_env"]}}},
    }))
    (claude / "CLAUDE.md").write_text(f"# my rules\n{CANARIES['instruction']}\n")
    codex = home / ".codex"
    codex.mkdir()
    (codex / "config.toml").write_text(CODEX_CONFIG)
    (codex / "AGENTS.md").write_text(f"codex rules {CANARIES['instruction']}\n")
    (home / ".gitconfig").write_text(
        f"[core]\n\teditor = vi\n[user]\n\tname = {CANARIES['git_name']}\n"
        f"\temail = {CANARIES['git_email']}\n")
    for relative, key in NEVER_TOUCH.items():
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CANARIES[key] + "\n")
    for repo, files in REPOS.items():
        for name in files:
            path = home / repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
    for tool in TOOLS:
        _stub(bin_dir / tool, root)
    if with_gh:
        (bin_dir / "gh").write_text(FAKE_GH.replace("__ROOT__", str(root)))
        (bin_dir / "gh").chmod(0o755)
    for name, lines in GH_LINES.items():
        (root / "gh" / name).write_text("\n".join(lines) + "\n")
    if logged_in:
        (root / "gh-logged-in").write_text("")
    env = {"HOME": str(home), "PATH": str(bin_dir), "USER": "someone", "LANG": "C"}
    return {"root": root, "home": home, "bin": bin_dir, "sysroot": sysroot, "env": env}


def gh_calls(fake: dict) -> list:
    log = fake["root"] / "gh.log"
    return log.read_text().splitlines() if log.exists() else []


def executed(fake: dict) -> list:
    return sorted(p.name for p in Path(fake["root"]).glob("*-was-executed"))


def tree_state(home: Path) -> dict:
    state = {}
    for dirpath, _dirs, files in os.walk(home):
        for name in files:
            path = Path(dirpath) / name
            info = path.stat()
            state[str(path)] = (info.st_size, info.st_mtime_ns, info.st_mode)
    return state
