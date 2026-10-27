# z0 onboard: final design

**Hub:** `kvnloo/z0` (grounded at main `7933914`: `./z0` bash launcher; `lib/z0/{__main__,commands,registry,generate}.py`, 654 lines; `registry/*.yaml`; `schemas/{component,repo}.schema.json`; `scripts/{registry-check,docs-generate,docs-check}`; no `tests/` dir).

**Law pattern copied from:** `the .files worktree/bend/host_layout/{MODEL,LAWS,PROOF}.bend` plus `toolchain.json`, with a Python twin whose test enumerates the whole domain.

**Base and grafts:**
- Base: Design 0 (deterministic core).
- From Design 2: a stage 0 that needs no Python, user-local pinned toolchains, `host_id` in `workspace.yaml`, public-ready gates, local-first cached LLM, degrade-with-asks, a no-Python CI image, an opt-in real-tailnet job, and a pairing QR that holds the code only.
- From Design 1: volatile-fact re-check before apply, closed bind classes, adopted units diffed and kept, a fake tailscale plus systemd container that reaches the 401 check, and adversarial fake-LLM tests.
- Appendix A maps every judge flaw to its fix.

---

## 0. Principles

1. **Four stages, each handing off a file.**
   - DETECT is read-only and writes `host.json`.
   - PLAN is a pure function `plan(host, registry, answers, mode, grants) -> plan.json`.
   - APPLY runs a plan that is already written, identified by its hash. It journals every effect.
   - VERIFY writes `receipt.json`.
2. **The registry is the plan source.** Component, harness, toolchain, hardware, consent and service rules are data in `registry/`. Code interprets the data and holds no host literals.
3. **Degrade, don't fail.** A feature that cannot run becomes `unavailable(reason)` plus an *ask* that shows the exact command to finish it. A failure blocks only the steps that depend on it. Independent components continue.
4. **Consent is explicit and enumerated.** `--auto` asks no *choice* questions. Writes outside z0's own home need either one enumerated go/no-go confirmation or `--yes`. Some actions are never automatic.
5. **Live code never runs from a mutable checkout.** Services, the interpreter shim, plugins and env files point only into immutable release dirs, owned venvs or owned toolchains.
6. **The LLM is a classifier, not a planner.** It picks from candidates the engine lists. The engine checks the pick again and freezes it. A replay never calls the LLM. `--llm=none` is a complete, tested path.

---

## 1. Entrypoint, UX and bootstrap

### 1.1 Stranger flow
```
git clone https://github.com/kvnloo/z0 && cd z0
./z0 onboard                 # TTY: asks "auto or guided?" (default auto). No TTY: same as --auto.
./z0 onboard --auto --yes    # the owner's "minimal": zero questions, end to end
./z0 onboard --auto          # zero choice questions; ONE go/no-go confirmation before writes outside ~/.z0
./z0 onboard --guided        # the owner's "full": asks every choice; deterministic default preselected
```

### 1.2 CLI surface (7 subcommands, all under `onboard`)
| Command | Writes | Purpose |
|---|---|---|
| `./z0 onboard [--auto\|--guided] [--yes] [--accept BUNDLES] [--profile P] [--with ids] [--without ids] [--pin-policy pinned\|tip] [--llm none\|local\|auto] [--answers FILE] [--plan-only]` | see §3 | detect, then plan, then show, then (confirm), then apply, then verify |
| `./z0 onboard plan [--stdout]` | run dir only (`--stdout`: nothing, if PyYAML is importable) | the dry run |
| `./z0 onboard apply <run-id>` | journaled | applies only that plan, checked by hash |
| `./z0 onboard verify` | receipt | acceptance checks; exits non-zero on a required failure |
| `./z0 onboard rollback [<run-id>] [--purge-bootstrap]` | journaled | reverse replay, owned artifacts only |
| `./z0 onboard accept <ask-id>...` | journaled | resolves a deferred ask (re-plans, then applies the delta) |
| `./z0 onboard pair dash [--sonic]` | none | phone pairing; shows the 6-char code, never a token |
| `./z0 onboard status` | none | the last receipt, open asks, drift |

Exit codes:
- 0: every required step passed.
- 1: a required step failed.
- 2: a usage error, or `--guided` without a TTY.
- 3: consent is needed but none was available (no TTY and no `--yes`).
- 4: refused by a law (for example a host mismatch).

**report.md order.** It is written for a zero-context reader:
1. **"What you need to do"**: the asks, sorted by impact. Each has a one-line reason and a command.
2. What was installed, from which SHA.
3. What is unavailable, and why.
4. Harness table.
5. LLM decisions.
6. Upstream gaps and stale docs that were found.

### 1.3 Launcher and stage 0 (no Python needed)
The `./z0` change touches only the `onboard` branch, so `init`, `status` and `doctor` behave as today:

```
if argv[1] == onboard and not importable(yaml) under $Z0_HOME/venv/bin/python:
    exec lib/z0/onboard/stage0.sh "$@"
```

`stage0.sh` needs bash, plus curl or wget, tar, and sha256sum or `shasum -a 256`. Steps:
1. Find a python ≥ 3.10. Search PATH, then `~/.local/bin`, `/opt/homebrew/bin`, `~/.pyenv/shims` and mise shims. On macOS, skip `/usr/bin/python3` when `xcode-select -p` fails, because the CLT stub would open a GUI prompt.
2. If none is found, uv is needed. Find an existing uv. If uv is also missing, download the uv pinned in `registry/toolchains.yaml` (version plus sha256 per os/arch) into `$Z0_HOME/bootstrap/uv/<ver>/`. This download is a toolchain write, so it needs consent: `--yes`, or a `[y/N]` on a TTY that shows URL, version, sha256 and target. Without consent, exit 3 and print the manual commands. Then run `uv python install 3.12` into `$Z0_HOME/bootstrap/python`.
3. Create `$Z0_HOME/venv` with `uv venv` or `python -m venv`. Install PyYAML from `requirements.lock` with `--require-hashes`. Never use `--break-system-packages`. Never write to system Python.
4. Write `.z0-owned` markers. Re-exec `PYTHONPATH=<z0>/lib $Z0_HOME/venv/bin/python -m z0 onboard "$@"`.

Stage 0 writes **only** under `$Z0_HOME/{bootstrap,venv}`. Its effects go into the first run's journal. `rollback --purge-bootstrap` removes them.

**Dry-run purity (law P0), stated precisely:**
- `plan`/`detect` never write outside `$Z0_HOME`.
- Inside `$Z0_HOME` they write only `bootstrap/`, `venv/`, `cache/git/` (origin mirrors, §6.2) and `onboard/runs/<id>/`.
- With `--stdout`, on a host where PyYAML already imports, they write zero bytes.

### 1.4 Run directory
`$Z0_HOME/onboard/runs/<utc>-<plan8>/` holds `host.json`, `questions.json`, `answers.yaml`, `plan.json`, `plan.diff.txt`, `journal.jsonl` (append, fsync per line), `backups/`, `receipt.json` and `report.md`. The dir is mode 0700 and files are 0600. `$Z0_HOME/onboard/current` points to the last applied run. `$Z0_HOME/onboard/.lock` is an fcntl lock that stops concurrent runs.

---

## 2. Registry changes (the plan source)

### 2.1 `registry/components.yaml`
- **Add `dash`** (`kvnloo/dash`, `revs: {app: <APP_REV>, bridge: <BRIDGE_REV>}`, `maturity: canary`, `execution: live`).
- **Add `z0evals`** (`kvnloo/z0evals`, `maturity: stable`).
- **Add an `onboard:` block to each component.** Fields:
  ```yaml
  onboard:
    requires: {tools: ["bun>=1.4.3", "git", "python>=3.10"], optional: ["ffmpeg", "tailscale"]}
    hardware: {os: [linux, darwin], arch: [x86_64, arm64], min_ram_gib: 2, min_disk_gib: 5, gpu: none}
    python:   {window: ">=3.10,<3.14", prefer: "3.11", venv: own}      # never shared (tokenomics skew)
    public_ready: [revs_on_origin, no_private_on_auto_path]            # §11.3 gates
    steps:    [ ... ]          # closed step kinds (§2.5); `when:` is structured data, not a language
    services: [ ... ]          # unit template id, bind class, port, health, start_order, limits
    secrets:  [{name: CEREBRAS_API_KEY, kind: env, required: false}]   # names only
    harness_integrations: [ ... ]
    acceptance: {tiers: [...]}  # from each repo spec's §8
    remediations: [retry_with_cpu_index, use_public_install, skip_web_tier_offline, mark_unavailable]
  ```
