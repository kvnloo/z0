# Onboarding matrix

| Component | Gate | Auto target | Tools | Steps | C1 bundles | C2 / asks | Services |
|-----------|------|-------------|-------|-------|------------|-----------|----------|
| `agenttrace` | generic |  | git, python>=3.10 | 4 | - | - | - |
| `aodl` | generic |  | git, python>=3.10 | 4 | - | - | - |
| `dash` | dash | yes | bun>=1.4.3, git, python>=3.10 | 19 | services | 1 | dash-bridge.service (tailnet_ipv4:4747) |
| `evolution-lab` | generic |  | git, python>=3.10 | 4 | - | - | - |
| `flow` | generic |  | git, python>=3.10 | 3 | - | 1 | - |
| `frontier-kb` | generic |  | git | 2 | - | - | - |
| `kerdoios` | generic |  | git, python>=3.10 | 4 | - | - | - |
| `memento` | generic |  | - | 0 | - | - | - |
| `oh-my-pi` | generic | yes | bun>=1.4.3, git | 5 | harness | - | - |
| `tokenomics` | generic | yes | git, python>=3.10, node>=20, npm | 5 | - | - | - |
| `z0evals` | generic | yes | git, python>=3.10 | 26 | - | 3 | - |
| `z0intelligence` | z0int | yes | git, python-window | 18 | harness, models, services | 2 | z0intelligence.service (loopback:11501) |

## Legacy projection (R-sync)

`install.command` / `verify.command` are the shell projection of the steps marked `legacy_projection: true`; `scripts/registry-check` fails when they drift.

- `agenttrace`: install `pip install -e .`; verify `-`
- `aodl`: install `pip install -e .`; verify `-`
- `dash`: install `bun install --frozen-lockfile && bun scripts/install-public-ci.ts && bun install --frozen-lockfile --cwd bridge`; verify `bun run typecheck && bun run lint && bun run test`
- `evolution-lab`: install `pip install -e .`; verify `-`
- `flow`: install `-`; verify `python3 scripts/workspace_flow.py --help`
- `kerdoios`: install `pip install -e .`; verify `-`
- `oh-my-pi`: install `bun install && bun run build`; verify `bun test packages/coding-agent/test/rlm-tokenomics-bridge.test.ts`
- `tokenomics`: install `pip install -e packages/python && npm install -w packages/typescript`; verify `tokenomics report --range today`
- `z0evals`: install `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`; verify `.venv/bin/python scripts/validate.py`
- `z0intelligence`: install `pip install -e .`; verify `python3 -m z0int --help`

_Generated from `registry/components.yaml` `onboard:` blocks. Do not edit by hand._
