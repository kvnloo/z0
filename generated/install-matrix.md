# Install matrix

Harnesses are chosen separately from capabilities and are never installed as
components.

| Profile | Capabilities | Harnesses (default first) |
|---------|--------------|---------------------------|
| `minimal` | execution | `hermes-agent`, `oh-my-pi`, `deepseek-harness` |
| `core` | execution, contracts, measurement | `hermes-agent`, `oh-my-pi`, `deepseek-harness` |
| `personal` | cognition | `hermes-agent`, `oh-my-pi`, `deepseek-harness` |
| `desktop` | context, interaction | `hermes-agent`, `oh-my-pi`, `deepseek-harness` |
| `compute` | resources | `hermes-agent`, `oh-my-pi`, `deepseek-harness` |
| `context` | context | `hermes-agent`, `oh-my-pi`, `deepseek-harness` |
| `research` | evaluation, research | `hermes-agent`, `oh-my-pi`, `deepseek-harness` |
| `full` | cognition, context, interaction, resources, evaluation, research, governance | `hermes-agent`, `oh-my-pi`, `deepseek-harness` |

## Owned components per profile

| Component | minimal | core | personal | desktop | compute | context | research | full |
|-----------|---|---|---|---|---|---|---|---|
| `aodl` |  | yes | yes | yes | yes | yes | yes | yes |
| `dash` |  |  |  | yes |  |  |  | yes |
| `evolution-lab` |  |  |  |  |  |  | yes | yes |
| `flow` |  |  |  | yes |  |  |  | yes |
| `frontier-kb` |  |  |  |  |  |  | yes | yes |
| `hermes-agent-cluster` |  |  |  |  |  |  |  |  |
| `hermes-jev-skills` |  |  |  |  |  |  |  | yes |
| `hermes-keel` |  |  |  |  |  |  |  | yes |
| `hermes-mesh-keel` |  |  |  |  |  |  |  |  |
| `kerdoios` |  |  |  |  | yes |  |  | yes |
| `kvnloo-skills` |  |  |  |  |  |  |  | yes |
| `ripple` |  |  |  | yes |  |  |  | yes |
| `rlm` |  |  |  |  |  | yes |  | yes |
| `sol-pi-hermes` |  |  |  |  |  | yes |  | yes |
| `sol-pi-omp` |  |  |  |  |  |  |  |  |
| `tokenomics` |  | yes | yes | yes | yes | yes | yes | yes |
| `verified-oss-loop` |  |  |  |  |  |  |  | yes |
| `z0` |  | yes | yes | yes | yes | yes | yes | yes |
| `z0archy` |  |  |  |  |  |  |  | yes |
| `z0evals` |  |  |  |  |  |  | yes | yes |
| `z0intelligence` |  |  | yes |  |  |  | yes | yes |

_Generated from `registry/profiles.yaml`._
