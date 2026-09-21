# Evaluation plane

JEV is the seed semantic observer for Zer0 evaluations. It is **not** ground truth, a security authority, or automatically the runtime policy.

## Two planes

```text
Execution plane

AODL / user intent
        |
        v
harness / controller
        |
        v
rules + independently promoted specialists + model backends
        |
        v
tools -> artifacts -> verifier -> outcome
```

```text
Evaluation plane

immutable / replayable events
        |
        +--> objective counters -------- Tokenomics
        |
        +--> semantic readings --------- z0intelligence DecisionBackend
        |
        +--> verifier / future outcomes
        |
        v
joined evaluation receipt
        |
        v
Evolution Lab
(grouped splits, comparison, calibration, Pareto analysis, promotion)
        |
        v
credited specialist may enter the execution plane
```

The important boundary is that **observation is not authority**.

## What JEV supplies

JEV can cheaply annotate replayed or live state with typed semantic readings such as:

- workflow phase and progress state;
- remaining substantive work;
- verification-needed / blocked / recovery-needed;
- bounded action or model-route preferences;
- complete probability distributions and confidence where the backend exposes them.

Those readings are useful features and weak labels. They are not proof that an action was correct.

NanoJev, OpenJev, rules, ridge/logistic models, mushroom-body learners, fly-style temporal models and other backends should implement or adapt to the same z0intelligence observer/DecisionBackend contract so they can be compared on identical states and questions.

## Where truth comes from

Evaluation should progressively anchor observer readings to evidence that does not depend on the observer:

- tests, CI, artifact verification and explicit verifier results;
- future elapsed time, spend, tokens, retries and resource use;
- reproducible environment outcomes;
- human adjudication for genuinely ambiguous cases.

A NanoJev-to-JEV disagreement therefore means **disagreement**. It becomes a useful adjudication/evaluation case. It is not automatically a NanoJev failure.

## Split discipline

Do not randomly split individual events from the same work lineage across train and test.

Group related observations under at least:

```text
event -> trace -> attempt lineage -> work item -> task family -> environment/harness
```

Hold entire work items together. Harder generalization tests should hold out complete task families, harnesses or environments.

## Promotion

Evolution Lab owns the empirical promotion decision. Compare simple controls before more complex specialists:

```text
rules / counters
ridge or logistic model
small MLP
NanoJev / local semantic model
mushroom / fly specialist
other candidate backends
```

The simplest candidate that satisfies the frozen outcome, calibration, latency, cost and safety gates wins.

JEV teacher agreement may bootstrap weak supervision, but verified outcomes increasingly become the selection signal.

## Security

A semantic observer can flag suspicious state as defense in depth. It must not grant authority.

Destructive actions, credentials, payments, deployment and other privileged capabilities remain governed by deterministic policy, sandboxing, scoped credentials and explicit approval where required.

## Component ownership

| Component | Owns |
| --- | --- |
| z0intelligence | typed observer/question contract, DecisionBackend adapters, semantic readings, replay/evaluation receipts, specialist runtime interfaces |
| Evolution Lab | grouped experiment design, frozen splits, candidate comparison/calibration, Pareto analysis, promotion gates |
| Tokenomics | objective token/cost/latency/retry/resource counters and independently verified-outcome measurement semantics |
| frontier-kb | research evidence, observer failure modes, experiment rationale and kill criteria |
| AODL | portable intent/workflow/authority contract and optional observer context |
| Kerdoios | resource inventory and placement using calibrated forecasts/requirements where useful |
| harnesses | execution and replayable event emission |
| JEV / NanoJev / OpenJev / rules / fly / mushroom | candidate observer or bounded specialist implementations, never truth by identity |

## First experiment

The first cross-stack proof should reproduce a simple comparison on frozen historical traces:

1. objective counters only;
2. semantic observer readings only;
3. counters plus semantic observer readings.

Predict future/outcome-grounded quantities without leaking future information. Measure calibration and repeated-observer stability as well as top-line prediction quality.

This is the bridge from J1/J1.1 backend parity work to J2 outcome-grounded replay.
