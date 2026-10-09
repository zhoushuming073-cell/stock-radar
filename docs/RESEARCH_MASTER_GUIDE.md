# Stock Radar — Research Master Guide

> **Date:** 2026-10-09  
> **Status:** **ACTIVE MASTER RESEARCH GUIDE**  
> **Scope:** This file defines the current research taxonomy, comparison rules and stage gates. It replaces the earlier habit of treating v1/v2/v3, Vision-H, Vision-Y, Sequence and Fusion as separate top-level roadmaps.  
> **Status authority:** completion / blockers remain owned by the canonical project ledger: [reports/journey-2026-09-30-0651-📌当前总账.md](../reports/journey-2026-09-30-0651-📌当前总账.md).

## 0. Current reality

Stock Radar is **still in research infrastructure + method-definition stage**.

What exists today:
- frozen/reusable Research Infrastructure v1;
- historical PIT / identity / price-trust engineering with known gaps;
- local LEAN execution plumbing and old smoke / exploratory runs;
- reproducible Quant candidate-generation components;
- secure SVG / blind-human / future-review labeling infrastructure;
- objective future-outcome generation infrastructure.

What does **not** exist today:
- no completed head-to-head study of the three research paths below;
- no trained production-quality Vision model;
- no validated Quant+Vision fusion model;
- no frozen new strategy with credible fresh OOS evidence;
- no formal new-strategy backtest proving alpha;
- no QC / LEAN execution result that establishes the new research paths are profitable.

Older 245-session / 96-trade LEAN runs, Scanner forward statistics, Strategy 2 experiments and visual engineering acceptances are **engineering / exploratory evidence only**. They are not the final backtest of the current research program.

## 1. Only three top-level research paths

From now on, every new model or experiment must belong to exactly one of these three families.

```text
                         Stock Radar Research
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
        A. Quant-only       B. Quant + Vision     C. Vision-only
              │                   │                   │
        Q1 fuzzy shape       ML fusion / DL        ML visual / DL
        Q2 parallel channel  fusion                visual
        Q3 later ensemble
```

Human labels, future outcomes, Train/Validation/Test/Fresh, LEAN/QC and GPT/news review are **not additional top-level paths**. They are supervision, validation or downstream layers shared by the three paths.

---

# A. Quant-only

## A1. Q1 — Fuzzy Shape Quant

**Current status:** implemented as the Quant candidate generator used by the accepted v3 labeling infrastructure; **predictive efficacy not validated**.

Version:
- `fuzzy-shape-v1`
- config: `config/quant_vision_labeling_v1.yaml`
- implementation and tests are already in current `main`.

Research idea:

> prior strength → pullback → downside exhaustion → OHLCV support/absorption proxies → early turn-up → avoid excessive extension.

The A–F dimensions are:
- A: prior strength;
- B: pullback;
- C: downside exhaustion;
- D: OHLCV support/absorption **proxies**;
- E: early strengthening;
- F: current extension / entry-position risk.

Purpose:
- generate a broad, interpretable candidate domain;
- provide structured Quant features;
- become a Quant-only baseline and one possible input branch for Fusion.

Not yet proven:
- market-wide recall;
- stable future return lift;
- optimal weights / knots;
- OOS profitability.

## A2. Q2 — Parallel Channel Quant

