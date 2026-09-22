# Delegated catalog sources

Where a fact Zer0 appears to need already has a stronger owner, z0 records
the relationship, the discovery mechanism and the cache policy — never the
facts. A cached snapshot is never fresher than its source.

## `cerebras` — Cerebras
- **Kind:** provider_catalog
- **Authority:** Cerebras Cloud API /v1/models
- **Cache policy:** `derived` (ttl 24h)
- **Discovers:** served model ids, context window, rate-limit headers
- **Owns:** served model inventory, per-model rate limits
- **Does not own:** Zer0 model selection, quota accounting, placement
- **Consumed by:** kerdoios, z0intelligence
- **Note:** Same contract as Groq. Note that rate-limit dimensions are not always self-consistent (a `remaining` value has been observed exceeding its own `limit`), so a consumer must not treat a single dimension as authoritative.

## `groq` — Groq
- **Kind:** provider_catalog
- **Authority:** Groq API /openai/v1/models
- **Cache policy:** `derived` (ttl 24h)
- **Discovers:** served model ids, context window, model capability limits
- **Owns:** served model inventory, per-model rate limits
- **Does not own:** Zer0 model selection, quota accounting, placement
- **Consumed by:** kerdoios, z0intelligence
- **Note:** Reachable and authenticated when a key is present. Provider-side rate limits (requests/day, tokens/day) are discovered, never assumed: they are per-account facts, so they must be read from the API rather than hardcoded.

## `huggingface` — Hugging Face Hub
- **Kind:** model_hub
- **Authority:** huggingface.co API
- **Cache policy:** `derived` (ttl 24h)
- **Discovers:** model identity and config, model files and revisions, licence and gating metadata
- **Owns:** model identity, model files, model metadata
- **Does not own:** Zer0 model selection policy, residency policy
- **Consumed by:** z0intelligence
- **Note:** z0intelligence may pin a small intentional model set: selection + revision + role + residency ARE Zer0-owned facts. Architecture family and file metadata are not.

## `litellm` — LiteLLM
- **Kind:** provider_metadata
- **Authority:** BerriAI/litellm
- **Cache policy:** `derived` (ttl 24h)
- **Discovers:** provider and model metadata, model cost tables
- **Owns:** provider/model cost metadata
- **Does not own:** Zer0 placement, Zer0 spend policy
- **Consumed by:** kerdoios
- **Note:** Kerdoios consumes this. Kerdoios is explicitly NOT another gateway, and must not grow a parallel cost table.

## `nous` — Nous Portal
- **Kind:** provider_catalog
- **Authority:** Nous Portal API
- **Cache policy:** `derived` (ttl 24h)
- **Discovers:** served model ids, account entitlement state
- **Owns:** served model inventory, account entitlement
- **Does not own:** Zer0 model selection, quota accounting, placement
- **Consumed by:** kerdoios
- **Note:** Catalog reachable; credentials currently require re-login, so availability is `unavailable` until a usable credential exists. A reachable catalog is not an available provider.

## `ollama` — Ollama
- **Kind:** model_server
- **Authority:** local Ollama HTTP API
- **Cache policy:** `runtime`
- **Discovers:** installed models, model details
- **Owns:** local model installation state
- **Does not own:** Zer0 placement policy
- **Consumed by:** kerdoios, z0intelligence
- **Note:** Local runtime state is discovered on the machine, never committed.

## `openrouter` — OpenRouter
- **Kind:** provider_inventory
- **Authority:** openrouter.ai models API
- **Cache policy:** `live_only`
- **Discovers:** live provider inventory, live pricing, free-tier availability
- **Owns:** live provider inventory
- **Does not own:** Zer0 quota accounting
- **Consumed by:** kerdoios
- **Note:** Discover live. An offline snapshot is admissible only as a provenance-stamped fallback cache, never as the primary fact.

## `opentelemetry` — OpenTelemetry
- **Kind:** telemetry_transport
- **Authority:** OTel specification and SDKs
- **Cache policy:** `none`
- **Discovers:** telemetry transport, span/trace wire format
- **Owns:** telemetry transport
- **Does not own:** Zer0 measurement semantics, verified outcome
- **Consumed by:** tokenomics
- **Note:** OTel remains the TRANSPORT. Tokenomics owns Zer0-specific semantics and must not reimplement OTel.

## `vercel` — Vercel AI Gateway
- **Kind:** provider_catalog
- **Authority:** Vercel AI Gateway /v1/models
- **Cache policy:** `derived` (ttl 24h)
- **Discovers:** served model ids, gateway routing metadata
- **Owns:** served model inventory
- **Does not own:** Zer0 model selection, quota accounting, placement
- **Consumed by:** kerdoios
- **Note:** Account-wide 403 ("requires a valid credit card on file"). A gateway model listed as "zero-cost metadata" is NOT thereby available; a catalog name cannot confer availability.

## `vllm` — vLLM
- **Kind:** model_server
- **Authority:** vLLM model registry / runtime API
- **Cache policy:** `derived` (ttl 1h)
- **Discovers:** currently served models, supported architectures
- **Owns:** inference engine, model architecture support
- **Does not own:** Zer0 routing policy, verified outcome
- **Consumed by:** kerdoios

## `xai` — xAI
- **Kind:** provider_catalog
- **Authority:** xAI API /v1/models
- **Cache policy:** `derived` (ttl 24h)
- **Discovers:** served model ids
- **Owns:** served model inventory
- **Does not own:** Zer0 model selection, quota accounting, placement
- **Consumed by:** kerdoios
- **Note:** Credential requires re-login; availability is `unavailable`. Any use must be economically justified against the free providers first.

_Generated from `registry/sources.yaml`. Do not edit by hand._
