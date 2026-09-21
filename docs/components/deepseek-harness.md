---
id: upstreams.deepseek-harness
title: DeepSeek Harness
scope: [deepseek-harness]
status: generated
---

# DeepSeek Harness

**This is an upstream system, not a Zer0 component.** It is not installable
and appears in no profile.

**Repo:** `kvnloo/deepseek-harness`  
**Upstream:** `deepseek-ai/deepseek-harness`  
**Kind:** harness  
**Fork:** yes  
**Relationship:** `executes_via`

Plugin-oriented execution harness: models, tools, sessions, sandboxes and UI are all plugins. Zer0 integrates through its adapter/plugin seams rather than making a Zer0-specific fork its architectural centre.

## Owns

- DSH execution
- provider adapters
- llm-pi-ai provider/model catalog authority

## Explicitly does not own

- Zer0 routing
- quota allocation
- measurement semantics

## Note

Absent from the previous registry entirely, despite being a primary execution surface. Its llm-pi-ai catalog is the authority for provider and model identity — z0 must consume it, not mirror it.

> The upstream head is a **live** fact. Run `./z0 registry doctor` to see it;
> it is deliberately not stored in the repository.

_Generated from `registry/upstreams.yaml`. Do not edit by hand._
