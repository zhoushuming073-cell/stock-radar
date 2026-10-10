# Stock Radar — Quant + Vision cascade research idea

> **Date:** 2026-10-10  
> **Status:** RESEARCH DIRECTION NOTE — not an implementation or training authorization  
> **Scope:** Records a candidate architecture for future Quant + Vision / Vision-only research without changing current frozen strategy versions or active execution tasks.

## Why record this now

Recent Quant experiments show a useful failure mode: a hand-written structure definition can become too restrictive before the strategy ever reaches the execution layer. Q2 v1.2 is an example of why Quant and Vision should not be forced to do the same job.

The project should therefore separate three questions:

1. **Universe / admissibility:** is the security liquid, sufficiently elastic, and data-valid?
2. **Shape retrieval:** does the past-only chart resemble the setup we want?
3. **Entry readiness / ranking:** as of T close, is price in a favorable location and is the setup ready enough to rank highly?

The shape detector and the entry-timing layer should remain distinguishable.

## Route A — Quant coarse filter → Vision fine selection

```text
Broad market
→ permissive Quant admissibility / coarse shape filter
→ Vision shape classifier or ranker
→ causal T-close price-position / readiness score
→ final ranking
→ T+1 earliest hypothetical entry
```

Recommended Quant role:
- data quality and common-stock scope;
- liquidity / Beta / volatility / other market-state gates;
- broad, high-recall shape hints;
- current price location / extension / downside-state features.

Recommended Vision role:
- judge repeated visual structure that is awkward to encode with rigid pivots;
- distinguish clean ranges/channels from monotonic declines, one-off moves and noisy pseudo-patterns;
- rank ambiguous boundary cases rather than requiring every geometric sub-condition to PASS.

**Key design rule:** the Quant stage should be deliberately permissive. It should not recreate Q2 v1.2-style hard geometric consensus and then ask Vision to inspect the one surviving chart. Vision only adds value if the upstream gate preserves recall.

## Route B — Vision shape retrieval → Quant scoring / price-position assessment

```text
Broad liquid / tradable universe
→ Vision-only past-chart retrieval
→ Quant market-state + risk score
→ T-close price-position / readiness assessment
→ final ranking
→ T+1 earliest hypothetical entry
```

This route is especially useful if learned visual representations capture irregular high-beta ranges better than explicit channel rules.

The downstream Quant layer can evaluate:
- SPY / QQQ Beta and recent realized volatility;
- ADV / liquidity;
- relative strength / relative weakness;
- position inside an estimated range or distance from recent support;
- pullback depth and extension risk;
- whether the latest completed session still looks like continuous downside acceleration;
- other strictly causal T-close state variables.

Vision says **this looks like the setup**; Quant says **this setup is or is not currently in a favorable state**.

## Route C — independent Quant and Vision scores → late fusion

```text
Quant score ─────┐
                 ├─ calibrated fusion / rank model
Vision score ────┘
        +
T-close readiness / price-position features
```

Do not require one branch to hard-PASS before the other branch is observed.

Possible simple fusion baselines:
- weighted rank average;
- logistic / linear calibration;
- tree / boosting model over Quant score, Vision score and readiness features.

The purpose is to measure **incremental information** across Quant only, Vision only, Quant→Vision cascade, Vision→Quant cascade and late fusion. A more complex fusion model is justified only if it beats simpler baselines under the same data / split / execution contract.

## Separate setup quality from entry readiness

A chart can have a good multi-week or multi-month structure while still be in active decline today. Conversely, a short-term bounce does not make a poor long-horizon structure attractive.

Future models should expose at least two distinct outputs:

1. **Shape / setup score** — repeated range/channel quality or visual similarity, using past-only information.
2. **T-close readiness / position score** — location, extension/breakdown risk and stabilization/early-turn evidence through the latest completed session.

The final rank can combine them, but the two components should remain auditable.

## Causal boundary

- visual and numerical inputs end at **T close**;
- no T+1 or later bar, label, scaling or metadata may affect inference;
- earliest hypothetical fill remains **T+1 tradable open** unless a later experiment explicitly registers another execution rule;
- H_review and Y_future remain supervision / diagnostics, not live inputs.

## Suggested research sequence

When Quant + Vision work is explicitly authorized:

1. Start with **Route A** because current Quant, SVG/raster and review infrastructure already exist.
2. Make the Quant front end high-recall and measure candidate survival before training.
3. Train/evaluate a simple Vision baseline on shape quality, not portfolio-return optimization.
4. Add the separate T-close readiness layer.
5. Compare against Quant-only and Vision-only baselines.
6. Then test **Route B** to see whether Vision can replace brittle hand-coded geometry.
7. Only after both branches have useful independent signal, test late fusion.

## Research stop rules

Do not keep adding infrastructure merely because a strategy fails. Before deeper model work, require a non-degenerate candidate funnel, enough independent examples to evaluate, incremental Vision discrimination rather than Quant duplication, causal timing features, and validation under the same execution assumptions.

If a route remains sparse or non-incremental after one clearly registered iteration, archive it rather than indefinitely repairing it.

## Current status

This note **does not start model training** and does not change the three top-level families in the Research Master Guide: Quant-only, Quant + Vision, Vision-only. It records two concrete cascade directions plus a late-fusion control for future authorization. Existing Q1, Q2 v1.1/v1.2, Vision infrastructure and historical evidence remain unchanged.