- **One source of truth.** The legacy `install.command`/`verify.command` stay for `z0 init`. A new `registry-check` rule **R-sync** asserts that each legacy command equals the shell projection of the `onboard` steps marked `legacy_projection: true`. `scripts/docs-generate` writes that projection, so the two cannot drift. A later phase makes `z0 init` call the engine and deletes the legacy fields.

### 2.2 `registry/profiles.yaml`
Profile names do not change. The membership proposal (owner decision D-3) adds no supplementals to profiles. Instead, the **`--auto` default target set** is the hardware profile plus `dash` plus `z0evals`. These are the three repos the owner named. Each one is gated, so dash on a host without a tailnet installs no unit (§8.3). `--without` removes any of them. Fix the `full` summary text: `full` contains shadow components.

### 2.3 `registry/harnesses.yaml`
Each row gets `detect:` and `policy:` blocks:
```yaml
claude-code:
  aodl_id: claude                 # catalog_gap until kvnloo/aodl adds it (WP-A1)
  detect:
    binaries: [claude]            # installed == binary resolves under the prepared PATH
    config_dirs: [{env: CLAUDE_CONFIG_DIR}, "~/.claude-home", "~/.claude"]
    pick: has_child:projects      # several matches -> all recorded; Z0INT_CLAUDE_PROJECTS_DIRS lists all
    session_stores: ["{config}/projects"]
    version_cmd: [claude, --version]
  policy: {configure: allowed, offload: allowed, exec_probe: allowed, dash_acp: claude-agent-acp}
grok:
  detect: {binaries: [grok], config_dirs: ["~/.grok"]}
  policy: {configure: never, offload: never, exec_probe: never, dash_acp: null, bridge_path: excluded}
```
- **Rows:** omp, hermes, codex, pi, deepseek (existing), plus claude-code, grok, cursor-agent (`configure/offload/exec_probe: never`), opencode, gemini, kimi, fx, dsh and codexbar.
- **Installed rule:** a harness counts as installed only when its binary resolves. A config dir alone gives `config_only`.
- **No unknown binary is ever run** (§4).

### 2.4 New registry files (two only)
- **`registry/toolchains.yaml`.** Per tool:
  - detect paths: `~/.bun/bin`, `~/.local/bin`, `~/.cargo/bin`, `/opt/homebrew/bin`, `~/.nvm/versions/node/*/bin`, and fnm/mise/volta shims
  - user-local install pins: uv, bun 1.4.3, node 22.x and rustup-init, each with a URL template and sha256 per os/arch, installed into `$Z0_HOME/toolchains/<tool>/<ver>`
  - a `system_pkg:` map (pacman/apt/dnf/brew for ffmpeg, git and tailscale). This map is **printed only, never run in auto**.

  `scripts/toolchains-bump` refreshes the versions and checksums. A monthly CI job flags stale pins.
- **`registry/onboarding.yaml`** holds:
  - consent classes and bundles (§3)
  - the hardware class table (§5)
  - unit/plist templates by id, bind classes `{loopback, tailnet_ipv4}` (a wildcard cannot be expressed), and reserved ports
  - the LLM policy: providers, order, model ids, budget, forbidden `[grok, cursor]`
  - the probe catalog, and denylists for reads and redaction (`<bulk-mount>`, `<owner-home>`, `/workspace/`, `<tailnet-name>`, `<tailnet-ip>`)

  It is validated by `schemas/onboarding.schema.json`.

