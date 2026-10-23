# Component bindings and observed evidence

Bindings are declarative consumption recipes, not host enablement or runtime proof.
Harness ids come from AODL. `.files` owns host/profile intent; native adapters bind tools.
Dated observations are separate snapshots, not continuously refreshed health checks.

## `agentsview`

### Declarative bindings

```json
{
  "mcp": {
    "command": "agentsview",
    "args": [
      "mcp"
    ]
  },
  "harnesses": [
    "hermes",
    "omp",
    "claude",
    "codex"
  ]
}
```

Evidence source for: `z0intelligence.context-packet`

### Observation (2026-10-22, groot)

The capability snapshot records MCP configured in Hermes chiefstaff, OMP, Claude Code and Codex, plus an agentsview-sync timer. It does not prove every connection is live or establish shared-continuity acceptance.

- https://github.com/kenn-io/agentsview/blob/main/README.md
- https://github.com/kenn-io/agentsview/blob/main/docs/commands.md
- /mnt/zer0models/workspace/zer0/data/operations/capability-matrix/20261022.md

## `ctx`

### Declarative bindings

```json
{
  "mcp": {
    "command": "ctx",
    "args": [
      "mcp",
      "serve"
    ]
  },
  "harnesses": [
    "hermes"
  ]
}
```

Evidence source for: `z0intelligence.context-packet`

### Observation (2026-10-22, groot)

systemctl --user show reports ctx.service enabled, active/running. The unit runs ctx daemon run; installed ctx mcp --help documents stdio serve. The snapshot records MCP configured in Hermes clean and rippletern. This is not a universal default switch or qualified continuity result.

- https://github.com/ctxrs/ctx/blob/main/README.md
- /home/kvn/.config/systemd/user/ctx.service
- systemctl --user show ctx.service --property=Id,ActiveState,SubState,UnitFileState,FragmentPath (2026-10-22)
- ctx mcp --help (2026-10-22)
- /mnt/zer0models/workspace/zer0/data/operations/capability-matrix/20261022.md

## `graphrag`

### Declarative bindings

```json
{
  "harnesses": []
}
```

Evidence source for: `z0intelligence.context-packet`

### Observation (2026-10-22, groot)

The local README documents installed GraphRAG 3.3.0 and batch commands, with no service. The newer capability snapshot records an incomplete full index and no finished graph/query service/MCP/skill. Built does not mean integrated or query-ready; no private corpus is published here.

- https://github.com/kvnloo/graphrag/blob/main/README.md
- /mnt/zer0models/sft-svlm/data/graphrag/README.md
- /mnt/zer0models/workspace/zer0/data/operations/capability-matrix/20261022.md

## `memento`

### Declarative bindings

```json
{
  "harnesses": []
}
```

### Observation (2026-10-22, groot)

Not enabled. The repository implements a screen-capture/timeline app; Kevin's ecosystem sensor integration remains an idea, not a running service.

- https://github.com/kvnloo/Memento/blob/main/README.md
- https://github.com/kvnloo/z0/issues/1
- https://github.com/kvnloo/z0/issues/15#issuecomment-6353289693

## `oss-factory`

### Declarative bindings

```json
{
  "harnesses": []
}
```

### Observation (2026-10-22, source-only)

Existing factory operations are documented; app-worker concurrency and durable one-turn handoffs have separate open qualification work. No MCP server, universal harness binding or thousand-worker readiness is claimed.

- https://github.com/kvnloo/oss-factory/blob/842af1a26b4854d4e2702d175ae5b45d75877d70/README.md
- https://github.com/kvnloo/oss-factory/issues/214
- https://github.com/kvnloo/oss-factory/pull/215

## `qmd`

### Declarative bindings

```json
{
  "mcp": {
    "command": "qmd",
    "args": [
      "mcp"
    ]
  },
  "harnesses": []
}
```

Evidence source for: `z0intelligence.context-packet`

### Observation (2026-10-22, source-only)

Upstream documents CLI and stdio/HTTP MCP. The inspected host snapshot lists no QMD MCP binding; actual host enablement is not established here. Registry evidence-source intent does not promote it to a universal tier.

- https://github.com/tobi/qmd/blob/main/README.md
- https://github.com/kvnloo/z0intelligence/issues/136
- /mnt/zer0models/workspace/zer0/data/operations/capability-matrix/20261022.md

## `supermemory`

### Declarative bindings

