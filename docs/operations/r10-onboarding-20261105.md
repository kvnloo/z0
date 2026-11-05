# R10 onboarding evidence, 2026-11-05

R10 remains incomplete. The bounded smoke reports `accepted: false` even when its public HF workflow passes. Source: `scripts/tool-onboarding-smoke.py:92-109`.

## Evidence locations

`E` below means `/mnt/zer0models/workspace/zer0/data/operations/intent-analyzer-20261104/ayo-runs/exec-R10`.
The source checkout is `/mnt/zer0models/worktrees/z0-bindings`, base `b8408586f4870aff996fb287ea998f0cacf661b0`. It contains an untracked `.artifact-lease.json`. The isolated worktree is `/mnt/zer0models/worktrees/ayo-R10`, branch `ayo/R10`. Source: `E/logs/z0-checkout.log:1-9`, `E/logs/worktree-create.log:1-4`.

## Current observations

| Tool | Entrypoint and existing owner | Current evidence | Unresolved scope |
|---|---|---|---|
| Hermes | Managed files-bws launcher, then native Hermes. Reliability and tooling owner 59858c98 retain ownership. | Launcher invokes `bws-env-exec` unconditionally. Native doctor was not run. | Credential handling is forbidden. Historical doctor and model-turn receipts are not current proof. |
| T3 | `~/.local/bin/t3` resolves to nightly `0.1.8-nightly.20261105.4218`. Native T3 maintainers. | `t3 doctor --dry-run`, exit 0. Database 1.97 GiB, 4 KiB reclaimable, no changes. | Database maintenance is not a model-plus-tool workflow. No fix, vacuum, delete, or restart ran. |
| HF | `hf` is Hugging Face Hub 1.28.0. Intended owner workflow is unspecified. | Anonymous pinned config download, RTK key inspection, jq semantic check, HTTP 200 and identical bytes all passed. | This is public metadata only. No authenticated access, model inference, or confirmation of the owner's meaning of HF. |
| z0 | Source checkout above. No `z0` executable on PATH. | Native wrapper exits 1 for missing config parsers. Offline cached dependencies allow source doctor and binding observation, both exit 0. | No canonical deployed entrypoint established. Inventory doctor observes no component or interface. Binding doctor reports drift despite exit 0. |
| ctx | `~/.local/bin/ctx`, existing ctx maintainers. | `ctx doctor --format json` exits 0 but reports `ok: false`. | History and lexical indexes require generation upgrade. Refresh is pending, source discovery incomplete, daemon disabled. |
| AgentsView | `~/.local/bin/agentsview`, existing AgentsView maintainers. | `agentsview doctor sync` exits 0. Database readable, SQLite and binary versions both 113. | Root `agentsview doctor` only displays help. Sync diagnostics do not prove current cross-tool retrieval. |
| RTK | `~/.local/bin/rtk`, installed version 1.1.0, existing tooling owner. | Consumed the HF artifact through `rtk json --keys-only`, exit 0. | No claim about every harness's rewrite plugin or output fidelity. |

Sources for the table:
- Hermes launcher: `/home/kvn/.local/bin/hermes:1-3`. Existing ownership: `/mnt/zer0models/workspace/zer0/data/operations/t3-thread-triage/20261104/handoffs/4-reliability-ACK.md:3-17`.
- Entrypoints and service liveness: `E/logs/entrypoints-services-clean.log:1-59`. Active units do not prove integration.
- Versions: `E/logs/tool-versions-help.log:1-11`. T3 result: `E/smoke-1/t3-doctor.log:1-19`.
- HF command, consumers, digest, and scope: `E/smoke-1/acceptance.json:88-205`. HTTP status: `E/smoke-1/hf-http-witness.log:1-7`. Anonymous request: `E/smoke-1/hf-public-download.log:1-5`.
- z0 wrapper dependency check: `z0:1-9`. Native failure: `E/smoke-1/z0-native-doctor.log:1-4`. Source inventory: `E/smoke-1/z0-isolated-doctor.log:1-78`.
- ctx result: `E/logs/ctx-doctor-summary.json:1-15`, extracted from the native output in `E/logs/ctx-doctor-agentsview-help.log`.
- AgentsView result: `E/logs/agentsview-doctor-sync.log:1-19`. Its later log-tail rows are historical sync observations, not newly executed syncs.

## Native binding findings

The existing `z0 doctor --bindings` inspected only Hermes profile `clean`, without inventing desired enablement. It records 11 findings and leaves desired state unknown. Source: `E/smoke-1/native-bindings.json:8-70`.

- ctx has a recipe mismatch and its declared `ctx.service` is inactive. This alone does not prove that its stdio MCP is broken.
- emma, hermes_memory, noop, vitryne, and z0int-memory are configured but unregistered in this checkout.
- agentsview and tencentdb-memory are registered but unbound. z0bridge and z0live have no observable supported binding.

These are registry observations, not authority to enable every optional tool. The existing doctor deliberately returns 0 after writing observations. Source: `lib/z0/bindings.py:517-565`.

## Reproduction and limits

`python3 scripts/tool-onboarding-smoke.py --output /new/evidence/directory` captures exact commands, output, exit codes, entrypoints, and the existing native binding receipt. It refuses an existing output directory. It uses only cached dependencies and disables implicit HF authentication, telemetry, and update checks. Source: `scripts/tool-onboarding-smoke.py:14-109`.

The initial run took about five seconds locally. The final script also passed the same HF workflow in `E/smoke-2/acceptance.json`. Both runs exit 1 because full owner acceptance remains false. No heavy suite, build, eval, or fleet job ran. Verification used static AST parsing, real CLI execution, and a no-overwrite check. Sources: `E/logs/smoke-run.log`, `E/logs/smoke-final.log`, `E/logs/static-checks.log`, and `E/logs/no-overwrite-check.log`.

`E/logs/entrypoints-services.log` is INVALID evidence because that shell accidentally replaced PATH through zsh's special `path` variable. Use the clean inventory instead. The initial AST label in `smoke-run.log` describes the later exact command recorded in `static-checks.log`; the initial invocation used `ast.parse` through `python3 -c`.

The contract forbids credentials, spending, and service restarts. Therefore Hermes native doctor, a new Hermes/T3 model turn, and gated HF login were not attempted. Historical web, memory, history-tool naming, and Serena gaps remain unverified here. Source: `E/ITEM.json:8-16`, `E/smoke-1/acceptance.json:206-213`, `/mnt/zer0models/workspace/zer0/data/operations/tool-skill-audit-20261104/AUDIT.md:29-50`, and the Reliability handoff cited above.
