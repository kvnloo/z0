#!/usr/bin/env bash
# Extract the official verifier only inside a caller-owned destination.
set -euo pipefail
[ "$(uname -s)-$(uname -m)" = Linux-x86_64 ] || {
  echo 'z0 onboard law verifier requires Linux x86_64 (including the Linux MBP)' >&2
  exit 1
}
root=$(realpath -m "${1:?usage: bootstrap.sh OWNED_DESTINATION}")
case "$root" in /tmp|/tmp/*) echo 'toolchain installation under /tmp is forbidden' >&2; exit 1;; esac
export TMPDIR="${TMPDIR:-$root/work}"
case "$(realpath -m "$TMPDIR")" in /tmp|/tmp/*) echo 'TMPDIR under /tmp is forbidden' >&2; exit 1;; esac
mkdir -p "$TMPDIR"
mkdir -p "$root/downloads"
manifest="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/toolchain.json"
mapfile -t pins < <(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print("\n".join(p[k] for k in ("url", "sha256", "lean_url", "lean_sha256")))' "$manifest")
bend=${BEND_ARCHIVE:-$root/downloads/bend-2.0.34-linux-x64.tar.gz}
lean=${LEAN_ARCHIVE:-$root/downloads/lean-4.34.0-linux.tar.zst}
if [ ! -f "$bend" ]; then
  curl --fail --location --max-time 180 --max-filesize 40000000 --output "$bend" \
    "${pins[0]}"
fi
if [ ! -f "$lean" ]; then
  curl --fail --location --max-time 600 --max-filesize 600000000 --output "$lean" \
    "${pins[2]}"
fi
printf '%s  %s\n' "${pins[1]}" "$bend" | sha256sum --check --strict -
printf '%s  %s\n' "${pins[3]}" "$lean" | sha256sum --check --strict -
tar -xzf "$bend" -C "$root"
tar --zstd -xf "$lean" -C "$root"
printf 'BEND=%s/bend/bin/bend\nLEAN_BIN=%s/lean-4.34.0-linux/bin\n' "$root" "$root"