```json
{
  "mcp": {
    "url": "https://mcp.supermemory.ai/mcp"
  },
  "harnesses": []
}
```

Evidence source for: `z0intelligence.context-packet`

### Observation (2026-10-22, groot)

The capability snapshot records disabled staging in an isolated Hermes home, blocked on a missing API key on October 21. No credential, live connection, provider comparison or all-harness availability is claimed.

- https://github.com/supermemoryai/supermemory/blob/main/README.md
- /mnt/zer0models/workspace/zer0/data/operations/capability-matrix/20261022.md
- https://github.com/kvnloo/z0evals/pull/114

## `tencentdb-memory`

### Declarative bindings

```json
{
  "harnesses": [
    "hermes",
    "omp"
  ],
  "hermes": {
    "memory_provider": "memory_tencentdb"
  },
  "omp": {
    "extension": "tencentdb-memory"
  }
}
```

Evidence source for: `z0intelligence.context-packet`

### Observation (2026-10-22, groot)

systemctl --user show reports tencentdb-memory.service enabled, active/running. The unit starts the local Docker gateway wrapper on loopback :8420. The snapshot records memory_tencentdb only in Hermes default/chiefstaff/memory-lab and the OMP extension; Hermes clean has no memory provider. Unit state does not establish useful extraction, embeddings, all-host connectivity or fresh shared-continuity acceptance.

- https://github.com/TencentCloud/TencentDB-Agent-Memory/blob/main/README.md
- /mnt/zer0models/z0-wt/wiring/ops/tencentdb/README.md
- /home/kvn/.config/systemd/user/tencentdb-memory.service
- systemctl --user show tencentdb-memory.service --property=Id,ActiveState,SubState,UnitFileState,FragmentPath (2026-10-22)
- /mnt/zer0models/workspace/zer0/data/operations/capability-matrix/20261022.md

## `z0-memory-readonly`

### Declarative bindings

```json
{
  "harnesses": [
    "hermes",
    "claude",
    "codex",
    "omp"
  ],
  "mcp": {
    "command": "${Z0_MEMORY_MCP_BIN}",
    "args": []
  }
}
```

## `z0bridge`

### Declarative bindings

```json
{
  "harnesses": [
    "hermes"
  ]
}
```

### Observation (2026-10-22, source-only)

README documents the Hermes ACP adapter and identity/pairing service. Other harness adapters are future work. Identity-only deployment and a NOOP consumer do not prove migration of every application; this entry does not assert a currently running service.

- https://github.com/kvnloo/z0bridge/blob/99f513b2f3de1c9b6ce5da29de137281497488e2/README.md
- https://github.com/kvnloo/z0bridge/issues/3
- https://github.com/kvnloo/z0bridge/pull/2#issuecomment-6310221595

## `z0intelligence`

### Declarative bindings

```json
{
  "harnesses": [
    "hermes",
    "claude",
    "codex"
  ],
  "hermes": {
    "mcp": {
      "command": "${Z0INT_PYTHON}",
      "args": [
        "-m",
        "z0int.intelligence_mcp"
      ],
      "env": {
        "Z0INT_HARNESS": "hermes",
        "Z0INT_SHARED_ONLY": "1"
      }
    }
  },
  "claude": {
    "mcp": {
      "command": "${Z0INT_PYTHON}",
      "args": [
        "-m",
        "z0int.intelligence_mcp"
      ],
      "env": {
        "Z0INT_HARNESS": "claude-code",
        "Z0INT_SHARED_ONLY": "1"
      }
    }
  },
  "codex": {
    "mcp": {
      "command": "${Z0INT_PYTHON}",
      "args": [
        "-m",
        "z0int.intelligence_mcp"
      ],
      "env": {
        "Z0INT_HARNESS": "codex",
        "Z0INT_SHARED_ONLY": "1"
      }
    }
  }
}
```

## `z0live`

### Declarative bindings

```json
{
  "harnesses": [
    "hermes",
    "omp"
  ]
}
```

### Observation (2026-10-22, source-only)

README documents portable actor/harness integration and a desktop phone broker. This entry does not establish a running host service or physical phone/audio acceptance; OMP /live product parity remains a separate gate.

- https://github.com/kvnloo/z0live/blob/e1b485c40a11ab67b52b0aaf43362ac40d756fab/README.md
- https://github.com/kvnloo/z0live/issues/32

_Generated from `registry/components.yaml`. Do not edit by hand._
