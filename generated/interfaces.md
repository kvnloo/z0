# Interface registry

## `agenttrace.span.v0`
- **Owner:** `agenttrace`
- **Summary:** Historical agent span for observability export.

## `aodl.intent.v1`
- **Owner:** `aodl`
- **Summary:** Typed intent / plan contract (not runtime execution).

## `cu.stage_intent.v0`
- **Owner:** `oh-my-pi`
- **Summary:** Handsfree / computer-use window and layout intent.

## `flow_prediction.v1`
- **Owner:** `flow`
- **Summary:** OS-context prediction with horizon metadata and gates.

## `kerdoios.route.v1`
- **Owner:** `kerdoios`
- **Summary:** Model/provider routing decision with cost estimate.

## `limitless.cron_job_spec.v0`
- **Owner:** `limitless`
- **Summary:** Keyword arguments for a Hermes host's cron.jobs.create_job, one per sending job (event poll, no-agent script, local delivery, window_class, stale_after_s), printed by bin/limitless-cron-spec; --check, --plan and --plan --cli compare against the host's job records and make no call.

## `limitless.state_card.v0`
- **Owner:** `limitless`
- **Summary:** Hermes pre_llm_call hook adding a short state card of coarse-label lines (digits masked by default).

## `limitless.tools.v0`
- **Owner:** `limitless`
- **Summary:** Hermes plugin tools listed under provides_tools in the plugin's plugin.yaml (limitless_status, limitless_state, limitless_window and the rest), each result an evidence envelope.

## `limitless.window_provider.v0`
- **Owner:** `limitless`
- **Summary:** Provider a Hermes host takes through ctx.register_window_provider; current(now) names the open cron window_class (peak, trough, anytime, wind_down) from events, or None (asleep, focus block, unknown) so windowed jobs hold.

## `omp.session.aggregate`
- **Owner:** `oh-my-pi`
- **Summary:** Session-level token rollup for Tokenomics reconciliation.

## `os.next_context.v0`
- **Owner:** `flow`
- **Summary:** Shadow prediction of next desktop context episode.

## `tokenomics.event.v0`
- **Owner:** `tokenomics`
- **Summary:** Vendor-neutral usage / cost / latency event envelope.

## `tokenomics.report.v1`
- **Owner:** `tokenomics`
- **Summary:** Aggregated savings, reconciliation, and coverage report.

## `z0int.context_resolve.v1`
- **Owner:** `z0intelligence`
- **Summary:** Provenance-preserving bounded context packet for source-backed retrieval and harness injection.

## `z0int.decision_receipt.v1`
- **Owner:** `z0intelligence`
- **Summary:** Structured decision receipt for routing and policy audit.

_Generated from `registry/interfaces.yaml`._
