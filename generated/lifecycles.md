# Lifecycle registry

## `architecture-truth` — Zer0 architecture truth classes
- **Kind:** epistemic
- **Stages:** `declared` → `implemented` → `observed` → `historical` → `derived`
- **Rule:** Lower-authority observations may expose drift but never silently overwrite declared architecture.

## `evolution-lab-promotion` — Evolution Lab candidate promotion
- **Kind:** experiment
- **Stages:** `sanity` → `replay` → `shadow` → `promoted`
- **Rule:** Experiment genomes are eliminated cheaply and promoted only after measured replay/verifier evidence; preview/nightly branches carry rolling candidates.

## `verified-oss-rolling` — Verified OSS rolling promotion
- **Kind:** promotion
- **Stages:** `candidate` → `preview` → `nightly` → `dev` → `main`
- **Rule:** Evidence-gated work moves through increasingly authoritative surfaces; workers do not merge main.

_Generated from `registry/lifecycles.yaml`._
