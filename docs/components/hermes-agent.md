---
id: upstreams.hermes-agent
title: Hermes Agent
scope: [hermes-agent]
status: generated
---

# Hermes Agent

**This is an upstream system, not a Zer0 component.** It is not installable
and appears in no profile.

**Repo:** `NousResearch/hermes-agent`  
**Upstream:** `NousResearch/hermes-agent`  
**Kind:** harness  
**Fork:** no  
**Relationship:** `executes_via`

Upstream harness. Several Zer0 systems ship as Hermes plugins (Kerdoios today; hermes-jev-skills, hermes-keel), which is an implementation detail of those components, not of the harness abstraction.

## Owns

- Hermes agent runtime

## Explicitly does not own

- Zer0 routing policy
- harness catalog

> The upstream head is a **live** fact. Run `./z0 registry doctor` to see it;
> it is deliberately not stored in the repository.

_Generated from `registry/upstreams.yaml`. Do not edit by hand._
