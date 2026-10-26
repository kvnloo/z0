#!/usr/bin/env bash
# Stage 0 of `./z0 onboard` (design §1.3): no Python needed.
#
# Needs bash, curl or wget, tar, and sha256sum or `shasum -a 256`. Gets a python
# >= 3.10 and PyYAML into $Z0_HOME/venv, then re-execs `python -m z0 onboard ...`.
#
# Writes ONLY under $Z0_HOME/bootstrap and $Z0_HOME/venv (law P0). Never uses
# --break-system-packages, never writes to a system Python, never runs sudo.
# Downloading uv or a CPython is a toolchain write: it needs --yes, or a [y/N] on a
# TTY that shows URL, version, sha256 and target. Without consent: exit 3 and print
# the manual commands. Effects are journaled to $Z0_HOME/bootstrap/stage0.jsonl.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
Z0_HOME="${Z0_HOME:-$HOME/.z0}"
REG="$ROOT/registry/toolchains.yaml"
LOCK="$ROOT/requirements.lock"
BOOT="$Z0_HOME/bootstrap"
VENV="$Z0_HOME/venv"
JOURNAL="$BOOT/stage0.jsonl"
PY_VERSION="3.12"

say() { printf 'z0 stage0: %s\n' "$*" >&2; }

# --- the uv pin, read from registry/toolchains.yaml without Python ----------------
uv_version() {
  awk '/^  uv:$/ {f=1; next} f && /^  [a-z]/ {f=0} f && $1 == "version:" {gsub(/"/, "", $2); print $2; exit}' "$REG"
}
uv_pin() { # $1 = os-arch key -> "target sha256"
  awk -v key="$1:" '
    /^  uv:$/ {f=1; next}
    f && /^  [a-z]/ {f=0}
    f && $1 == key {
      t = $0; sub(/.*target: */, "", t); sub(/,.*/, "", t)
      s = $0; sub(/.*sha256: */, "", s); sub(/[ }].*/, "", s)
      print t, s; exit
    }' "$REG"
}

if [[ "${1:-}" == "__uv_pin" ]]; then # test hook: print the parsed pin
  printf '%s %s\n' "$(uv_version)" "$(uv_pin "$2")"
  exit 0
fi

os_arch() {
  local os arch
  case "$(uname -s)" in Linux) os=linux ;; Darwin) os=darwin ;; *) os=unsupported ;; esac
  case "$(uname -m)" in x86_64 | amd64) arch=x86_64 ;; aarch64 | arm64) arch=arm64 ;; *) arch=unsupported ;; esac
  printf '%s-%s\n' "$os" "$arch"
}

YES=0
for arg in "$@"; do [[ "$arg" == "--yes" ]] && YES=1; done

journal() { # $1 step, $2 path
  mkdir -p "$BOOT"
  printf '{"stage":"stage0","step":"%s","path":"%s","ts":"%s"}\n' "$1" "${2/#$HOME/\~}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$JOURNAL"
}

own() { # mark a dir z0-owned
  printf 'stage0\n' > "$1/.z0-owned"
}

consent() { # $1 = what will be downloaded; return 0 only with --yes or a TTY yes
  ((YES)) && return 0
  if [[ -t 0 && -t 2 ]]; then
    printf '%s\nProceed? [y/N] ' "$1" >&2
    local answer
    read -r answer || return 1
    [[ "$answer" == y || "$answer" == Y || "$answer" == yes ]]
    return
  fi
  return 1
}

py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' > /dev/null 2>&1; }

find_python() {
  local dirs=() d n
  IFS=: read -r -a dirs <<< "${PATH:-}"
  dirs+=("$HOME/.local/bin" /opt/homebrew/bin "$HOME/.pyenv/shims" "$HOME/.local/share/mise/shims")
  for d in "${dirs[@]}"; do
    for n in python3 python3.13 python3.12 python3.11 python3.10; do
      [[ -x "$d/$n" ]] || continue
      # macOS: /usr/bin/python3 is a stub that opens a GUI prompt without the CLT.
      if [[ "$(uname -s)" == Darwin && "$d/$n" == /usr/bin/python3 ]] && ! xcode-select -p > /dev/null 2>&1; then
        continue
      fi
      if py_ok "$d/$n"; then
        printf '%s\n' "$d/$n"
        return 0
      fi
    done
  done
  for d in "$BOOT"/python/cpython-*/bin; do
    [[ -x "$d/python3" ]] && py_ok "$d/python3" && { printf '%s\n' "$d/python3"; return 0; }
  done
  return 1
}

