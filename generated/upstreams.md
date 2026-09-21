# Upstream systems

Not installable, not in any profile. A repository we contribute to is not
automatically supported infrastructure.

| ID | Name | Kind | Fork | Relationship | Upstream |
|----|------|------|------|--------------|----------|
| `NanoJev` | NanoJev | model | yes | reference_to | `<fork>` |
| `agenttrace` | AgentTrace | observability | yes | reference_to | `<fork>` |
| `deepseek-harness` | DeepSeek Harness | harness | yes | executes_via | `deepseek-ai/deepseek-harness` |
| `firstmate` | Firstmate | distro | yes | reference_to | `<fork>` |
| `hermes-agent` | Hermes Agent | harness | no | executes_via | `NousResearch/hermes-agent` |
| `jev-ultrafast` | Jev Ultrafast | model | yes | reference_to | `<fork>` |
| `laya` | Laya | model | yes | reference_to | `<fork>` |
| `laya-coreml` | Laya (Core ML) | model | yes | reference_to | `<fork>` |
| `laya-mlx` | Laya (MLX) | model | yes | reference_to | `<fork>` |
| `memento` | Memento | legacy | yes | reference_to | `<fork>` |
| `o8` | o8 | control_room | yes | reference_to | `<fork>` |
| `oh-my-pi` | OMP (Oh My Pi) | harness | yes | executes_via | `<fork>` |
| `sol-pi` | SoL-Pi | research | yes | reference_to | `NVlabs/SoL-Pi` |

## Reference-only and donor entries

Owned repositories that are **not** part of the network: product lines and
superseded aliases. Listed so the almanac accounts for every repository we
swept, without pretending they are supported infrastructure.

| ID | Name | Kind | Relationship | Repo |
|----|------|------|--------------|------|
| `blueprint` | Blueprint | product_line | reference_to | `kvnloo/blueprint` |
| `openjev` | OpenJev (alias) | superseded_alias | legacy_of | `kvnloo/openjev` |
| `solarpunk` | solarpunk | product_line | reference_to | `kvnloo/solarpunk` |

_Generated from `registry/upstreams.yaml`. Do not edit by hand._
