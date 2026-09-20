# Ownership map

This page is generated from each component's `boundaries` entry in `registry/components.yaml`. If this page is wrong, fix the registry rather than this file.

| Component | Owns | Explicitly does not own |
|-----------|------|--------------------------|
| `agenttrace` | agent span history, TUI | live runtime, measurement kernel |
| `aodl` | typed intent/plan/observed contracts, fail-closed validation, harness ids | runtime implementation, scheduling, provider execution |
| `evolution-lab` | experiment search, autoresearch orchestration | production runtime, personal traces |
| `flow` | OS prediction, prepare, routine mining | agent runtime, token accounting, training loops |
| `frontier-kb` | research evidence, external references | private user traces, runtime code |
| `kerdoios` | resource inventory, hard filtering, quota/capacity, placement, execution portfolios | provider gateway execution, task scheduling, token measurement, agent runtime |
| `memento` | visual private history | research KB, agent runtime |
| `oh-my-pi` | coding agent runtime, voice/stage/CU, RLM spill, Jev hotpath | token measurement, routing policy store, research KB |
| `openjev` | local SLM decision heads | agent runtime, measurement |
| `tokenomics` | usage attribution, savings reports, reconciliation | routing policy, provider execution, agent runtime |
| `z0intelligence` | personal policy, routine promotion, specialists | coding agent runtime, OS prediction, measurement kernel |

## Rule

Every cross-repo fact should have one authoritative owner. Other repos may consume, reference, or observe that fact, but should not silently redefine it.

_Generated from `registry/components.yaml`. Do not edit by hand._
