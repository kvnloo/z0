# Where does this belong?

| I need to change… | Owner component |
|-------------------|-----------------|
| Coding agent runtime | `oh-my-pi` |
| Voice / Stage / computer use | `oh-my-pi` |
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
| Visual private history | `memento` |

## Do NOT put…

| Anti-pattern | Correct owner |
|--------------|---------------|
| Routing policy in Tokenomics | `kerdoios` / `z0intelligence` |
| Training logic in Flow | `evolution-lab` |
| Provider execution in Kerdoios | OMP / provider adapters |
| Runtime implementation in AODL | `oh-my-pi` |
| Private user traces in frontier-kb | `memento` / `z0intelligence` |
