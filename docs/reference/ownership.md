# Where does this belong?

| I need to change… | Owner component |
|-------------------|-----------------|
| Coding agent runtime | `oh-my-pi` |
| Realtime voice actor / floor / barge | `z0live` |
| Native Stage / computer use effects | `oh-my-pi` / harness plugins |
| Context spill / RLM | `oh-my-pi` |
| OS prediction / prepare | `flow` |
| Personal learned policy | `z0intelligence` |
| Routine promotion | `z0intelligence` |
| Token / cost measurement | `tokenomics` |
| Compute / provider allocation | `kerdoios` |
| Experiment search | `evolution-lab` |
| Research knowledge | `frontier-kb` |
| Typed intent / plan schema | `aodl` |
| Historical agent TUI | `agenttrace` |
| Device pairing / scoped session transport | `z0bridge` |
| Worker coordination / durable handoffs | `oss-factory` |
| Source-history retrieval | `agentsview` / `ctx` |
| Shared memory gateway | `tencentdb-memory` |
| Docs / notes retrieval | `qmd` |
| Batch graph-memory research | `graphrag` |
| Credential-gated memory candidate | `supermemory` |
| Future screen-recording recall sensor (not enabled) | `memento` |

## Do NOT put…

| Anti-pattern | Correct owner |
|--------------|---------------|
| Routing policy in Tokenomics | `kerdoios` / `z0intelligence` |
| Training logic in Flow | `evolution-lab` |
| Provider execution in Kerdoios | OMP / provider adapters |
| Runtime implementation in AODL | `oh-my-pi` |
| Private user traces in frontier-kb | `memento` / `z0intelligence` |
