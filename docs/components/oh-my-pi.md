---
id: upstreams.oh-my-pi
title: OMP (Oh My Pi)
scope: [oh-my-pi]
status: generated
---

# OMP (Oh My Pi)

**This is an upstream system, not a Zer0 component.** It is not installable
and appears in no profile.

**Repo:** `kvnloo/oh-my-pi`  
**Upstream:** `<fork>`  
**Kind:** harness  
**Fork:** yes  
**Relationship:** `executes_via`

Coding-agent runtime. Zer0 executes through it, and the RLM context extension lineage lives on its branches. It is one harness among peers, never a mandatory architectural root.

## Owns

- coding agent runtime

## Explicitly does not own

- Zer0 routing policy
- Zer0 measurement semantics
- harness catalog

## Note

The earlier registry pinned this fork to d707478 on rfc/interactive-performance-stack, which is the head of OPEN PR #77 — an unmerged fork branch presented as architecture truth.

> The upstream head is a **live** fact. Run `./z0 registry doctor` to see it;
> it is deliberately not stored in the repository.

_Generated from `registry/upstreams.yaml`. Do not edit by hand._
