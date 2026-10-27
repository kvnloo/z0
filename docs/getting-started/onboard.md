# Onboard a new host

Start from a public clone:

```bash
git clone https://github.com/kvnloo/z0 && cd z0
./z0 onboard
```

On a terminal, choose **auto** (the default) or **guided**. Without a terminal,
this is auto mode; it never waits for input. Stage 0 finds Python or offers a
checksummed, user-local toolchain, then creates z0's own environment. Do not
install dependencies into system Python or use `--break-system-packages`.

> Onboarding is experimental. Component APIs and pins can change. This branch
> contains the guided UX on the Z2 engine: the Z3/Z4 service and harness actions,
> Dash pairing, and Z5 provider resolver must be integrated before the complete
> runtime path is available. Unsupported actions fail visibly; a plan or a green
> unit-test run is not evidence that a real host was installed successfully.

## Minimal or full interaction

```bash
./z0 onboard --auto --yes    # minimal interaction: no questions, C1 bundles granted
./z0 onboard --guided        # full interaction: deterministic defaults are displayed
```

“Minimal” and “full” describe **interaction**, not profiles. Auto selects a
hardware-appropriate profile and includes the gated `dash` and `z0evals`
supplementals. Use `--profile core`, `--with IDS` or `--without IDS` to change
that target set. Guided asks for the profile, each supplemental, pin policy,
LLM policy and each runnable C1 step. Press Enter to retain the displayed
choice; write confirmations default to **no**. Explicit bundle grants also
apply in guided mode; `--yes` is not permission for C2 actions.

```bash
./z0 onboard --auto --profile core --without dash --plan-only
./z0 onboard plan --stdout --llm none  # JSON dry run, no writes when PyYAML imports
./z0 onboard --auto --accept toolchains,harness
```

A normal plan writes only z0's cache/run artifacts; `--plan-only` does not apply
steps. `--guided` without a terminal is a usage error (exit 2). The default LLM
policy is local-first; `--llm none` requires no model. A remote classifier is
not an executor and never grants consent. Provider execution depends on the
Z5 integration noted above; choosing `auto` does not itself authorize spending.

## Consent: what can change

| Class | Scope | Behaviour |
|---|---|---|
| **C0** | z0-owned state, releases and per-component environments; declared repo-local setup in a clean adopted tree | Applied without an additional consent prompt. |
| **C1** | Reversible user-scoped changes in the four bundles below | Auto shows **one enumerated go/no-go confirmation**. `--yes` grants all bundles; `--accept` grants a subset. Guided asks per runnable step. |
| **C2** | System/global or sensitive actions | Remain explicit manual asks in this UX; neither `--yes` nor `accept BUNDLES` authorizes them. |

C1 bundles:

- `toolchains`: pinned, checksummed user-local downloads, not system packages.
- `harness`: permitted harness plugins and links, backed up before changes.
- `services`: user service definitions, interpreter shims and component config.
- `models`: bounded model/wheel installation declared in the plan.

Examples of C2: sudo/system packages, `tailscale up`, linger, dotfiles, private
clones, native Android builds, large model sync, redeploying an adopted running
unit at another SHA, and **every Hermes profile/config edit**. Grok and Cursor
are policy-excluded, not alternative automatic backends. Authentication remains
in the owning app; no login credentials belong in answers, workspace YAML,
receipts or prompts. The guided secret-input helper uses `getpass`, refuses an
echoed fallback and passes a value only to a supplied owning-store writer; this
branch does not introduce a generic credential file or prompt for app logins.

Without a terminal and without grants, auto still applies C0, leaves C1 as asks,
and exits **3**. It does not silently broaden consent. A required failure exits
**1**; a host/law refusal exits **4**. Exit 0 means required runnable checks passed;
read the unavailable/ask sections too, rather than treating skipped work as installed.

## What gets installed

The registry and the actual host gates determine the plan, not this overview:

- **Dash**: pinned app/bridge releases and dependencies; public/null-renderer
  fallback where necessary. A bridge unit needs a detected current tailnet address
  and the services grant. Without a tailnet, no bridge unit is installed; joining
  the tailnet remains manual. STT is gated on resources and the models grant;
  Metro is optional (`--with dash-metro`). Native Android builds and phone setup
  are not automatic. Unpublished or legacy pins are unavailable/refused, never
  replaced with an unverified checkout.
- **z0intelligence** (when the selected profile includes it): a stamped release,
  a separate runtime environment, a hardware-appropriate torch plan and gated
  shim/plugin/service steps. Live code must not point at an editable checkout.
  Intel macOS and unsupported Python windows are refused. Hermes configuration
  and the upstream onboard delegate remain asks where their contracts are absent.
- **z0evals**: source plus a private environment, ordered Python checks and,
  when Node/network gates permit, generated web data and the web build checks.
  Maintainer promotion scripts, visual probes and skill/config linking are not
  automatic. No z0evals service is installed.

These describe the registered target plans. Missing component actions on this
branch are reported as failures, not claimed as installed. Inspect `report.md`
for the SHA, actual step outcomes, unavailable features and acceptance results.

### macOS services

Linux/systemd is the release-service path. On macOS **guided mode only** offers
an inspectable z0intelligence LaunchAgent preview under the run's `launchd/`
directory. It uses planned stamped runtime/release paths and a Python `fcntl`
lock instead of `flock`. XML round-trips through `plistlib`; on macOS you can run
`plutil -lint <preview.plist>` before reviewing it. This is **rendering only**:
no `Library/LaunchAgents` files are changed and `launchctl` is not invoked.
Auto mode never renders or starts these agents. A preview is not service-health
or installation evidence.

## Read the result; grant a deferred bundle

```bash
./z0 onboard status
./z0 onboard accept toolchains,harness
./z0 onboard accept services models
```

`status` is read-only: it prints **What you need to do** first, then the last
applied run's receipt summary, failed steps, installed SHAs and report location.
It does not probe drift or run network/process checks; use `onboard plan` for
fresh detection. Before any applied run, it tells you to run `./z0 onboard`.

`accept` reads that run's last effective plan, re-detects the host, re-checks
kernel gates and grants the named **C1 bundles only**. It executes only pending,
unchanged C1 steps that were already in that plan. It never replays unrelated C0,
C2, newly discovered steps or completed steps; missing prerequisites require a
normal onboarding rerun. It refuses host mismatches and changed registry hashes.
The delta, receipt and effects stay in the original run's journal so rollback
can undo them together. This command is not a C2 ask-id executor. For a complete
fresh acceptance pass after prerequisites change, rerun `./z0 onboard`.

`./z0 init` routes real installs through this same engine and propagates its exit
code. `init --dry-run` retains the legacy profile-only, no-write inventory (no
supplementals). `./z0 doctor` stays a read-only inventory and points here; its
legacy exit code is not an onboarding acceptance gate.

## Where state lives and how to roll back

By default state lives in `~/.z0`; set `Z0_HOME` to choose another location.
Run directories are private (0700; files 0600):

```text
$Z0_HOME/onboard/runs/<run-id>/
  host.json  plan.json  plan.diff.txt  journal.jsonl
  backups/   receipt.json  report.md
```

`$Z0_HOME/onboard/current` identifies the last applied run. Do not publish these
private host receipts. Applying a saved run checks its plan hash and freshness;
`--yes` on `apply` cannot add grants.

```bash
./z0 onboard rollback                  # last applied run, including accepted bundles
./z0 onboard rollback <run-id>         # a specific run
./z0 onboard rollback --purge-bootstrap # also remove owned stage-0 tooling
```

Rollback reverse-replays journaled effects. It removes only owned, unchanged
artifacts and restores backups/symlinks when ownership and hashes permit it.
User-edited files and adopted checkouts are kept and reported. Existing app
credentials are not deleted. Cache mirrors remain unless `--purge` is supplied.
Rollback is safe to repeat, but it cannot undo arbitrary external effects or
manual C2 work. Keep the journal and backups until you are satisfied.

For the contracts, gates, and distinction between tested and Bend-proven laws,
see [the onboarding design](../onboarding/DESIGN.md).
