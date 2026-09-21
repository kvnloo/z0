# Ownership map

This page is generated from each component's `boundaries` entry in `registry/components.yaml`. If this page is wrong, fix the registry rather than this file.

| Component | Owns | Explicitly does not own |
|-----------|------|--------------------------|
| `agenttrace` | agent span history, TUI | live runtime, measurement kernel |
| `aodl` | typed intent/plan/observed contracts, fail-closed validation, harness ids | runtime implementation, scheduling, provider execution |
| `evolution-lab` | grouped evaluation design, experiment search, candidate comparison, calibration, promotion gates, autoresearch orchestration | semantic observer contract, production runtime, personal traces |
| `flow` | OS prediction, prepare, routine mining | agent runtime, token accounting, training loops |
| `frontier-kb` | research evidence, observer failure modes, experiment rationale, external references | private user traces, runtime code, eval ground truth |
| `kerdoios` | resource inventory, hard filtering, quota/capacity, placement, execution portfolios | provider gateway execution, task scheduling, token measurement, agent runtime |
| `memento` | visual private history | research KB, agent runtime |
| `oh-my-pi` | coding agent runtime, voice/stage/CU, RLM spill, judgment integration hooks | semantic observer truth, eval promotion, token measurement, routing policy store, research KB |
| `openjev` | legacy local SLM decision-head implementation | canonical observer contract, verified truth, security authority, eval promotion, agent runtime, measurement |
| `tokenomics` | objective counters, usage attribution, verified-outcome semantics, savings reports, reconciliation | semantic labeling, routing policy, provider execution, agent runtime |
| `z0intelligence` | typed observer and DecisionBackend contracts, semantic readings, replay/evaluation receipts, personal policy, specialist runtime interfaces, routines | verified ground truth, experiment promotion authority, coding agent runtime, OS prediction, measurement kernel |

## Rule

Every cross-repo fact should have one authoritative owner. Other repos may consume, reference, or observe that fact, but should not silently redefine it.

_Generated from `registry/components.yaml`. Do not edit by hand._
