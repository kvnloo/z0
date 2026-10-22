---
id: guides.add-a-tool
title: "OMPB1-06: Add a tool"
scope: [z0, oh-my-pi, z0intelligence, kerdoios]
concepts: [registry, host-profiles, bindings, drift]
status: draft
---

# Add a tool

One front door for adding a tool to Zer0: **register → enable → bind → verify**.
Use the same path for a new MCP server, memory source, model provider, or worker
without moving its implementation into `z0`.

> **Implementation status (2026-10-22): proposed, not deployed.** This guide
> describes the contract requested in [z0 #15](https://github.com/kvnloo/z0/issues/15#issuecomment-6353289693).
> Today `./z0 init --dry-run`, `./z0 add`, `./z0 status` and `./z0 doctor`
> exist. The `bindings` validator is proposed in
> [PR #30](https://github.com/kvnloo/z0/pull/30) (`feat/component-bindings`);
> the registry examples below follow that draft schema. The `.files`
> `z0_components` field, `z0 apply`, harness-config drift checks and
> `fleet health` integration remain **future slices**, not deployed config.
> Do not infer host adoption from this document.

## The three steps

1. **Register — `kvnloo/z0`.** Identify the owning implementation first.
   For an installable product/service, add its ID to
   [`registry/components.yaml`](../../registry/components.yaml) using existing
   `kind`, `status`, `execution`, `boundaries`, `install` and `verify`
   fields; the proposed additive `bindings` block declares how named harnesses
   consume it. Use [`registry/harnesses.yaml`](../../registry/harnesses.yaml)
   for harness metadata; the canonical harness IDs come from
   [AODL's catalog](https://github.com/kvnloo/aodl/blob/main/harnesses/catalog.json)
   (notably `claude`, not `claude-code`). Do not turn every model, research
   note, or worker into an installable component just to get a registry row.
2. **Enable — `kvnloo/.files`.** A reviewed `fleet.toml` host profile
   (proposed) declares a `[hosts.<logical_id>.z0_components]` table:
   exact registry component IDs map to explicit harness/profile selector arrays.
   Use logical IDs `desktop`, `mbp`, `phone` (not the hostname `groot`).
   `.files` owns installation, service startup, host-specific paths and secret
   references. A registry entry alone enables nothing; never commit credentials.
3. **Bind — `z0 apply` / `z0 doctor`.** The **planned**
   `z0 apply --dry-run` renders a diff of each *native* harness config.
   After human inspection, an explicit `--apply` may write only the
   approved host/harness selections. The **planned extended**
   `z0 doctor` reads back desired versus observed configuration;
   `fleet health` can project that status. Neither command supplies
   execution permission, tests a model's behavior, or promotes an unverified
   integration.

Native binding targets: Hermes profiles (`mcp_servers` and, where
supported, `memory.provider`); Claude Code `~/.claude.json`; Codex
`~/.codex/config.toml`; OMP `mcp.json` and harness-owned extensions.
Do **not** overwrite entire profiles or install a universal MCP gateway as
the default. Generate minimal native diffs while retaining each harness's
selection, scope and approval gates. An optional `mcporter` gateway is a
separate, later architecture choice.

### Where code belongs

| Tool type | Implementation owner | What `z0` maps |
|---|---|---|
| Upstream MCP server | Its installed upstream package | Package identity, binding, scope and verification recipe |
| Memory/history source | Its own store; evidence contract at [z0intelligence #22](https://github.com/kvnloo/z0intelligence/issues/22) | Retrieval capability; never authoritative current belief |
| Model/provider | [Kerdoios](https://github.com/kvnloo/kerdoios) inventory/adapters | Placement binding, not semantic model choice or secrets |
| Worker type | [oss-factory](https://github.com/kvnloo/oss-factory) worker contract | Where it can be invoked; no new scheduler |
| Harness-native behavior | That harness's plugin/extension | Supported harness ID and adapter hook |
| Research only | [frontier-kb](https://github.com/kvnloo/frontier-kb) | Research link, **not** an enabled tool |

`z0` owns the cross-repo map; `.files` owns host intent; harnesses execute;
z0intelligence constructs evidence-derived state; AODL owns authored
intent/authority; Kerdoios places eligible computation; and independent
verification is separate from setup.

## Worked examples (proposed schema, not runnable config)

The snippets illustrate **which owner changes what**. Reconcile actual CLI
arguments, IDs, validation, permissions and host paths against the owning
project before implementation. No example is proof of current enablement.

### 1. Add an MCP server: scoped filesystem tools

Register a package-owned MCP endpoint in `registry/components.yaml`,
without forking its code into `z0`. This is a *shape example*, not a tested
server command or an invitation to expose a whole home directory:

```yaml
components:
  filesystem-mcp:
    name: Scoped filesystem MCP
    kind: service
    status: experimental
    execution: shadow
    boundaries:
      owns: [filesystem MCP service]
      not_here: [harness approval policy, host paths]
    install:
      command: "<package owner's documented install step>"
    verify:
      command: "<read-only MCP handshake and scoped probe>"
    bindings:
      mcp:
        command: npx
        args: [-y, "@modelcontextprotocol/server-filesystem", "${MCP_SHARE_ROOT}"]
      harnesses: [hermes, omp, claude, codex]
```

Then opt a host into `filesystem-mcp` in `.files` and explicitly scope
`MCP_SHARE_ROOT` to authorized files. The renderer should create/update only
selected harness MCP entries, preserve each client's permissions, and show
the exact command/args in the dry-run diff. Check a native tool listing,
then perform a permitted *read-only* probe; write-capable tools still require
their own native authorization.

### 2. Add a memory evidence source: GraphRAG

GraphRAG is **not bound to any harness** in the snapshot reported by #15.
Treat retrieval as **evidence**, not a new global memory authority:

```yaml
components:
  graphrag:
    kind: memory-source
    status: experimental
    execution: shadow
    boundaries:
      owns: [GraphRAG source retrieval]
      not_here: [current belief, execution permission, canonical transcript]
    install:
      command: "<GraphRAG owner's install instructions>"
    verify:
      command: "<source-backed read-only retrieval probe>"
    bindings:
      mcp:
        command: graphrag-mcp
        args: [--root, "${GRAPHRAG_ROOT}"]
      harnesses: [hermes, omp, claude, codex]
      hermes: {memory_provider: null}
    evidence_source_for: [z0intelligence.context-packet]
```

`graphrag-mcp` is the **proposed command from #15**, not a verified local
binary. Enable only hosts with an authorized `GRAPHRAG_ROOT`. Hermes's
`memory_provider: null` deliberately does **not** claim a native memory
provider is active. Bind GraphRAG through a thin retrieval adapter, preserve
source revision/identity, scope, freshness and contradictions, and verify
both retrieval **and** actual model-visible consumption before counting
integration. Keep the State Packet contract with z0intelligence #22.

### 3. Add a model provider: Kerdoios

A new provider or model SKU belongs in the **Kerdoios provider inventory**,
not in a second catalog of secrets inside `z0`. The existing `kerdoios`
component is already registered. Register or update `bindings` on that
component **only if** the host/harness integration changes:

```yaml
# Illustrative addition to the existing components.kerdoios mapping
bindings:
  harnesses: [hermes, omp, codex]
  hermes: {provider_adapter: kerdoios}
  omp: {provider_adapter: kerdoios}
  codex: {provider_adapter: kerdoios}
```

PR #30 permits adapter metadata under a selected harness ID, not arbitrary
top-level keys such as `bindings.provider_adapter`. These proposed
`provider_adapter` hooks are descriptive; no native renderer implements them
yet. Do not infer adapter support merely because the metadata validates.

Enable `kerdoios` for the intended host in `.files`; pass credentials by
host-local secret references, never committed YAML or a generated diff.
The adapter consumes a capability/model-class requirement already selected
upstream, then uses Kerdoios for eligible placement, budget/quota/latency
and fallback. Verify one eligible and one ineligible route; **never**
silently substitute a cheaper, semantically invalid model. See
[Kerdoios #55](https://github.com/kvnloo/kerdoios/issues/55).

### 4. Add a worker type: oss-factory

Keep worker claiming, leases, exact-head receipts and coordination with
[oss-factory](https://github.com/kvnloo/oss-factory), not with the `z0`
installer or a new master harness. If the factory coordinator needs an
installable/service identity, register its ownership and proposed binding:

```yaml
components:
  oss-factory:
    repo: kvnloo/oss-factory
    kind: worker-coordinator
    status: experimental
    execution: shadow
    boundaries:
      owns: [factory worker contract, claims, result receipts]
      not_here: [per-harness execution, cognition/authority policy]
    install:
      clone: https://github.com/kvnloo/oss-factory.git
      command: "<owner-approved setup>"
    verify:
      command: "<owner contract and readback checks>"
    bindings:
      # PR #30 records no supported native harness binding yet.
      harnesses: []
```

Enable the coordinator's local runtime on approved hosts with an empty
selector array, **not** all harnesses by default. Register a harness-specific
adapter only after its contract exists. A harness plugin may then request an
authorized worker card; oss-factory owns
claim/collision checks and durable receipts. A configured worker is not an
executed card, verified outcome or authorized upstream promotion. Reuse
[factory #201](https://github.com/kvnloo/oss-factory/issues/201) for its
existing preflight ownership.

## Host profile and verification

Follow the [`.files` field proposal](https://github.com/kvnloo/.files/issues/16#issuecomment-6353585727),
normalizing its display name `claude-code` to AODL's **`claude`**:

```toml
# Proposed .files syntax; none of these selections are deployed by this guide.
[hosts.desktop.z0_components]
"filesystem-mcp" = ["hermes:default", "claude", "codex", "omp"]
"graphrag" = ["hermes:default"]  # only after its proposed adapter exists
"kerdoios" = ["hermes:default", "codex", "omp"]
"oss-factory" = []             # local runtime only, no harness injection
```

Keys must match exact registry IDs; for example PR #30 uses
`tencentdb-memory`, not the host proposal's `tencentdb-gateway`.
Selectors use canonical AODL harness IDs, with `hermes:<profile>` selecting
one explicit Hermes profile. No wildcard or implicit profile expansion.
Empty arrays request local presence only; absence is not a deletion request
for unmanaged configuration. Hermes `clean` remains `ctx`/`noop` only, without
TencentDB or a z0intelligence memory hook; missing IDs/adapters remain blocked.

Logical-host joins are explicit: `desktop → groot`, `mbp → mbp`,
`phone → omarchy-phone`; the proposed `phone_s22plus → galaxy-s22plus`
requires verified identity before automatic planning. An ambiguous PRoot
hostname is insufficient; PRoot has no systemd or K3s.

Expected selection = registered `bindings.harnesses` **intersection** explicit
host/component selectors **intersection** supported native adapter. Profile
selection belongs in `.files`, not in `bindings.harnesses`. Reject unknown
AODL IDs, missing commands, disabled profiles, secrets without local references,
unsupported platforms and disallowed tool scopes. The GraphRAG, Kerdoios and
worker examples above describe future adapters, not current PR #30 enablement.

In PR #30, `bindings` accepts shared `mcp`, `harnesses`, and per-harness
mapping overrides whose keys must appear in `harnesses`. MCP declares exactly
one of `command` or `url`; stdio permits `args`/`env`, HTTP permits `headers`.
`memory_provider` is a per-harness string or null. The GraphRAG example's
`hermes.memory_provider: null` declares no native provider activation.
The host proposal does not enable GraphRAG/QMD/Supermemory/Memento by default.

```bash
# Available today (registry/install inspection, not harness binding):
./z0 init --profile core --dry-run
./z0 status
./z0 doctor

# PROPOSED future commands; do not run against current main:
z0 apply --dry-run
z0 apply --apply          # explicit owner-reviewed mutation only
z0 doctor                # future: native config drift/readback
fleet health             # future: host-level projection
```

| Stage | Evidence needed | Never infer |
|---|---|---|
| Registered | Registry commit, valid owner/boundary/schema | Installed |
| Desired | Host/profile revision and explicit harness opt-in | Configured |
| Configured | Readback of exact native file/extension at host + harness revision | Running |
| Running | Fresh process/handshake with timestamp and age | Used |
| Used | Actual authorized invocation and scoped result | Independently verified |
| Verified | Verifier/receipt linked to the intended outcome | Generalized or universally enabled |

Each `z0 doctor` drift row (future) should include host, harness ID/version,
registry/profile revision, desired state, observed state, observation time/age,
exact diff, supported probe result and explicit unknowns. Missing access,
stale observation or absent telemetry must be reported as **unknown/not
verified**, never green. Store no private history or credentials in `z0`.

## Review / rollback checklist

- [ ] Confirm owner, package origin, trust boundary and native harness hook.
- [ ] Pin install/verify instructions to evidence; mark missing/experimental
      implementations honestly (see [#18](https://github.com/kvnloo/z0/issues/18)).
- [ ] Review the host/harness intersection and inspect every generated diff.
- [ ] Apply only with `--apply` after explicit owner review; preserve backups,
      unrelated settings and per-harness approval gates.
- [ ] Read back native configs, probe a least-privilege call, then verify an
      independently observable outcome; record failures and unknowns.
- [ ] On mismatch or failure: disable the host opt-in, restore the prior
      generated config/extension state, restart only affected services with
      authorization, then rerun readback. Never silently expand scope.

Implementation follows #15's separate draft slices: registry `bindings` +
validator; `.files` host intent; `z0 apply --dry-run` and doctor/fleet
readback. **This guide adds no runtime, installer behavior or live binding.**
