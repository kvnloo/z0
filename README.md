# Zer0

**Personal AI infrastructure that makes frontier models do less.**

`kvnloo/z0` is the **map, installer, contract registry, and documentation source** for the Zer0 ecosystem. It is deliberately **not** a runtime or orchestrator.

```bash
git clone https://github.com/kvnloo/z0
cd z0
pip install -r requirements.txt   # PyYAML for the CLI
./z0 init --profile core
./z0 doctor
```

## I want…

| Goal | Start here |
|------|------------|
| A better coding agent | [OMP](docs/components/oh-my-pi.md) (`oh-my-pi`) |
| Lower token usage | [Tokenomics](docs/components/tokenomics.md) + RLM (in OMP) |
| Personal intelligence | [z0intelligence](docs/components/z0intelligence.md) |
| Predictive desktop UX | [Flow](docs/components/flow.md) + Handsfree (in OMP) |
| Cheaper compute routing | [Kerdoios](docs/components/kerdoios.md) |
| Automatic AI research | [Evolution Lab](docs/components/evolution-lab.md) |
| Typed agent plans | [AODL](docs/components/aodl.md) |
| Agent observability | [AgentTrace](docs/components/agenttrace.md) |
| Everything stable | `./z0 init --profile full` |

## Profiles

| Profile | Components | For |
|---------|------------|-----|
| `minimal` | OMP | "I want the agent" |
| `core` | OMP + Tokenomics | normal Zer0 user |
| `personal` | core + z0int | personalization |
| `desktop` | core + Flow | daily Handsfree workflow |
| `compute` | core + Kerdoios | model/provider optimization |
| `research` | z0int + Evolution Lab + frontier-kb | AI research |
| `full` | all stable/canary | power users |

```bash
./z0 init --profile core
./z0 add tokenomics
./z0 add flow
```

## CLI

| Command | Purpose |
|---------|---------|
| `./z0 init` | Interactive or `--profile` install plan + clone |
| `./z0 add <id>` | Add one component |
| `./z0 doctor` | What's installed vs registry pins |
| `./z0 status` | Dev-state table (branch, HEAD, maturity) |
| `./z0 graph` | Text dependency tree |
| `./z0 graph --mermaid` | Mermaid for docs |
| `./z0 docs generate` | Regenerate `generated/` from registry |

## Rule

> **Implementation docs live with implementations. Architecture and onboarding live in `z0`.**

See [ARCHITECTURE.md](ARCHITECTURE.md), [AGENTS.md](AGENTS.md), and [docs/getting-started/five-minute-start.md](docs/getting-started/five-minute-start.md).
