# Shared formal-laws toolkit (experimental)

`z0` owns the installer and verification tooling, not runtime policy. The domain's
hand-written twin remains its runtime choke point. A Bend verdict does not grant
permission and does not attest that production source implements the model.

## Commands

From a consumer repository, use the path to your reviewed z0 checkout:

```bash
/path/to/z0/z0 laws init demo
/path/to/z0/z0 laws check
/path/to/z0/z0 laws prove
/path/to/z0/z0 laws prove --all
```

Or select a consumer explicitly: `./z0 laws --root ./consumer check`.
Python 3.10+ is required (3.10 uses the pinned `tomli` dependency). Native Bend
proofs and parity currently require Linux x86_64, host clang, curl, tar and zstd.
No macOS archive is pinned; native checks are not advertised there.

- `init` creates a runnable identity-law example: MODEL, LAWS, PROOF, Python twin,
  exhaustive Boolean parity, and a killed mutation. Replace these examples with
  the domain's real contracts. Existing declarations/files are never overwritten.
- `check` runs **all declared domains**, not only touched files. It requires real
  pinned Bend execution for parity and mutation. Empty or skipped law-test suites
  fail instead of being reported green. It does not run the full positive proof.
- `prove` runs `bend PROOF.bend --verdict` unless the local success lock matches.
  An unchanged run writes an explicit `status: unchanged` receipt; it is **not** a
  newly executed proof. `--all` ignores unchanged locks and must be used in CI.

## Manifest

One root `laws.toml` declares all domains:

```toml
toolchain = "bend-2.0.34"

[[domain]]
name = "onboard"
dir = "bend/onboard"
twin = "lib/z0/onboard/kernel.py"
parity = "tests/onboard/test_kernel_twin.py"
mutation = "tests/onboard/test_kernel_mutation.py"
gate = []
```

Names must be unique lowercase identifiers. The `dir`, `twin`, `parity` and
`mutation` paths are required and repository-relative; absolute paths, parent
traversal, and symlink escapes are rejected. `critic = "gdp"` and `gate` paths are
reserved metadata only: this WP1–3 implementation does not run a critic, enforce
gate call sites, or configure branch protection.

## Pins, caches and scratch

`lib/laws/toolchain.json` is the only manifest. It pins the official Bend 2.0.34
and Lean 4.34.0 archives, their SHA-256 digests, the Bend executable/base/checker
source digests, and the explicit false trust declarations. `bootstrap.sh` reads
archive locations and hashes from that manifest.

Defaults (respecting `XDG_CACHE_HOME` when set):

- Toolchain: `$HOME/.cache/z0/toolchains/<sha256(manifest bytes)>/`.
- Native checker: `$HOME/.cache/z0/checker/<input hash>/`. The key is SHA-256 of a
  length-delimited JSON array containing the SHA-256 of `bendtt.lean`, the SHA-256
  of the Lean executable, and the exact host `clang --version` output.
- Scratch: explicit `TMPDIR`, otherwise `$HOME/.cache/z0/work/`.

Set TMPDIR to an owned, non-system-temp directory, for example:

```bash
mkdir -p "$HOME/tmp/lawsbench"
TMPDIR="$HOME/tmp/lawsbench" ./z0 laws prove --all
```

Cache/scratch paths resolving under `/tmp` are refused, including symlinks.
Installed artifacts are sealed with file digests and symlink targets, made
read-only on creation, and rehashed before reuse. Missing, stale, modified,
escaping or unlisted artifacts fail closed; they are not silently rebuilt over
corrupt entries. Builds use locked, same-filesystem staging directories. Hash
validation is not a defense against a malicious same-user process rewriting both
artifacts and local metadata; the cache is an optimization, not an attestation.

The benchmark-only `Z0_LAWS_FRESH_CHECKER=1` lane reproduces original isolated-HOME
checker compilation with supplied Bend/Lean paths. Ordinary commands should not
set it. Normal verification ignores ambient `BENDTT`, installs the pinned
archives, and supplies only its validated checker.

## Locks and receipts

`.z0/laws.lock` maps each domain to its name, SHA-256 input identity, toolchain,
verdict and UTC date. The input identity includes **all** `.bend` files in that
domain (including imported helpers), the pin manifest and the shared verifier /
cache implementation. A failed forced recheck invalidates the previous success.
Malformed lock records fail closed. Lock writes are atomic and serialized.

`.z0/laws.receipt.json` records `proven`, `unchanged` or `failed`. Both lock and
receipt are local ignored files. CI uses `prove --all`; a forged local lock must
never be treated as CI proof. The existing onboard CI now uses the shared CLI;
no reusable workflow or downstream-repository migration was added.

## Measurement and verification

See [BENCH-2026-10-26.md](BENCH-2026-10-26.md) for raw cold/warm measurements,
method limitations and the evidence supporting the checker cache.

Run lightweight regressions with:

```bash
PYTHONPATH=lib python3 -m unittest tests.test_laws tests.test_laws_bench -v
./z0 laws prove --all
./z0 laws check
scripts/public-leak-check
```

The full repository suite is `PYTHONPATH=lib python3 -m unittest discover -v`.
Direct discovery without Bend environment intentionally skips the two native
law tests; `z0 laws check` executes them and permits no skips. Full pinned-suite
verification can run discovery within `laws.verifier.verifier_environment()`
while applying the returned environment and `Z0_REQUIRE_BEND=1`.

The pre-existing detected-host schema rejects personal `/home/…` temp paths in
fake-host fixtures. Thus full discovery with the benchmark's home-based TMPDIR
fails that schema test; use a non-personal, non-`/tmp` scratch directory for full
repository discovery. Do not loosen the schema or skip that test.

### Final local qualification

- Full pinned discovery: **175 tests run**, 0 failures, 1 skip (the optional
  external `z0-hosts-template` checkout was absent). Native parity and mutation
  tests executed; they were not skipped. Test runner time: 28.379 seconds.
- Targeted toolkit and benchmark regression suite: **11 tests**, all passed.
- Onboard command: **7 tests**, all passed; 23 Bend mutants and 13 Python mutants
  rejected, with the positive reference law battery passing.
- Fresh consumer: `init demo`, 2-test `check`, initial `proven`, then `unchanged`,
  content-change `proven`, false-law `failed`, and restored-law `proven` all
  behaved as expected against the real pinned verifier.
- `scripts/public-leak-check`: **162 files**, 0 findings. `git diff --check` and
  shell syntax checks passed.
- No push, PR, hosted CI, macOS qualification, reusable workflow, downstream
  migration, gdp critic or branch-protection setup was performed in WP1–3.