**Current status:** experimental source-only Draft PR [#10](https://github.com/zhoushuming073-cell/stock-radar/pull/10); **not merged / not locally accepted on the full real market**.

Research idea:

> monthly/weekly horizontal-to-slowly-rising channel → repeated lower/upper-bound tests and alternation → not a monotonic decline → current daily price returns toward the lower region → wait for stabilization / early reversal.

This is intentionally different from Q1:
- Q1 looks for a strong-stock pullback / recovery structure.
- Q2 looks for repeated long-horizon range/channel structure and lower-band location.
- Neither should be forced to replace the other.

Before merge / formal use, Q2 requires:
- real-market local scan;
- human shape inspection;
- correction/review of coordinate consistency and lower-band breach handling;
- robust daily pivot / impulse-pullback definition;
- multi-window stability / consensus checks;
- historical PIT universe path for backtests rather than current-active symbols only;
- full project regression.

## A3. Q3 — Quant ensemble / ML on Quant features

**Future subfamily, not a separate top-level path.**

Once Q1 and Q2 are individually stable, compare:
- Q1 only;
- Q2 only;
- simple rule/score combination;
- classical ML over Quant features (e.g. logistic / tree / boosting models).

Do not combine Q1 and Q2 prematurely. Their complementarity must be measured.

---

# B. Quant + Vision

The Fusion family asks:

> Does visual structure provide information **beyond** the explicit Quant state?

This is likely the most important final research family, but it should not be assumed to win.

## B1. Classical Machine Learning Fusion

Examples:
- Q1/Q2 features + deterministic visual geometry / handcrafted visual descriptors;
- logistic regression, linear/rank models, tree ensembles, gradient boosting, SVM where appropriate.

Purpose:
- establish a cheaper, interpretable Fusion baseline;
- test whether visual descriptors add incremental information without deep networks.

## B2. Deep Learning Fusion

Candidate design:

```text
Quant feature branch ───────┐
                            ├─ fusion head → ranking / probabilities
Vision encoder branch ──────┘
```

Possible visual encoder inputs:
- deterministic rasterization of **past-only** SVG;
- separately versioned vector-geometry representation.

The model must never receive future-right SVG, H_review, future-derived scaling or future metadata as inference input.

Fusion is retained only if it beats the best valid single-family baseline under the same universe / split / outcome / cost contract.

---

# C. Vision-only

Vision-only asks:

> If the model receives no Q1/Q2 score or engineered Quant state, can chart structure alone learn useful and generalizable information?

The visual input is always past-only through T.

## C1. Classical Machine Learning Vision

Possible inputs:
- candle / wick / volume geometry summaries;
- contour / shape / local visual descriptors;
- deterministic embeddings that do not use Q1/Q2 factors.

Possible learners:
- logistic / linear ranking;
- SVM;
- tree / boosting models.

This is a baseline for testing whether visual representation has value without deep learning.

## C2. Deep Learning Vision

Candidate inputs:
- left-only deterministic SVG rasterization → CNN / ResNet-class model;
- later, if justified, lightweight ViT;
- optionally a deliberately designed vector-geometry neural model.

Important:
- raw SVG XML is not automatically a conventional CNN image input;
- rendering / rasterization must be deterministic and versioned;
- visual DL must be compared with cheaper alternatives before more complex architectures are justified.

---

# 2. Supervision is an orthogonal axis, not a research path

The project has three different label concepts.

## H_blind — human decision signal

Before future reveal:
- Observe;
- Entry readiness;
- confidence;
- optional reasons.

Use:
- learn the researcher's discretionary visual/entry judgment;
- measure consistency;
- provide one supervisory signal for Vision or Fusion.

It does **not** equal future profitability.

## H_review — retrospective explanation

After future reveal:
- post-hoc review / error attribution;
- timing-vs-setup discussion;
- optional explanatory labels.

Use:
- diagnostics / error analysis / active-learning research.

It contains hindsight and must **not** be treated as a real-time label or input.

## Y_future — objective market outcome

Programmatically generated after T:
- future returns;
- MFE / MAE;
- target-before-adverse events;
- gaps / ambiguity / censored / missing states.

Use:
- objective training target where explicitly chosen;
- common economic evaluation target across paths.

H and Y remain separate.

Thus future experiments can be named, for example:
- Vision-H;
- Vision-Y;
- Quant+Vision-H;
- Quant+Vision-Y;
- later, explicitly authorized multi-task H+Y.

These are **supervision variants inside B/C**, not additional research paths.

---

# 3. Mandatory control baselines

Some models are useful scientifically but are not new top-level paths.

## Numeric OHLCV sequence baseline

A 1D CNN / TCN or other small sequence model may read normalized past OHLCV directly.

Purpose:
- test whether chart rendering adds value over raw numerical time structure;
- prevent the project from assuming Vision is superior because humans like charts.

Classification:
- **control baseline**, not a fourth research path.

## Simple Quant / statistical baselines

Examples:
- simple momentum / reversal;
- candidate-domain base rate;
- logistic / LightGBM over explicit causal Quant features.

Purpose:
- determine whether complex ML/DL is actually necessary.

---

# 4. Shared infrastructure layer

All three paths must use the same research foundations where applicable.

## Data / causal contracts
- Research Infrastructure v1 is frozen and reusable.
- historical identity / delisting / corporate-action coverage remains incomplete and must be reported;
- no future information in T-time inputs;
- no current-survivor-only historical claim.

## Visual contracts
The accepted v3 dual-stage system is now classified as **shared Vision/Human/Y research infrastructure**, not the sole active research roadmap.

Reusable components:
- X_left_num;
- X_left_svg;
- deterministic left-only rendering;
- H_blind;
- H_review;
- Y_future;
- secure future reveal.

Current state:
- engineering accepted;
- human-trial phase **paused by user**;
- no Vision training authorized merely because the UI exists.

Reference:
- [dual-stage plan / subsystem design](QUANT_VISION_DUAL_STAGE_RESEARCH_PLAN.md)
- [labeling guide](QUANT_VISION_DUAL_STAGE_LABELING_V3.md)
- [acceptance](../reports/acceptance/quant-vision-dual-stage-v3-acceptance-2026-10-09.md)

## Execution / validation infrastructure
LEAN / QC are validation machinery, not model families.

They answer:
- whether frozen signals can be executed consistently;
- costs / slippage / portfolio effects;
- company actions / fill assumptions;
- later independent validation.

They do not make a weak selector strong.

---

# 5. One common experiment contract

A fair comparison requires the same:
- decision time T;
- earliest executable reference (currently T+1 tradable open when used);
- eligible universe definition;
- Train / Validation / held-out time partitions;
- future outcome definition;
- fee / slippage assumptions;
- candidate count / ranking metric;
- missing / ambiguous treatment;
- issuer grouping / overlap controls.

A method is not allowed to claim superiority using an easier universe, different future window or more favorable execution definition.

Primary comparisons eventually become:

| ID | Family | Core input | Learning style |
| --- | --- | --- | --- |
| Q1 | Quant-only | fuzzy-shape features | explicit rules / scores |
| Q2 | Quant-only | parallel-channel features | explicit rules / scores |
| Q3 | Quant-only | Q1 + Q2 features | classical ML / ensemble |
| V1 | Vision-only | past-only visual descriptors | classical ML |
| V2 | Vision-only | past-only chart representation | deep learning |
| F1 | Quant + Vision | Q features + visual descriptors | classical ML |
| F2 | Quant + Vision | Q branch + visual encoder | deep learning |

Mandatory controls include simple rules, base rates and numeric sequence models.

---

# 6. Research stages

The project is currently around **Stage 0–1**, not the final backtest stage.

## Stage 0 — Research infrastructure
Status: **substantially built / still imperfect**.

Includes:
- market data;
- PIT/identity trust layers;
- Train/Validation/Test/Fresh contracts;
- reproducible numerical / SVG inputs;
- labels/outcomes;
- LEAN adapter;
- audit / hashing.

## Stage 1 — Method definition and candidate quality
Status: **CURRENT**.

Goals:
- stabilize Q1;
- validate / repair Q2;
- inspect real candidates;
- define comparable features and common experiment dataset;
- do not optimize on Test/Fresh.

## Stage 2 — Baselines
Not yet complete.

Build:
- Quant-only Q1/Q2/Q3;
- simple statistical / LightGBM-type baselines;
- numeric sequence control;
- Vision classical-ML baseline.

## Stage 3 — ML / Deep Learning
Not started as a formal program.

Build only after Stage 1/2:
- Vision-H / Vision-Y;
- Quant+Vision classical ML;
- Quant+Vision DL;
- controlled ablations.

## Stage 4 — Freeze and historical evaluation
Not started.

Freeze:
- data version;
- candidate generation;
- model;
- target;
- metrics;
- execution assumptions.

Then run controlled held-out evaluation.

## Stage 5 — genuinely new OOS + LEAN/QC
Not started for these new methods.

Only here can the project begin discussing deployable evidence.

---

# 7. Current status of historical plans

Older files are retained because they contain useful contracts and research history, but they no longer define separate top-level routes.

| Document | New classification |
| --- | --- |
| `QUANT_VISION_FUSION_RESEARCH_PLAN.md` | historical v1 idea; contributed Human→Vision / Fusion concepts |
| `PRICE_STRUCTURE_OUTCOME_LEARNING_PLAN.md` | historical v2 idea; contributes objective-Y / sequence / fair-comparison methodology |
| `QUANT_VISION_DUAL_STAGE_RESEARCH_PLAN.md` | **shared Vision/Human/Y infrastructure specification**, engineering accepted; not sole master roadmap |
| `VISION_DEEP_LEARNING_RESEARCH_PLAN.md` | historical visual-research design / P0/P1 lineage |
| Strategy 2 docs/results | historical rule baseline / engineering reference; not current master path |
| PR #10 Parallel Channel | active experimental Quant research draft; not merged |

Do not delete or rewrite dated acceptance reports. Later decisions supersede roadmap status, not historical facts.

---

# 8. Immediate project posture

## Authorized Q1/Q2 implementation update · 2026-10-09

The explicit active work order supersedes the earlier statement below about waiting for authorization. Independent Q1 parity, hardened Q2, latest-session watchlist and the isolated fixed-horizon Native adapter are implemented on Draft PR #13. Release remains subject to actual local execution gates; source/fixture passes cannot replace a missing-price or identity/price-safety gate. The [dated acceptance](../reports/acceptance/q1-q2-quant-infrastructure-backtest-2026-10-09.md) controls actual results. Q2 Draft #10 remains open until an accepted replacement is merged. No changes to the three-family taxonomy, no model training and no Fresh/OOS efficacy claim.

As of this guide:
- **no model training is the default next action;**
- v3 human labeling trial is **paused**;
- PR #10 remains **Draft / experimental**;
- no formal backtest of Q1/Q2/Vision/Fusion is claimed;
- next implementation should be explicitly authorized after deciding which Stage-1 research item to tackle.

The project should prefer **clean comparisons over adding more branches**.

---

# 9. Final success criterion

The goal is not:
- “a CNN recognizes charts”;
- “a Quant formula finds pretty patterns”;
- “one historical equity curve looks good”.

The goal is:

> On the same causal market universe and future-evaluation contract, determine whether Quant-only, Vision-only or Quant+Vision produces stable incremental candidate quality in genuinely unseen periods, and retain only complexity that survives costs, data-quality checks and independent validation.

Until that evidence exists, Stock Radar remains a **research platform**, not a validated trading strategy.