find_uv() {
  local ver
  ver="$(uv_version)"
  if command -v uv > /dev/null 2>&1; then command -v uv; return 0; fi
  for cand in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" "$BOOT/uv/$ver/uv"; do
    [[ -x "$cand" ]] && { printf '%s\n' "$cand"; return 0; }
  done
  return 1
}

fetch() { # $1 url, $2 out
  if command -v curl > /dev/null 2>&1; then
    curl -fsSL --proto '=https' --tlsv1.2 -o "$2" "$1"
  elif command -v wget > /dev/null 2>&1; then
    wget -q -O "$2" "$1"
  else
    say "needs curl or wget"; return 1
  fi
}

sha256() {
  if command -v sha256sum > /dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

manual_and_exit() { # no consent: print the commands, exit 3 (design §1.2)
  local ver="$1" url="$2" sha="$3"
  say "a python >= 3.10 is needed and none was found; installing one needs consent."
  cat >&2 << EOF
Re-run with --yes, or do it by hand:
  curl -fsSLo uv.tar.gz '$url'
  echo '$sha  uv.tar.gz' | sha256sum -c -
  mkdir -p '$BOOT/uv/$ver' && tar -xzf uv.tar.gz -C '$BOOT/uv/$ver' --strip-components=1
  UV_PYTHON_INSTALL_DIR='$BOOT/python' '$BOOT/uv/$ver/uv' python install $PY_VERSION
EOF
  exit 3
}

umask 077
PY="$(find_python || true)"
UV="$(find_uv || true)"
export UV_CACHE_DIR="$BOOT/uv-cache" UV_PYTHON_INSTALL_DIR="$BOOT/python" \
  UV_PYTHON_BIN_DIR="$BOOT/python/bin" UV_NO_MODIFY_PATH=1 PIP_NO_INPUT=1
unset PIP_BREAK_SYSTEM_PACKAGES

if [[ -z "$PY" ]]; then
  key="$(os_arch)"
  ver="$(uv_version)"
  read -r target sum <<< "$(uv_pin "$key")"
  [[ -n "${target:-}" ]] || { say "no pinned uv for $key"; exit 1; }
  url="https://github.com/astral-sh/uv/releases/download/$ver/uv-$target.tar.gz"
  what="Download uv $ver ($url, sha256 $sum) into $BOOT/uv/$ver, then CPython $PY_VERSION into $BOOT/python."
  [[ -n "$UV" ]] && what="Download CPython $PY_VERSION with $UV into $BOOT/python."
  consent "$what" || manual_and_exit "$ver" "$url" "$sum"
  mkdir -p "$BOOT"
  own "$BOOT"
  if [[ -z "$UV" ]]; then
    tmp="$BOOT/uv-$ver.tar.gz"
    fetch "$url" "$tmp"
    got="$(sha256 "$tmp")"
    if [[ "$got" != "$sum" ]]; then
      rm -f "$tmp"
      say "uv checksum mismatch: got $got, want $sum"
      exit 1
    fi
    mkdir -p "$BOOT/uv/$ver"
    tar -xzf "$tmp" -C "$BOOT/uv/$ver" --strip-components=1
    rm -f "$tmp"
    UV="$BOOT/uv/$ver/uv"
    journal uv "$BOOT/uv/$ver"
  fi
  "$UV" python install "$PY_VERSION"
  journal python "$BOOT/python"
  PY="$(find_python || true)"
  [[ -n "$PY" ]] || { say "uv did not produce a python >= 3.10"; exit 1; }
fi

if ! { [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -c 'import yaml' 2> /dev/null; }; then
  mkdir -p "$BOOT"
  own "$BOOT"
  if [[ -n "$UV" ]]; then
    "$UV" venv --quiet --python "$PY" "$VENV"
    "$UV" pip install --quiet -p "$VENV/bin/python" --require-hashes -r "$LOCK"
  else
    "$PY" -m venv "$VENV"
    "$VENV/bin/python" -m pip install --quiet --no-cache-dir --disable-pip-version-check \
      --require-hashes -r "$LOCK"
  fi
  own "$VENV"
  journal venv "$VENV"
fi

if [[ -n "${Z0_STAGE0_DRY_EXEC:-}" ]]; then # test hook: show the re-exec instead of running it
  printf 'exec %s -m z0 %s\n' "$VENV/bin/python" "$*"
  exit 0
fi
export PYTHONPATH="$ROOT/lib${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
exec "$VENV/bin/python" -m z0 "$@"
