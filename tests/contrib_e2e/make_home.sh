#!/usr/bin/env bash
# Build a synthetic contributor HOME (contributor spec §4.1): fixture repos (marker and
# empty source files only), git identity, harness configs with CANARY values planted,
# a canary gh token, and stub toolchains for the profile's facts.
#   make_home.sh PROFILE HOME CANARY
set -euo pipefail
PROFILE="$1"; H="$2"; CANARY="$3"
mkdir -p "$H/code" "$H/.local/bin" "$H/.claude" "$H/.codex" "$H/.config/gh"
stub() { printf '#!/bin/sh\necho "%s 0.0.0-stub"\n' "$1" > "$H/.local/bin/$1"; chmod 755 "$H/.local/bin/$1"; }
repo() { # repo NAME FILE...
  local d="$H/code/$1"; shift
  mkdir -p "$d"
  for f in "$@"; do mkdir -p "$(dirname "$d/$f")"; : > "$d/$f"; done
  git -C "$d" init -q && git -C "$d" add -A && git -C "$d" -c user.name=fixture -c user.email=fixture@example.invalid commit -qm init
}
case "$PROFILE" in
  frontend)
    repo web-app package.json vite.config.ts src/App.tsx src/main.tsx tsconfig.json
    repo ui-kit package.json src/index.ts src/button.tsx
    stub node; stub bun; stub npm ;;
  ml-research)
    repo trainer pyproject.toml train.py notebooks/explore.ipynb requirements.txt
    repo evals pyproject.toml eval.py data/README.md ;;
  systems-rust)
    repo fastpath Cargo.toml src/main.rs src/lib.rs
    repo proxy go.mod main.go
    stub cargo; stub rustc; stub go ;;
  *) echo "unknown profile $PROFILE" >&2; exit 2 ;;
esac
cat > "$H/.gitconfig" <<G
[user]
	name = Fixture Contributor
	email = fixture-$CANARY@example.invalid
[core]
	hooksPath = $H/.config/git-hooks
G
mkdir -p "$H/.config/git-hooks"
printf '#!/bin/sh\necho "push blocked by the e2e harness" >&2\necho "$(date -u +%%FT%%TZ) push $*" >> "%s/.e2e-push.log"\nexit 1\n' "$H" \
  > "$H/.config/git-hooks/pre-push"
chmod 755 "$H/.config/git-hooks/pre-push"
cat > "$H/.claude/settings.json" <<J
{"env": {"E2E_CANARY_SETTING": "$CANARY-claude-settings"}}
J
cat > "$H/.codex/config.toml" <<T
[mcp_servers.canary]
command = "false"
enabled = false

[mcp_servers.canary.env]
E2E_CANARY_TOKEN = "$CANARY-codex-mcp"
T
cat > "$H/.config/gh/hosts.yml" <<Y
github.com:
    oauth_token: gho_$CANARY
    user: fixture-contributor
Y
chmod 600 "$H/.config/gh/hosts.yml"
# fake gh (spec §4.1): reads return empty JSON, every write verb is logged and fails
cat > "$H/.local/bin/gh" <<'GH'
#!/bin/sh
LOG="$HOME/.e2e-gh.log"
echo "$(date -u +%FT%TZ) gh $*" >> "$LOG"
case "$1 $2" in
  "issue comment"|"issue edit"|"issue create"|"issue close"|"pr create"|"pr comment"|"pr edit"|"pr merge"|"label create"|"repo fork"|"repo create")
    echo "WRITE gh $*" >> "$LOG"; echo "gh: writes are blocked in this test" >&2; exit 1 ;;
  "auth status") echo "github.com: logged in as fixture-contributor (fake)"; exit 0 ;;
  "auth token") echo "gh: token unavailable in this test" >&2; exit 1 ;;
esac
case "$1" in
  api) case " $* " in *" -X POST "*|*" --method POST "*|*" -X PATCH "*|*" -X PUT "*|*" -X DELETE "*|*" -f "*|*" -F "*)
         echo "WRITE gh $*" >> "$LOG"; exit 1 ;; esac
       echo "[]"; exit 0 ;;
  issue|pr) echo "[]"; exit 0 ;;
esac
echo "[]"
GH
chmod 755 "$H/.local/bin/gh"
