# Delegated catalog sources

Where a fact Zer0 appears to need already has a stronger owner, z0 records
the relationship, the discovery mechanism and the cache policy — never the
facts. A cached snapshot is never fresher than its source.

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

## `vllm` — vLLM
- **Kind:** model_server
- **Authority:** vLLM model registry / runtime API
- **Cache policy:** `derived` (ttl 1h)
- **Discovers:** currently served models, supported architectures
- **Owns:** inference engine, model architecture support
- **Does not own:** Zer0 routing policy, verified outcome
- **Consumed by:** kerdoios

_Generated from `registry/sources.yaml`. Do not edit by hand._
