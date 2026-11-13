# Tool onboarding evidence for R10

R10 remains incomplete. This check records native command results separately from integrated workflow acceptance.

## Existing ownership and acceptance

- `z0` owns the map, installer, registry, and documentation, not execution. See `README.md:5` and `AGENTS.md:48-57`.
- Hermes owns its doctor and model/tool runtime. The harness registry prohibits automatic execution probes. See `registry/harnesses.yaml:30-49`.
- `z0 doctor` returns zero after reporting component and interface inventory, even when nothing is observed. See `lib/z0/commands.py:122-155`.
- The existing operational acceptance check remains `/mnt/zer0models/workspace/zer0/data/operations/t3-thread-triage/20261104/reports/integration-check.py:21-81`. It checks cleanup configuration, artifact reclamation, fleet health, and admission. Its scope excludes all-tool onboarding. This smoke does not replace it.

## Repeat the safe subset

From this checkout, run:

```bash
python3 scripts/tool-onboarding-smoke --output /path/to/new-evidence --public-hf
```

The command writes exact argv, exit codes, output logs, entrypoint inventory, and `acceptance.json`. It makes no repairs. It does not execute Hermes, SSH, Kubernetes, model inference, login, or GUI commands. It gives HF a minimal environment, an isolated `HF_HOME`, and no implicit tokens. See `scripts/tool-onboarding-smoke`.

The public workflow downloads only `gpt2/config.json` at revision `607a30d783dfa663caf39e06633721c8d4cfcd7e`. Native HF checksum verification checks the downloaded file. Python parses the config, and RTK must reproduce its bytes exactly. Missing weights are expected. This is not authenticated onboarding, inference, or a Hermes/T3 round trip.

Exit 1 and top-level `passed=false` are deliberate. This command cannot close R10, even when every bounded command succeeds. Exit codes in `checks` describe command execution, not component health. The workflow has its own bounded result.

## Observations on 2026-11-13

Evidence root: `/mnt/zer0models/workspace/zer0/data/operations/intent-analyzer-20261104/ayo-runs/exec-R10`.

| Observation | Evidence relative to evidence root |
|---|---|
| T3 dry-run exited 0, reporting 1.21 GiB reclaimable from a 1.97 GiB database. No repair ran. | `logs/current/t3-doctor.log:1-18` |
| Both user services were active/running. This is liveness only. | `logs/current/service-state.log` |
| HF 2.4.0 downloaded the pinned config and verified its checksum. Native verification warned about 25 absent remote files. | `logs/current/hf-version.log`, `logs/current/hf-download.log`, `logs/current/hf-verify.log:1-11` |
| RTK 1.2.0 reproduced the config bytes. Rewrite exit 3 means that host approval remains necessary, not that rewriting failed. | `logs/current/acceptance.json`, `logs/provenance.log` |
| The Hermes entrypoint invokes the managed vault wrapper. That wrapper retrieves and injects credentials. No bypass ran. | `logs/hermes-wrapper-source.txt:2-5`, `logs/vault-wrapper-source.txt:15-32,70-87` |
| The cached MBP receipt reported unhealthy/paused admission. This is a cached receipt, not a fresh admission probe. | `logs/fleet-health-snapshot.json` |

## Unresolved acceptance

1. Run the native Hermes doctor through the existing credential wrapper under separately authorized credential use. Its source also loads dotenv and auth state. See `hermes_cli/doctor.py:10-20,73-87,113-132` in the Hermes repo, copied to `logs/hermes-doctor-source.txt`.
2. Qualify a no-spend route and observe a synthetic Hermes/T3 model-plus-tool round trip. Do not infer this result from service liveness or a storage doctor.
3. Establish whether HF means Hugging Face in the owner request, and identify the intended workflow from permitted operational records. No raw owner history was read. Authenticated or gated use needs separate authorization if required.
4. Run current web extraction, memory, and Serena acceptance through their existing owners. The historical audit remains `/mnt/zer0models/workspace/zer0/data/operations/tool-skill-audit-20261104/AUDIT.md:19-50`.
5. Reconcile the current deployed onboarding owner. This worktree is based on the existing `kvnloo-z0` map checkout, not proof of a deployed `z0` command. The earlier verdict's `z0-bindings` checkout was not located. `~/.z0/onboard/current/report.md` was absent during inspection.

No all-tools test suite or authenticated end-to-end test ran. Heavy tests must use `fleet-build` under the compute brief. No local heavyweight fallback is permitted.