### 2.5 Closed step kinds (`schemas/onboard-step.schema.json`)
Common fields: `id`, `component`, `kind`, `when` (a list of `{fact, op, value}`, evaluated by a 40-line matcher, never eval'd), `needs`, `consent` (C0/C1/C2 + bundle), `network`, `where` (`mirror|build|release|venv|home`), `probe` (idempotence), `effects`, `undo`, `verify`.

| kind | action | undo |
|---|---|---|
| `ensure_toolchain` | resolve; else a user-local pinned install with a sha256 check | remove the owned dir |
| `adopt_or_clone` | match by origin. A clean adopted tree is used in place for repo-local work. Otherwise create a z0-owned clone (`$Z0_HOME/repos/<name>`) from the mirror. Never checks out or moves an adopted tree | remove the clone only if this run created it |
| `build_tree` | `git clone --shared $Z0_HOME/cache/git/<repo>.git $Z0_HOME/build/<id>/<sha>`, check out `<sha>`, `git submodule update --init --recursive`, and `git lfs pull` when `.gitattributes` uses LFS. This tree **has** `.git`, so steps that need git metadata run here (rollout.py, dash scripts, static gates) | remove the owned tree |
| `stage_release` | copy `build/<id>/<sha>` without `.git` to `<release_root>/<id>/<sha>`, install deps **in the release**, write `deployed.json` | remove it if it is not `current` |
| `swap_current` | atomic symlink `<id>-current -> <sha>` | restore the previous target from the journal |
| `venv` / `pip_install` | `uv venv`/`uv pip install -p <venv>` with the index URL from the plan | remove the owned venv |
| `run` | argv only (no shell), `where`, env from an allowlist, timeout; `creates` or `probe` required | a declared `undo`, else `irreversible` (shown in the plan; never auto) |
| `write_file` | render a template atomically, umask 077 for env files, hash in the journal | delete if the hash is unchanged, else keep and report |
| `service_unit` | systemd `--user` unit or launchd plist from a z0 template; existing units are adopted and diffed | stop, disable, remove, restore the backup |
| `harness_plugin` | official CLI (claude/codex), OMP linker script, DSH patch; the config file is backed up first | uninstall plus restore the backup if the hash is unchanged |
| `delegate` | a repo's own onboarder through a versioned contract (§8.4) | the delegate's undo, plus a snapshot restore |
| `check` | acceptance probe, read-only | — |
| `ask` | a deferred item with its command; never executes | — |

`where` and the bind class are part of the schema, so `registry-check` can enforce S1 and S2 (§11) statically.

### 2.6 Repo-local `zer0.repo.yaml` `setup:`
- Optional. It is read **only from the pinned SHA in the z0 mirror** (`git -C cache/git/<repo>.git show <sha>:zer0.repo.yaml`), never from a working tree.
- It may hold repo-local steps (for example z0evals' generator order).
- The registry owns host-level and cross-repo steps.
- If both define the same step id, the registry wins and the plan reports the conflict.
- The `setup:` schema is added to `schemas/repo.schema.json`.

### 2.7 `registry-check` new rules
- R-sync (see §2.1).
- Every `run` step has `creates|probe` and a `where`.
- No step names a `configure: never` harness.
- No service has a non-closed bind or a `where` inside a checkout.
- No denylisted literal appears in the registry or in templates.
- Every component in the auto target set has `acceptance`.
- `generated/onboarding-matrix.md` is up to date.

---

## 3. Modes and consent

**Consent classes.**
- **C0, z0-private:** writes under `$Z0_HOME`, release roots, repo-local gitignored paths in a *clean* adopted checkout, and repo venvs.
- **C1, user-scoped and reversible.** It has four bundles:
  - `toolchains`: user-local pinned downloads into `$Z0_HOME/toolchains`.
  - `harness`: Claude/Codex plugin installs, OMP extension links, DSH patch, dash ACP adapters, each with a backup.
  - `services`: systemd user units or launchd agents with loopback or current-tailnet binds; the z0int shim and `~/.z0int/config/hermes.json`.
  - `models`: CPU torch wheel; dash STT model ≤ 1 GB when disk allows.
- **C2, never automatic:**
  - sudo and system packages
  - `tailscale up`
  - `loginctl enable-linger`
  - dotfiles link or apply (flow)
  - approval-policy bypass
  - grok and cursor in any role
  - private repo clones (aodl-views, z0bridge)
  - any bind outside the closed set
  - redeploying an adopted running service at a different SHA
  - HF sync > 1 GB and `system_one_4b`
  - shadow components
  - **every Hermes config edit** (the profile choice is the user's intent, which no verifier can confirm)
  - State Packet, memory injection, obspack
  - maintainer scripts (promote.sh, import_local SHAs, verify_channels, create-labels, `gitnexus analyze`, `/setup-pstack`)
  - z0evals CLAUDE.md, kit skill links and visual probes
  - the native Android build
  - remote LLM providers that spend the user's paid quota, unless listed and confirmed (§7)

| Aspect | `--auto` | `--guided` |
|---|---|---|
| Choice questions | none | one per choice point, default preselected |
| Profile | hardware default (§5.2) unless `--profile` | asked |
| Targets | profile + dash + z0evals (gated) | asked per supplemental |
| Pin policy | pinned | asked (pinned/tip), recorded in `workspace.yaml` |
| C0 | applied | applied |
| C1 | **One confirmation** on a TTY: "Apply N steps; M write outside ~/.z0: [list by bundle]. [y/N]". `--yes` grants all bundles; `--accept toolchains,harness` grants a subset. No TTY and no `--yes`: C1 becomes asks, C0 still applies, exit 3 | asked per step |
| C2 | asks in report.md; `./z0 onboard accept <id>` | asked per step; sudo commands are shown, then run with the user's sudo |
| Unknowns | LLM resolver (§7) inside the candidate set, else the safe default | asked; an LLM suggestion is the preselected default |
| Missing system tool | `unavailable(missing ffmpeg: sudo pacman -S ffmpeg)` plus an ask; dependents skipped | offered |
| Step failure | `failure_triage` remediation (≤ 1 retry), else block that component's dependents; others continue; exit 1 | retry / skip / abort |
| Adopted running service | kept; a SHA change becomes an ask | asked |

**Replay.** `./z0 onboard --auto --answers runs/<id>/answers.yaml` reproduces the same plan hash with no LLM calls. This holds for answers from a guided run or for frozen LLM answers.

---

## 4. DETECT (`lib/z0/onboard/detect/`, stdlib only, read-only)

| Module | Signals | Output |
|---|---|---|
| `osinfo.py` | `uname -sm`, `/etc/os-release`, `ldd --version`, pkg-manager probe, PEP 668 marker at `sysconfig.get_path("stdlib")/EXTERNALLY-MANAGED`, `/etc/machine-id` or `ioreg -rd1 -c IOPlatformExpertDevice` | os, arch, libc, distro, pkg_manager, pep668, `host_id` = sha256(machine-id ‖ hostname)[:16] |
| `hardware.py` | `nproc`/`hw.ncpu`, `lscpu -p=core`/`hw.physicalcpu`, `/proc/meminfo`/`hw.memsize`, `df -Pk` on `$Z0_HOME`, `$HOME`, `HF_HOME` and candidate volumes; `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader`, `/proc/driver/nvidia/version`, `rocm-smi`, `/sys/class/drm/*/device/vendor`, `vulkaninfo --summary`, Darwin arm64 | cpu{logical, physical}, ram_gib, disks[], gpu{class, vram_gib, driver, cuda_max} |
| `session.py` | `XDG_SESSION_TYPE`, `WAYLAND_DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`, `DISPLAY`, `pactl list short sources`/`arecord -l`, `systemctl --user is-system-running`, `loginctl show-user $USER -p Linger`, launchd | desktop, audio_in, systemd_user, linger, launchd |
| `toolchains.py` | absolute paths from toolchains.yaml, then `sh -c 'command -v X'` under the **prepared PATH**, plus `--version` for registry tools only | per tool: path, version, sh_resolves, source |
| `network.py` | HTTPS HEAD with a 3 s timeout to github.com, pypi.org, registry.npmjs.org, fonts.googleapis.com, download.pytorch.org, bun.sh, github.com/k2-fsa | reachability map |
| `tailscale.py` | `tailscale ip -4` (must be in 100.64/10); `tailscale status --json` (reads only Self.TailscaleIPs, DNSName, BackendState) | installed, logged_in, ipv4, magicdns |
| `harnesses.py` | `harnesses.yaml detect:`; `version_cmd` runs only when `policy.exec_probe: allowed` | installed / config_only / absent, version, config_dir(s), sessions_present (existence only), overrides (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `PI_CODING_AGENT_DIR`, `HERMES_HOME`) |
| `unknown_bins.py` | for files in `~/.local/bin` and `~/.bun/bin` that are not in the registry: **name, symlink target and shebang line only, never executed** | `unknowns[]` of kind `harness_classify` |
| `checkouts.py` | `.git` at depth ≤ 3 under `~/workspace`, `$HOME`, `$Z0_HOME/repos`, `~/zer0/oss`; normalized `origin`; `status --porcelain` count; branch; `merge-base --is-ancestor`; `cat-file -e <pin>` | adoption map + drift (name map: flow→`.files`, memento→`Memento`) |
| `services.py` | `systemctl --user list-units --all 'dash-*' 'z0*'`, `systemctl --user show -p ExecStart,WorkingDirectory,EnvironmentFiles`, `launchctl list`, `ss -ltnp`/`lsof -iTCP -sTCP:LISTEN` on 3000, 4747, 4788, 4789, 8212, 18212, 8917, 8921, 9333, 11500, 11501, 11503, 11510, 11520 | units, port owners, `exec_root_in_checkout` |
| `secrets.py` | env var **names**; `test -e` + `stat` mode for `~/.dash/{token,bootstrap-token}` and the `~/.dash` dir | present/absent, mode_ok |
| `workspace.py` | `$Z0_HOME/workspace.yaml` incl. `host_id`; stamp files `~/.local/share/{dash,z0}/**/deployed.json` | prior state, host match |

**Never opened** (`stat` only, or not at all): `~/.z0int/shadow/**`, `~/.hermes/**` contents, `~/.ssh`, `~/.claude*/.credentials*`, `~/.codex/auth*`, agentsview `config.toml`, any `*.env` that z0 did not write. The z0evals component additionally forbids any reference to `~/.z0int` and `~/.hermes`.

**Rules:**
- Detectors never raise. A missing tool is `absent`, and an ambiguous signal becomes an `unknown`.
- `$HOME` is written as `~` before any file is written.
- **Prepared PATH** = resolved toolchain bin dirs, then `$Z0_HOME/toolchains/*/bin`, then the component venv bin, then `/usr/bin:/bin`. The same PATH goes into every `run`, unit/env file and check (law T1). Bin dirs of `configure: never` harnesses are excluded.

---

## 5. Hardware decisions (pure, in `kernel.py`)

### 5.1 Classes and tiers
- `hw_class ∈ {nvidia, amd, apple, intel_mac, cpu}`
- `ram_tier ∈ {<4, 4–8, 8–16, >16}`
- `disk_tier ∈ {<3, 3–10, 10–40, >40}` (measured at the volume of `$Z0_HOME` and at the release root)

### 5.2 Decision table
| Decision | Rule |
|---|---|
| Auto default profile | `personal` if ram ≥ 8 ∧ disk ≥ 10 ∧ hw ≠ intel_mac ∧ a python in [3.10, 3.14) can be made; else `core` if disk ≥ 3; else refuse with the reason. RAM 8–16 adds a warning for research/full. |
| z0intelligence | `unavailable(ram<8)` if RAM < 8; `refused(intel_mac: no torch 2.10 wheel)`; `unavailable(python_window)` if no 3.10–3.13 can be made |
| torch index (`torch==2.10.0`) | cpu or disk < 10 → `https://download.pytorch.org/whl/cpu` (`+cpu`); nvidia ∧ cuda_max ≥ 12.8 → PyPI (cu128), otherwise cpu + warning; amd ∧ ROCm present → ROCm index, else cpu; apple → PyPI |
| z0int device env | apple → `Z0INT_{LAYA,NANOJEV,JULIA,IMAGE}_DEVICE=mps` in `service.env`, report "MPS not auto-used"; amd+ROCm → explicit device vars |
| z0int model policy | `cpu_only`, unless NVIDIA VRAM ≥ 8 (`twelve_gb`) or ≥ 20 (`high_vram`); disk < 10 forces `cpu_only`; disk 10–40 caps at `twelve_gb`; apple ≥ 32 GB unified → `twelve_gb` **guided only**; `models.sync` and `system_one_4b` are C2 |
| z0int llama tier | only when llama-server **and** a GGUF are found ∧ ram ≥ 16; `--llama-server`/`--gguf-dir` always passed explicitly |
| dash | `DASH_STT_THREADS=min(4, physical)`; RAM < 4: bridge only; 4–8: + STT + metro (metro needs `--with dash-metro`); ≥ 8: native build allowed (C2); release root = the volume with the most free space; warn below 5 GB |
| oh-my-pi | disk ≥ 5; rustup (C1 toolchains) only when the pinned tree has `rust-toolchain.toml` |
| desktop/flow | only on linux ∧ desktop ≠ none; always C2 |
| z0evals | no hardware branch; web tier needs `network.fonts_google` ∧ node ≥ 20.9 (node 22 user-local if C1 toolchains is granted, else an ask) |
| `compute`/`research` | offered on every class; warning when RAM < 16 |

---

## 6. PLAN, APPLY, VERIFY, ROLLBACK

### 6.1 Plan (pure)
- **Input:** `host.json`, a registry snapshot (sha256 of each source file), `answers.yaml`, mode and grants.
- **Order:** a topological sort over `depends_on ∪ needs ∪` implicit edges. Implicit edges: tokenomics → z0intelligence → oh-my-pi verify; shim → every z0int plugin; tailnet → dash bridge unit; sync → loop tick. This fixes the `resolve_profile` order bug without touching `registry.py`.
- **State per step:** `todo | already_satisfied | ask(C2 or ungranted C1) | unavailable(reason) | refused(law) | blocked(dep)`.
- **Hash:** `plan_hash` = sha256 of canonical JSON.
- **Diff:** `plan.diff.txt` is compared with `current/receipt.json`.
- **Idempotence:** a second plan on an unchanged host has an empty `todo` set (law I1).

### 6.2 Mirror cache
`plan` may `git fetch` the pinned SHAs into `$Z0_HOME/cache/git/<repo>.git`. This is a bare mirror and a z0-private write. It serves three purposes:
- the R0 check (does the SHA exist on origin?)
- reading `zer0.repo.yaml setup:` and `rust-toolchain.toml`/`bun.lock`/`pyproject` at the pin
- build trees

Adopted checkouts are never written to, and no `git worktree add` touches their `.git`.

### 6.3 Apply
1. Take the lock, then check the plan hash.
2. **Freshness check.** Re-detect the volatile facts: ports, tailnet IP, toolchain versions, unit states, checkout HEADs, disk. If anything changed, re-plan:
   - Steps that changed only within the granted classes: continue, and print the diff.
   - Otherwise: stop and ask for confirmation again (`--yes` cannot widen a grant).

   There is no wall-clock expiry.
3. For each step: re-run the probe (skip if satisfied) → snapshot for the undo (prior symlink target, file hash, backup into `runs/<id>/backups/` at 0600) → execute with the prepared env (`shell=False`, `PIP_NO_INPUT=1`, `PIP_BREAK_SYSTEM_PACKAGES` unset, `LANG=C.UTF-8`, allowlisted env) → journal `{step, effects:[{path, sha256|target}], ts}` → step `verify`.
4. **On failure:** `failure_triage` may choose one listed remediation for a single retry. Otherwise the dependents become `blocked` and independent components continue. A failed install is always reported as a failure. (z0 init today prints only `warning: setup command failed` and continues.)
5. **Ownership:** every created dir carries `.z0-owned` (run id), and every file has a journal hash.
6. **`workspace.yaml`:** write `host_id` plus `components.<id>.{path, branch, ref}` (the adopted dev path, or the z0 clone), so `z0 doctor` and `z0 status` see the same state. `onboard.<id>.release` points to the live release. The keys are additive; a Phase 1 test checks that `registry.py` ignores them.

### 6.4 Verify
- Runs every selected component's `acceptance` tiers, service health, harness checks and the secret canary scan.
- Writes `receipt.json` and `report.md`.
- `z0 doctor`'s exit code is never a gate.

### 6.5 Rollback
- Replays the journal in reverse:
  1. restore symlinks (services return to the previous release)
  2. stop and remove new units
  3. restore harness config backups (only if the file hash still equals what the run wrote)
  4. delete owned artifacts whose hash is unchanged

  Changed files are kept and reported (law R1).
- It never deletes: adopted checkouts, a pre-existing `~/.dash`, the release that `current` points to, or the `cache/` mirrors (unless `--purge`).
- Rollback is itself journaled, so it is safe to run twice.

---

## 7. LLM use in `--auto`

**Role.** The LLM classifies typed unknowns. It has no tools, writes no files, runs no commands and never makes a plan.

**Closed question kinds.** Each has `{id, kind, facts(redacted), candidates, safe_default, verifier}`:
| kind | Candidates | Verifier | Safe default |
|---|---|---|---|
| `harness_classify` | registry harness ids ∪ {unsupported} | name/symlink/shebang facts only; the chosen id must have no `exec_probe: never` | unsupported |
| `config_dir_pick` | the listed dirs | the dir has `projects/` | all dirs, via `Z0INT_CLAUDE_PROJECTS_DIRS` |
| `fork_match` | yes/no | the pinned SHA exists in that repo | no (clone a separate copy) |
| `port_owner` | adopt/conflict | `/proc/<pid>/cmdline` resolves under the component's release root | conflict (`unavailable`) |
| `gpu_vendor_resolve` | hw classes | driver probe | cpu |
| `pkg_hint` | package names from the toolchains.yaml families | — (print-only) | generic hint |
| `failure_triage` | that step's `remediations:` | the remediation's own `when:` holds | `mark_unavailable` |
| `first_task_pick` | at most 5 already-filtered task ids within the alignment tie epsilon | exact `{pick, reason_codes}`; closed codes must agree with the selected task and redacted profile aggregates; T3 fields refuse before send | deterministic top with no reason codes |

`first_task_pick` uses at most one call (no probes), inside the shared eight-call
budget. Its reasons are `tier:P0..P3`, `skill_match:<tag>`, `interest:<tag>`,
`first_task_size:S|M|L` or `size:S|M|L`; skill/interest tags must match both the
profile and the selected task, and size/tier must match the selected task.
It uses the same privacy, freeze and zero-call replay path as the other kinds.

There is no Hermes profile pick; Hermes is always an ask.

**Providers.** They come from `registry/onboarding.yaml`. The first one that is available, consented and smoke-tested wins:
1. **local**: llama-server/ollama on 127.0.0.1 (detected).
2. **claude CLI**: `claude -p --output-format json --model <onboarding.llm.claude_model, default "haiku"> --strict-mcp-config --mcp-config <empty> --tools ""`, 1 turn.
3. **codex**: `codex exec --sandbox read-only --skip-git-repo-check -m <onboarding.llm.codex_model, default "gpt-6.1-sol">`, with a JSON output schema.
4. **free gateway**: OpenRouter-free or Vercel AI Gateway-free, only when the key *name* is present. The value is read in-process into a header and never logged.

**Spend and consent.**
- `--llm=local` is the default when no TTY confirmation happens.
- Providers 2–4 use the user's account. They appear in the C1 confirmation list as "LLM: up to 8 calls via claude (your quota)", or are granted by `--yes`.
- `--llm=none` turns the LLM off.
- grok and cursor are refused by the kernel (law P1), not by the prompt.

**Guardrails.**
1. The model may answer `{"need_probe": "<id>"}` from the read-only probe catalog. The catalog gives existence and mode only for denylisted paths. At most 2 rounds.
2. An answer must pass the JSON schema, then candidate membership, then the verifier. If any check fails, the result is `safe_default` and the reason goes into the receipt.
3. An answer cannot raise a consent class, turn ask/refuse into apply, choose a forbidden provider or harness, or add a path (law L-LLM).
4. Budget: ≤ 8 calls, 30 s each, ≤ 3 min total. Over budget, safe defaults are used.
5. **Redaction fails closed.** `~` replaces `$HOME`, the username is replaced and hostnames are hashed. No env values and no user file contents are sent. Every secret byte the process touched is registered, and a canary check aborts the send if a canary is found.
6. Every answer is frozen into `answers.yaml` with source, provider, model, prompt sha256 and answer, and listed in report.md. A replay with the same input gives the same plan hash with no calls.

`--llm=none` must produce a working onboarding in the container matrix; that is what proves the LLM only fills gaps.

---

## 8. Component plans

### 8.1 z0 hub
1. Stage 0 venv (§1.3).
2. `check scripts/registry-check`.
3. `check` the plan is deterministic (`plan --stdout` twice gives equal hashes).
4. `check ./z0 init --profile P --dry-run` lists the expected set (the profile only; supplementals are excluded).
5. `memento` is never planned (law M1).
6. Order: tokenomics → z0intelligence → oh-my-pi → others → dash, z0evals.
7. Each Python component has its own venv `$Z0_HOME/venvs/<id>` (tokenomics 65e8f2dd vs z0int extra 2ae9051 skew).

### 8.2 z0evals (the first end-to-end target; all C0 unless marked)
1. `adopt_or_clone`. Reuse an adopted clone **in place only if it is clean** (prefer the clean one among `~/workspace/z0evals*`). Otherwise use a z0-owned clone. Run `git fetch origin main dev nightly preview`.
2. **Tier 0** with any stdlib python ≥ 3.10:
   - `rollout.py show`: record the worker base; flag B7.
   - `pages-url-map.py check --root . --base /z0evals`.
   - `tests/test_arm_identity.py`.
   - `tests/expire_claims.py`.
   - Optional: `.github/scripts/check-receipt.py`.
3. `.venv` with Python 3.12 via uv (with C1 toolchains granted, else any 3.10+ with a CI-drift warning). Then `pip_install -r requirements.txt`.
4. **Tier 1**, in CI order: `ci.yml:19-36`, 11 steps; `discover` is optional.
5. **Tier 2**, when fonts are reachable and node ≥ 20.9:
   1. generators first (`build_site_data.py`, `build_posts.py` as `needs`)
   2. `npm ci --no-audit --no-fund` (npm only; optional deps kept)
   3. `npm run typecheck`
   4. `Z0_BASE_PATH=/z0evals npx next build`, then `test -f web/out/index.html`
   5. `audit_web_export.py --root web/out`

   If the tier cannot run: `unavailable(offline|node)`.
6. Warn about B3 before the build if the openjev corpus exists (detect only).
7. **Post-check:** the `git status --porcelain` allowlist is `?? web/data/optchat-long-horizon-v0.json`, plus the two openjev drift files when the corpus exists. Anything else is reported.
8. **Asks:** CLAUDE.md pointer, kit skill links, pytest, visual probes, maintainer import (fills `root:` only, never SHAs).
9. **Never:** promote.sh, verify_channels, create-labels, any unit, `~/.z0int` or `~/.hermes`.

### 8.3 dash (bridge + phone)
- **Gates first** (laws D1 and D2):
  - `app_rev` and `bridge_rev` must be present in the origin mirror. If not: `unavailable(rev_not_on_origin: maintainer must push integrate/dash-v2)`. The rest continues.
  - Flavour from `git ls-tree <sha> bridge/src/acp app/modules`. **Legacy is refused** (it has the `0.0.0.0` bind and Expo Go). It is never deployed.
- **Steps:**
  1. `ensure_toolchain bun>=1.4.3`, user-local in `$Z0_HOME/toolchains/bun/1.4.3`. It does not replace `~/.bun`. New units use that absolute path. Also python3 ≥ 3.10 and git. ffmpeg is C2 if missing, so the static tests and voice become `unavailable`.
  2. `build_tree` for both SHAs. Run the static gates there: `bun run typecheck`, `lint`, `test` with `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`, plus the bridge security tests (spec §8.2–3).
  3. `stage_release` for both SHAs to `<largest volume>/…/dash/releases/<sha>` (`DASH_RELEASE_ROOT` overrides), each with its own `node_modules`:
     1. root `bun install --frozen-lockfile`
     2. the app: a full install if `git ls-remote https://github.com/kvnloo/aodl-views.git` succeeds (probe only), else `bun scripts/install-public-ci.ts`, reported as "null renderer"
     3. `--cwd bridge`
     4. `--cwd bridge/acp-adapters` when claude or codex is installed (fixes B8)
  4. Write `~/.config/dash-services/bridge.env` (0600):
     - `DASH_HOST=<ts-ip>`, `DASH_PORT=4747`, `DASH_CWD`
     - `PATH` = bun dir + **allowed** harness bin dirs + `/usr/bin:/bin` (grok excluded)
     - non-default `HERMES_HOME`/`CLAUDE_CONFIG_DIR`/`CODEX_HOME` only when set
     - STT vars only when voice was granted

     Gate, supervision, z0live, tiny, factory and orchestra vars stay unset. The approval policy stays unset (bypass is C2).
  5. `write_file ~/.local/lib/dash/bin/dash-wait-tailnet` (from `templates/dash/dash-wait-tailnet.py`).
  6. `service_unit dash-bridge`: `%h` paths, the absolute bun path, `ExecStartPre=dash-wait-tailnet`, After `network-online`, `Restart=on-failure`, `RestartSec=10`, `StartLimitIntervalSec=0`, `TimeoutStartSec=120`, `MemoryMax=1G`, WorkingDirectory `bridge-current/bridge`. On macOS, a launchd plist plus a wrapper that runs the same pre-check.
  7. `swap_current`, then start. If a unit exists at the same SHA: adopt it. At a different SHA: ask. Adopted units are diffed and kept.
- **Optional** (`--with dash-metro`, C1): metro `[::1]:18212` + relay `<ts-ip>:8212`.
- **Optional STT** (C1 models, RAM ≥ 4): download into a new empty dir, check the 4 files are non-empty, set `DASH_STT_MODEL`.
- **APK build:** C2.
- **Never install:** the the desktop host-only units, drop-ins or `fleet-build`.
- **No tailnet:**
  - Run the loopback self-test (`DASH_ALLOW_LOOPBACK=1 DASH_HOST=127.0.0.1`, disposable `DASH_CREDENTIAL_DIR` under the run dir).
  - Install no unit.
  - Add the ask `tailscale up` → `./z0 onboard accept dash.bridge.unit`.
- **Tokens:** the bridge creates them. Verify checks that both files exist with mode 0600 and that the dir is 0700. An existing `~/.dash` is kept.
- **Health** (`lib/z0/onboard/checks/dash.py`, the new doctor; the upstream fix is filed):
  - unauthenticated `GET http://<ts-ip>:4747/` with `Host: <ts-ip>:4747` returns **401**
  - an authorized GET (token read into memory, registered with the redactor, sent in a header) returns `ok:true` and the harness list
  - `bun bridge/acp-runtime.ts <run>/acp-receipt.json` returns per-harness ready or a reason
- **Pairing** (`./z0 onboard pair dash`):
  1. Precondition: the bridge is healthy. If the phone is not on the tailnet, print the join step (QR #0 links to the Tailscale app).
  2. Read the bootstrap token into memory and call `GET /pair` with Bearer and the Host header.
  3. Print **only** the 6-char code (3-min TTL), `http://<ts-ip>:4747`, and a terminal QR (vendored stdlib encoder, or `qrencode` if present). The QR holds `dash://pair?h=<ts-ip>&p=4747&c=<code>` once WP-D4 lands; until then it holds the URL plus the code for manual entry.
  4. Poll within 12 requests per minute.
  5. `--sonic` uses paplay → aplay → ffplay on Linux, ffplay only on macOS.

  The token is never displayed or put in a QR.
- **Phone app tiers:**
  - (a) `bun run debug:web`
  - (b) the dev-client APK from the dash Release asset (WP-D3); QR #1 is the APK URL
  - iOS is reported as unsupported

  The report tells the user to set the app cwd to `DASH_CWD`.

### 8.4 z0intelligence (runtime + plugins per harness)
- **Live layout (law S1).**
  - The runtime venv is `~/.local/lib/z0int-runtime/<sha>`. It is built by uv **directly at that path**, so nothing is relocated and the `stage-z0int-runtime.py` relink bug does not apply. It is a non-editable install from `stage_release` `~/.local/lib/z0int-shadow/<sha>`.
  - The shim and plugins point there.
  - A dev `<repo>/.venv` (`uv pip install -e '.[test]'`) is an opt-in for contributors (guided) and is never referenced by live config.
- **z0 steps:**
  1. `adopt_or_clone` + `build_tree` + `stage_release` at the pin. The pin must contain `.claude-plugin/marketplace.json` for the Claude plugin; see D-6.
  2. `ensure_toolchain python` in [3.10, 3.14), preferring `uv python install 3.11`. Refuse on intel_mac.
  3. `venv`, then `pip_install torch==2.10.0[+cpu]` with the index from §5.2, **before** `.[test]`. aodl and tokenomics git+ deps require github reachability, else `unavailable(network)`.
  4. `write_file ~/.z0int/bin/python`, mode 0755, an exec wrapper and not a symlink: `#!/bin/sh` / `exec <runtime>/bin/python "$@"`. Also `~/.z0int/config/hermes.json`. Both are C1 services.
  5. `check`:
     - `~/.z0int/bin/python -c 'import z0int, mcp, aodl_contract, fff, typesafe_sdk'`
     - the FTS5 probe
     - `torch.cuda.is_available()` matches the class
     - `python -m z0int doctor --json`
     - `models plan --json` matches the tier
     - `status --json`
     - `Z0INT_HOME=$(mktemp -d) HF_HUB_OFFLINE=1 pytest -q tests/test_z0int_onboard.py`
     - `Z0INT_HOME=$(mktemp -d) z0int onboard --dry-run --skip-evolution-lab --json` (temp home only)
  6. **`delegate` contract.**
     - `contract: z0int-onboard-v1` is detected from `zer0.repo.yaml setup.contract` at the pin. When present, z0 runs `z0int onboard --auto|--guided --host-profile <host.json> --grants <bundles> --plan-json`. The emitted steps are merged into the z0 plan as typed steps. Apply runs them through the same delegate.
     - **Interim, until WP-I1 lands:** the delegate is **not** run. Its existing `--dry-run` writes state and its OMP step links all 13 dirs. z0 performs steps 1–5 plus the harness steps below. `z0int onboard` itself becomes an ask, with a note.
     - Effects under `~/.z0int` are snapshotted before apply (`config/`, `state/onboard.json` only; **never** `shadow/`) for undo.
- **Harness plugins** (after the shim probe passes; each step takes a backup):

| Harness | Auto (C1 harness) | Verify | Undo |
|---|---|---|---|
| Claude Code | `claude plugin marketplace add <release path>` + `claude plugin install z0intelligence@z0intelligence`; `Z0INT_CLAUDE_PROJECTS_DIRS` when there are several dirs; adopt if already live | `claude mcp list` shows it; `route_worker` lists tools | `claude plugin uninstall` + marketplace remove |
| Codex | `codex plugin marketplace add` + `codex plugin add codex-z0intelligence@z0intelligence`; skipped if `z0intelligence@personal` exists; hook trust is an ask | plugin listed | `codex plugin remove` |
| OMP | `scripts/omp_bridge_install.py` with the curated 6 (z0int-bridge, z0-usage, z0-memory, z0-state-packet, z0-obspack, local-cognition); honours `PI_CODING_AGENT_DIR`; sets `Z0INT_OMP_ROOT`; report says "restart OMP" | links resolve | the script's backup/restore |
| DSH | cordis patch only if the profile dir exists ∧ node ≥ 22; else memory-doctor `deepseek-harness` is N/A | `node --test tests/test-dsh-plugin.mjs` | revert the patch |
| Hermes | **always an ask** (profile choice + `config.yaml` edit) | — | — |
| grok, cursor | never (P1) | reported "present, policy-excluded" | — |
| opencode, gemini, kimi, others | "detected, unsupported" | — | — |

  obspack, State Packet (plugin env **or** script, never both) and memory injection are C2.
- **Services** (C1, loopback only; ports probed first; existing units adopted):
  1. router `z0intelligence.service` on 127.0.0.1:11501, gated on `/healthz` then `/readyz`; the boot-check line is reported
  2. cognition/SLM only per §5.2
  3. agentsview-sync only if `agentsview` exists
  4. loop tick **last**, only after sync succeeded and `loop.json` exists; `z0int loop tick` must exit 0 once by hand
- **Unit templates** (the desktop host literals replaced by detected paths):
  - lock dir: `$Z0INT_HOME/locks`
  - the resolved `CLAUDE_CONFIG_DIR`
  - `PYTHONPATH` = release `src/`
  - `Z0INT_BIND_2` only when the kind network exists
  - `After=docker.service` dropped when docker is absent
- **macOS:** LaunchAgents with a Python fcntl lock in place of flock. Release mode is Linux+systemd only. On macOS, services are guided-only.

### 8.5 Other components
tokenomics, oh-my-pi, kerdoios and agenttrace use the generic path: adopt_or_clone, a venv each, argv install from the `onboard` block, and the registry verify. oh-my-pi runs `./omp setup` only when omp is a detected harness (C1 harness). Shadow components are C2.

---

## 9. Secrets
- Names only appear in host.json, the plan and receipts. Values live only in process memory (HTTP headers, provider keys) and are registered with the redactor.
- `redact.py` runs on every captured stdout/stderr before it reaches the journal, the terminal or an LLM. It masks known values plus these patterns: `sk-`, `ghp_`, `xox`, `Bearer …`, and runs of ≥ 20 high-entropy hex/base64 characters next to `token|key|secret`.
- Env files are written with umask 077, and the mode is checked after the write. Units reference env files and never inline secrets.
- Never written to: the z0 repo, `workspace.yaml`, receipts or prompts.
- Never automatic: `gh auth login`, `tailscale up`, `huggingface-cli login`, harness logins.
- Guided secret prompts use `getpass` and write only to the owning store.

---

## 10. Tests (stdlib `unittest`; no new test dependency)

**Layer 1: pure kernel (every PR, < 30 s).**
- `tests/onboard/test_kernel_twin.py` enumerates every `decide_*` domain (§11) and compares the result with the Bend table export.
- `test_plan_golden.py` runs host fixtures × {auto, guided} × profiles and compares with `expected/*.plan.json` byte for byte plus the hash. A golden changes only with `--update-golden`.
- Host fixtures: `desktop-cpu-15g`, `laptop-vulkan`, `cpu-6g`, `cpu-3g-disk`, `nvidia-24g`, `nvidia-10g-old-driver`, `arch-amd-rocm`, `apple-m-32g`, `intel-mac`, `musl-arm64`, `no-tailnet`, `offline`, `no-python`, `kvn-like-adopt` (dirty/off-pin checkouts, live dash at another SHA), `host-mismatch`.
- Property loops over generated fixtures (seeded `random`): determinism, topological validity, no C2 executed in auto, every `run` has `creates|probe`, no ungranted C1 executed.
- One **red fixture per law**: a plan or artifact that violates the law must fail.

**Layer 2: engine with fakes (every PR).**
- `tests/onboard/fakebin/` holds stubs for `claude codex omp hermes grok bun tailscale systemctl nvidia-smi` that log their argv.
- Apply on a temp `$HOME`, then check:
  - the second plan is empty (I1)
  - rollback restores a byte-equal tree outside `runs/` and `cache/` (R2)
  - grok was never called (P1)
  - the canary never appears (X1)
  - a freshness-drift re-plan triggers
  - the lock blocks a second run
- Fake LLM provider cases:
  - (a) a valid candidate is accepted and frozen
  - (b) an out-of-set value gives the safe default
  - (c) a forbidden provider is refused
  - (d) a timeout gives the safe default
  - (e) an answer that tries to escalate consent changes nothing
  - (f) a replay makes zero calls
  - (g) a canary in a prompt aborts the send

**Layer 3: clean machines** (nightly `.github/workflows/onboard-e2e.yml`; local `scripts/onboard-e2e --image X`).
- Images, pinned by digest, each with a non-root user: `archlinux` (PEP 668), `debian:12`, `ubuntu:24.04`, `fedora:41`, `alpine` (musl; expected refusals), and **a no-python variant** (bash, git, curl, tar only). There is a podman `--systemd=always` variant, plus a fake `tailscale` with a dummy interface carrying <tailnet-ip>, so the bridge unit reaches the **401** check.
- Scenarios:
  1. `--auto --yes --llm=none --profile core` with dash and z0evals: verify green; z0evals tiers 0–2 green; dash bridge 401/ok via the fake tailnet; the report lists the expected asks.
  2. The same without the fake tailscale: dash loopback self-test, no unit.
  3. Idempotent re-run: empty todo.
  4. `rollback`: clean snapshot diff (file tree + unit list + listening ports).
  5. `--auto` with no TTY and no `--yes`: exit 3, only C0 applied.
  6. Offline (`--network none` after the image build): z0evals Python tier only; z0int `unavailable(network)`.
  7. Nightly heavy: `personal` on CPU x86_64; torch `+cpu`; `cuda.is_available()==False`; venv < 2.5 GB; router `/healthz`.
- macOS `macos-14`: detect, plan golden, z0evals tiers 0–2, and a `plutil -lint` of the rendered plists.
- **Opt-in real tailnet job** (ephemeral authkey secret): real bridge unit, 401/`ok:true`, `pair --print-only` (code issued, no token in output).
- **Owner smoke** (manual): `./z0 onboard --auto --plan-only` on the desktop host and on the laptop must show only `already_satisfied`/`adopt`/`ask` for the live dash and z0int units, and zero C1 writes to running services. This is the "do not disturb a configured host" proof.

---

## 11. Durability: Bend laws, Python twin, red/green tests

- `bend/onboard/{MODEL,LAWS,PROOF}.bend` + `toolchain.json`, in the same layout as host_layout.
- The kernel is split into **small finite functions**, each fully enumerable:
  - `decide_host(match)`
  - `decide_consent(mode, class, granted, source)`
  - `decide_bind(bind_class, ip_from_detect)`
  - `decide_exec_root(root_kind)`
  - `decide_provider(id)`
  - `decide_component(gate, rev_on_origin, flavour, maturity, hw_class, py_window, ram_tier)`
- The largest domain is ≈ 3·2·2·3·5·3·4 = 2,160 rows.
- `lib/z0/onboard/kernel.py` is the **only** code that decides refuse/ask/allow.
- CI job `laws`: `bend check bend/onboard/PROOF.bend`, then the twin tests. A change to `kernel.py` without a matching MODEL change fails twin parity.

| Law | Statement | Proof status |
|---|---|---|
| H1 host_match | A host.json, answers or receipt whose `host_id` ≠ the current host → refuse (exit 4; `--rehost` re-detects). No fallback to another host's config | Bend + twin |
| H2 no_host_literals | Rendered artifacts contain no denylisted literal; every absolute path comes from facts or declared roots; tailnet IPs only from the current detection | artifact scan test |
| S1 never_through_checkout | Unit ExecStart/WorkingDirectory/EnvironmentFile, the shim target and plugin paths → only releases, owned venvs or toolchains; anything with a `.git` ancestor → refuse | Bend (root kind) + scan |
| S2 closed_bind | bind ∈ {loopback, current tailnet ipv4}; anything else cannot be expressed | Bend + schema |
| S3 adopt_before_create | an existing unit with the same name → adopt or ask, never a duplicate | twin + fake test |
| C1 auto_never_c2 | auto ∧ C2 → ask | Bend |
| C2 grant_bound | a C1 step runs only if its bundle is granted; a freshness re-plan cannot widen grants | Bend |
| L-LLM no_escalation | an LLM-sourced answer never changes a consent class or turns ask/refuse into apply | Bend + adversarial test |
| P1 forbidden_provider | grok and cursor are refused in offload, dash PATH, z0int routing, harness config and probes | Bend + fakebin |
| P0 dry_run_purity | plan/detect write only the §1.3 set; with `--stdout` and PyYAML present, zero bytes | snapshot test |
| D1/D2 dash gates | rev not on origin → unavailable; legacy flavour → refuse | Bend |
| Z1/Z2 z0int | python ∉ [3.10, 3.14) or intel_mac → refuse; cpu class → cpu index | Bend |
| M1/M2 | memento never planned; shadow → C2 | Bend |
| T1 prepared_path | every needed tool resolves under `sh -c` with the prepared PATH | detect test |
| O1 order | the plan is a topological order of the declared and implicit edges | property test |
| I1 idempotent | `plan(apply(plan(h)))` has no todo | fake + container |
| R1 own_before_delete | rollback deletes only owned artifacts with an unchanged hash | fake test |
| X1 no_secret_output | the canary appears nowhere ($Z0_HOME, run dir, logs, LLM transcripts) | container test |

Laws I1, R1, X1, H2 and T1 rest on tests, not on Bend proofs. The report and the docs say so.

---

## 12. File tree (kvnloo/z0, new or changed)
```
z0                                   # onboard branch -> stage0
requirements.lock                    # PyYAML with hashes
registry/{components,harnesses,profiles}.yaml   # edited
registry/{toolchains,onboarding}.yaml           # new
schemas/{component,repo}.schema.json            # +onboard, +setup
schemas/{host-profile,onboard-step,onboard-plan,onboard-receipt,onboarding}.schema.json
scripts/{registry-check,docs-generate}          # new rules, R-sync projection
scripts/{onboard-e2e,toolchains-bump,public-ready-check}
bend/onboard/{MODEL,LAWS,PROOF}.bend, toolchain.json
lib/z0/__main__.py                   # onboard subparser
lib/z0/onboard/
  stage0.sh  cli.py  kernel.py  plan.py  apply.py  verify.py  rollback.py
  journal.py lock.py  redact.py  report.py  freshness.py  when.py  ui.py  pair.py
  detect/{osinfo,hardware,session,toolchains,network,tailscale,harnesses,unknown_bins,checkouts,services,secrets,workspace}.py
  actions/{ensure_toolchain,adopt_or_clone,build_tree,stage_release,swap_current,venv,pip_install,run,write_file,service_unit,harness_plugin,delegate,check}.py
  checks/{z0,z0evals,dash,z0int}.py
  harness/{claude,codex,omp,dsh}.py
  llm/{resolver,providers,questions,probes}.py
  vendor/qrcode_min.py
templates/dash/{dash-bridge.service,dash-metro.service,dash-metro-relay.service,com.z0.dash-bridge.plist,launchd-wrapper.sh,bridge.env,metro.env}.tmpl, dash-wait-tailnet.py, metro-relay.py
templates/z0int/{z0intelligence.service,agentsview-sync.service,agentsview-sync.timer,z0int-loop-tick.service,z0int-loop-tick.timer,*.plist,service.env,shim.sh}.tmpl
tests/__init__.py
tests/onboard/{fixtures/hosts,expected,fakebin,containers}/ + test_*.py
.github/workflows/{onboard.yml,onboard-e2e.yml}
docs/onboarding/DESIGN.md, docs/getting-started/onboard.md, generated/onboarding-matrix.md
```
`lib/z0/commands.py` is **not edited** before Phase Z6, so `z0 init` users keep today's behaviour. Phase Z6 first adds characterization tests, then the fixes: fatal errors, topological sort, doctor exit code.

---

## 13. Ordered work packages (independent per repo)

**kvnloo/z0 (critical path)**
- **Z0, contracts and laws.** Schemas, `bend/onboard/*`, `kernel.py`, `test_kernel_twin.py` (red, then green), `tests/__init__.py`, `onboard.yml`.
- **Z1, read-only onboarding.** Registry edits (dash, z0evals, `onboard:` blocks, harness detect/policy rows), `toolchains.yaml`, `onboarding.yaml`, `registry-check`/R-sync, stage 0, `detect/*`, `plan.py`, golden fixtures. Ships `./z0 onboard plan`.
- **Z2, apply/verify/rollback + hub + z0evals end to end.** `actions/*`, journal, lock, freshness, `checks/{z0,z0evals}`, fakebin tests, containers (scenarios 1-core, 3, 4, 5, 6).
- **Z3, z0intelligence (interim path).** Torch index, runtime venv, shim, checks, `harness/{claude,codex,omp,dsh}`, z0int templates; nightly scenario 7. It switches to `delegate` when WP-I1 lands.
- **Z4, dash.** Templates, `checks/dash.py`, `pair.py`, QR, fake-tailnet container. Ready ahead of WP-D1. Until D1 lands, the e2e test uses a fixture repo that contains the current flavour.
- **Z5, LLM resolver.** `llm/*`, guardrail tests a–g.
- **Z6, guided UX and docs.** `ui.py`, macOS launchd paths, `docs/getting-started/onboard.md`, README quick start (`git clone … && ./z0 onboard`), with the bare `pip install` text replaced. `public-ready-check`. Characterization tests, then the `cmd_init`/`cmd_doctor` fixes.

**kvnloo/z0evals (independent)**
- **E1:** gitignore `web/data/optchat-long-horizon-v0.json`; use `Path.home()` in `tests/test_arm_identity.py`; make the README venv-based; add `.python-version` (3.12) and `.nvmrc` (22); add a `zer0.repo.yaml setup:` block with the tier order; flag B7 and B8 for the owner to resolve.

**kvnloo/dash (stranger-blocking)**
- **D1:** push `integrate/dash-v2` (`5f3ee27`, `30e6035`, `cfc08de`) and tag a release; make it the documented line.
- **D2:** add `zer0.repo.yaml` with `setup:` and `contract`.
- **D3:** publish the dev-client APK as a Release asset (sha256 recorded in the registry).
- **D4:** a `dash://pair?h=&p=&c=` deep link plus a manual "host + code" screen.
- **D5:** remove the `<tailnet-name>`/`100.113…` literals (env + tailnet discovery) and add env overrides for the desktop host paths (orchestra, factory, gate).
- **D6:** fix the `control-dash.ts doctor` auth/Host/port handling.
- **D7:** correct the README/AGENTS/ONBOARDING Expo Go and token claims.
- **D8:** decide on aodl-views (public, or the null renderer stays).

**kvnloo/z0intelligence**
- **I1:** onboard contract v1: `--host-profile`, `--grants`, `--plan-json`, a side-effect-free `--dry-run`, and new STEPS (`hardware.detect`, `interpreter.shim`, `harness.detect`, `harness.install.<name>`, `services.env`, `services.units`, `verify`).
- **I2:** MPS/ROCm/AMD detection beyond NVIDIA; enforce `<3.14` in doctor.
- **I3:** the desktop host and `<owner-home>` literal overrides (spec §9.4 list).
- **I4:** curated OMP subset plus `PI_CODING_AGENT_DIR`/`CODEX_HOME`; memory doctor treats DSH as N/A.
- **I5:** `stage-z0int-runtime.py` relinks `python3.<minor>`.
- **I6:** a `.claude-plugin` ref inside the registry pin (with D-6).

**kvnloo/aodl**
- **A1:** add harness ids `claude`, `grok`, `cursor-agent`, `opencode`, `gemini`, `kimi`, `fx` to `harnesses/catalog.json`.

**Dependencies:** Z0 → Z1 → Z2 → {Z3, Z4, Z5} → Z6. Z3's delegate needs I1. Z4 needs D1 for a real (non-fixture) run, and D3/D4 for the phone path. E1 and A1 are independent.

---

## 14. Open decisions for the owner
1. **(D-1) The `--auto` consent model.** Is "one enumerated go/no-go confirmation, or `--yes`" an acceptable form of "ask" for C1 (toolchains, harness plugins, user units, quota-spending LLM)? This design assumes yes. The alternative: C1 is never applied in auto, so strangers without bun get no dash or OMP.
2. **(D-2) The default LLM.** Should it be `local` unless confirmed, as designed, or `auto` with remote redacted calls?
3. **(D-3) Default target set.** Is it profile + dash + z0evals, as designed, or should they be added to profile membership?
4. **(D-4) Push the dash revs (WP-D1).** Until this happens, strangers get dash `unavailable`.
5. **(D-5) Pairing.** Approve the `dash://pair` scheme (WP-D4). Until then, pairing uses manual code entry.
6. **(D-6) z0intelligence pin.** The pin `0563ed7` lacks `.claude-plugin/`. Bump it (preferred: one ref per host), or install the plugin from a second ref.
7. **(D-7) Bun on the desktop host.** the desktop host's adopted units use bun 1.3.14, while new releases use the user-local 1.4.3. Moving the live units is a C2 redeploy. Confirm that this is acceptable.
8. **(D-8) z0evals B7.** Settle the branching-docs conflict. The onboarder treats `rollout.py show` as the authority.

---

## Appendix A: judge flaws and their fixes
| Flaw | Fix |
|---|---|
| `--auto` silently grants C1 | C1 bundles need a TTY confirmation or `--yes`/`--accept`; otherwise asks, exit 3 (§3) |
| No python/uv makes the stranger stuck | Stage 0 needs only bash + curl/tar; pinned, checksummed uv → CPython; consented (§1.3) |
| Vendored YAML loader left unspecified | Decided: stage 0 makes the z0 venv with PyYAML under `$Z0_HOME` before plan; P0 states exactly what plan may write |
| Stage 0 contradicts dry-run purity | P0 restated: writes only `$Z0_HOME/{bootstrap,venv,cache/git,onboard/runs}`; `--stdout` writes nothing |
| Python ≥ 3.8 threshold | ≥ 3.10 everywhere |
| `git archive` releases lack `.git`, submodules, LFS | `build_tree` (with git, submodules, LFS) runs git-needing steps; `stage_release` copies the tree without `.git`; `where:` is required per step |
| Stale facts between plan and apply | volatile-fact re-detect + re-plan; re-confirm if grants would widen; no wall-clock expiry |
| z0int delegate depends on an unmerged PR | contract detection; the interim path never runs z0int's impure dry-run on the real home; snapshot undo excludes `shadow/` |
| Hermes LLM profile pick | removed; Hermes is always an ask |
| Bend domain too large or vague | split into six small `decide_*` functions (≤ ~2k rows); the proof status of each law is listed honestly |
| Bun 1.4.3 vs the desktop host | user-local bun for new releases; adopted units kept; switching is an ask (D-7) |
| Two sources of truth (`onboard:` vs legacy) | R-sync projection, enforced by `registry-check` |
| Predicate parser cost | structured `when:` data with a tiny matcher |
| Test runner undecided | stdlib unittest; no Hypothesis |
| Running `--help` on unknown binaries | unknown binaries are classified by name, symlink and shebang only; `exec_probe` policy per harness |
| Legacy dash runs the 0.0.0.0 path | legacy is refused (D2) |
| "Any failure is fatal" | failures block only dependents; one triaged retry |
| Quota spent without disclosure | local-first; remote or quota providers are listed in the confirmation; model ids come from `onboarding.yaml` |
| Too many subcommands | 7 subcommands; report.md opens with "What you need to do" |
| Editing `cmd_init` risks back-compat | `commands.py` untouched until Z6, which starts with characterization tests |
| No ownership check on rollback | `.z0-owned` markers + journal hash; changed files are kept |
| No concurrency guard | fcntl lock |
| Dash unreachable for strangers | public-ready gates + WP-D1/D3/D4; degrades to `unavailable` without blocking other components |
| z0int non-editable vs dev-mode editable | the live runtime is a non-editable venv built in place (spec release mode); the editable `.venv` is a contributor opt-in that live config never references |
## Owner decisions (2026-10-25)
- D-1: --auto uses ONE enumerated go/no-go confirmation for C1 (`--yes` skips); C2 never automatic.
- D-2: LLM resolver is local-first; remote providers only after that confirmation; redacted facts; candidate-only answers.
- D-4: Dash served line is secret-scanned, then pushed as a branch + release tag (not main); onboarding pins it.
- D-6: z0intelligence pin bumps to master cfb33e5 (stamped release, never editable).
