# Box Structure Numeric Deep Learning — causal labeling and training-data pipeline v1

> **Date:** 2026-10-11  
> **Status:** ACTIVE USER-AUTHORIZED WORK ORDER  
> **Research scope:** multi-scale numeric time-series representation learning for historical box/range structure recognition  
> **Primary objective:** build a local, causal, high-throughput human-labeling and dataset-generation workflow for training numeric deep-learning models to recognize box/range structures from historical OHLCV sequences.  
> **Explicitly not an image-model project:** candlestick charts are human-facing annotation views only. Model inputs are numeric, past-only OHLCV tensors.

## 0. Repository entry protocol

Synchronize latest `main`, then read in this order:

1. `AGENTS.md`
2. `reports/journey-2026-09-30-0651-📌当前总账.md`
3. `docs/RESEARCH_MASTER_GUIDE.md`
4. `codex/tasks/ACTIVE.md`
5. this work order
6. `docs/RESEARCH_INFRASTRUCTURE_V1.md`
7. the reusable v3 labeling implementation under `src/radar/vision/dual_*`
8. historical Q1/Q2/Vision plans only when needed as design references; they do not override this task.

Preserve all frozen data, old acceptance evidence, old Q1/Q2 artifacts, and historical work orders. Do not rewrite old reports to make them appear consistent with this new direction.

## 1. Research question

The immediate research problem is **representation and recognition**, not profitability:

> Given only information available at historical decision time `T`, can a numeric deep-learning model learn to identify a persistent box/range structure, tolerate local microstructure noise or temporary undercuts, and estimate the current price's structural location within that range?

The first supervised target is human-defined **structure**, not future return.

This task must produce infrastructure that supports later experiments with:

- rule-based / handcrafted numeric baselines;
- classical machine learning on explicit causal descriptors;
- 1D CNN / TCN-style sequence encoders;
- multi-scale numeric sequence fusion;
- later outcome-supervised or Quant+DL experiments under a separate authorization.

Do **not** interpret this task as proof that box structures predict positive returns.

## 2. Non-negotiable modality decision

### 2.1 Model input

The learning system must consume **numeric OHLCV sequences**, not PNG/JPEG/SVG pixels.

Canonical model channels:

`Open, High, Low, Close, Volume`

The canonical source of truth remains the historical numerical series and its hashes.

### 2.2 Human annotation display

The local web UI should render deterministic candlestick views for human judgment:

- Daily
- Weekly
- Monthly

These visualizations are annotation aids only. They must never become the default training features for the numeric model.

No screenshot OCR, no raster-image classifier, no image-only CNN, and no future-derived visual scaling.

## 3. Causal information boundary

For every labeling task, define a historical **decision timestamp/date `T`**.

Hard invariant:

```text
all observations used for selection, resampling, rendering, tensor construction,
normalization, diagnostics, task metadata, and model input must satisfy date <= T
```

No T+1 or later row may influence:

- candidate inclusion;
- candidate score;
- daily/weekly/monthly bar construction;
- chart scaling;
- normalization statistics;
- labels presented to the human;
- tensor contents;
- train/validation assignment.

There is **no future reveal stage in Box Labeling v1**. Do not generate, preload, serialize, embed, or expose post-T returns/outcomes in the labeling bundle.

### 3.1 Weekly/monthly resampling semantics

Weekly and monthly bars must be constructed exclusively from source daily bars with `date <= T`.

If `T` lies inside an incomplete week or month, the final weekly/monthly bar is a **partial as-of-T bar**:

- Open = first observed session in that period;
- High = max through T;
- Low = min through T;
- Close = T/as-of-period last available close;
- Volume = sum through T.

Never complete the bar using later sessions.

A post-T mutation test must prove that modifying every source observation after T leaves:

- candidate decision;
- all three rendered views;
- all numeric tensors;
- hashes;
- human task payload

byte-for-byte or numerically identical as applicable.

## 4. Data backend and history provider

Use finalized **Research Infrastructure v1** / `shape_research_universe_v1(root)` as the default historical research source.

Do not modify its frozen semantics or mutate its databases.

The current frozen public window API is intentionally limited. Add the **smallest additive, read-only, host-owned past-only history capability** required for this task.

Target capability:

```python
history = provider.history(
    security_id=...,
    decision_date=T,
    max_sessions=430,
)
```

Requirements:

- strictly clipped at `T`;
- historical `security_id` preserved;
- uses Research Infrastructure v1 historical membership/trust semantics;
- explicit missing/unsafe-history status;
- deterministic ordering;
- no current-survivor fallback;
- no network access;
- no mutation of frozen stores;
- provenance/version/hash exposed;
- sufficient history for the configured daily/weekly/monthly views when available.

If an additive history provider from the earlier Q2 adapter work already exists on latest `main`, reuse/harden it rather than creating a second competing abstraction.

## 5. Candidate prefilter architecture — high-recall retrieval, not final truth

Human labeling throughput should be improved by a permissive box-candidate retrieval stage.

The prefilter is **not** Ground Truth and must not define the entire learning domain.

### 5.1 Plugin-style isolation

Implement the candidate logic in an isolated, replaceable module rather than embedding thresholds in the web server, dataset builder, renderer, or trainer.

Preferred structure:

```text
src/radar/box_labeling/
    candidate_plugins/
        __init__.py
        base.py
        loose_box_v1.py
```

The exact package path may be adjusted to existing repository conventions, but the separation-of-concerns contract is mandatory.

The plugin receives only an already-authorized past-only OHLCV history object / numeric frame. It must not:

- open DuckDB itself;
- read arbitrary files;
- perform network access;
- read future labels;
- inspect portfolio/backtest results;
- depend on Test/Fresh outcomes.

Return a typed result such as:

```python
CandidateResult(
    passed: bool,
    score: float,
    diagnostics: Mapping[str, float | int | bool | str],
    rejection_reasons: tuple[str, ...],
)
```

### 5.2 Loose-box-v1 design objective

`loose_box_v1` is a **high-recall candidate generator**. It should identify plausible range/channel structures while deliberately tolerating:

- non-perfectly horizontal boundaries;
- locally irregular swings;
- transient support undercuts / false breakdowns;
- unequal swing amplitudes;
- volatility heterogeneity;
- partial degradation near the decision date.

Do not reproduce Q2 v1.2-style textbook-perfect geometric conjunctions.

Candidate diagnostics may include causal, scale-free descriptors such as:

- range occupancy / containment ratio;
- robust upper/lower quantile bands;
- boundary-touch density;
- oscillation / turning-point count;
- alternation quality;
- robust drift / channel slope;
- range width relative to local price/volatility;
- lower-band/current normalized position;
- undercut magnitude and recovery;
- monotonic-trend penalty;
- structural-breakdown flag.

These are candidate-generation diagnostics, **not the supervised target**.

Thresholds must be explicit and versioned. Prefer a separate configuration namespace/file for numeric thresholds so logic and tuning surface remain inspectable.

No threshold may be tuned against future returns in this work order.

## 6. Sampling design — prevent candidate-filter selection bias

Do not construct the human dataset solely from `loose_box_v1.passed == True`.

The dataset builder must preserve a control channel so the future model can learn structures that the prefilter misses.

Create versioned sampling strata, with configurable proportions. Initial recommended policy:

- ~70% prefilter-positive / high-scoring suspicious boxes;
- ~20% boundary / near-miss / disagreement cases;
- ~10% unconditional or minimally conditioned historical controls.

Exact quotas belong in configuration and must be reported in the dataset receipt.

Candidate stratum and prefilter score must be **hidden from the human labeling UI** to reduce anchoring bias.

Use Train/Validation development domains only. Do not consume Historical Test or Fresh OOS for labeling or model selection in this task.

Avoid near-duplicate leakage:

- group highly overlapping windows from the same security;
- preserve issuer/security identity for split control;
- prohibit trivial adjacent-window duplication across Train/Validation;
- record repeat tasks separately only when intentionally measuring human self-consistency.

## 7. Multi-scale as-of-T numerical representation

Construct and persist versioned numeric tensors from the same historical prefix used by the human views.

Initial target representation:

- Daily: last **126 trading sessions** when available;
- Weekly: last **52 as-of-T weekly bars** when available;
- Monthly: last **18 as-of-T monthly bars** when available.

If the available trusted history cannot satisfy a scale, record explicit availability/mask metadata. Do not synthesize future observations or silently forward-fill missing market sessions.

Tensor channels:

```text
open, high, low, close, volume
```

### 7.1 Causal normalization

Normalization must remove irrelevant price/volume scale without using information after T.

Implement and version a deterministic causal normalization contract. Suitable options include:

- log-price relative to a past-only reference such as T close or the first valid window close;
- OHLC represented relative to the same causal anchor;
- volume represented by log-volume and/or a past-only relative-volume normalization.

Whichever method is selected:

- document the formula;
- preserve raw OHLCV separately;
- store raw and normalized hashes;
- test invariance to absolute price rescaling where economically appropriate;
- never calculate normalization statistics using post-T samples.

## 8. Local human-labeling web application

Reuse the existing authenticated local Django / Label Studio extension infrastructure where practical:

- session/auth handling;
- CSRF;
- local-only operation;
- transactional SQLite annotation persistence;
- immutable revisions / audit events;
- no-store responses;
- deterministic task manifest and hashes.

Do not overwrite or repurpose v3 annotation contracts in place. Add a new versioned subsystem.

Suggested route:

`/box-label/v1/human/`

### 8.1 UI

For each task, display simultaneously:

- Daily candlestick chart through T;
- Weekly candlestick chart through T;
- Monthly candlestick chart through T.

The decision date is historical and must be treated as "latest as of T", **not latest today**.

Do not display:

- ticker/symbol if unnecessary for structure judgment;
- calendar date if hiding it reduces context leakage and does not impede labeling;
- prefilter score/stratum;
- future prices;
- future returns;
- subsequent outcome;
- any current-day/current-company metadata that would reveal post-T knowledge.

Use stable relative scaling and deterministic rendering.

Support efficient keyboard-driven labeling.

### 8.2 Label contract

Create a new, explicit schema. Minimum fields:

```text
shape:
  BOX
  NOT_BOX
  UNCERTAIN

position:
  LOWER
  MIDDLE
  UPPER
  BREAKDOWN
  UNCERTAIN

confidence:
  HIGH
  MEDIUM
  LOW
```

Optional reason codes should be versioned and finite, for example:

- repeated_support_zone;
- repeated_resistance_zone;
- clean_oscillation;
- noisy_but_intact;
- transient_undercut_recovered;
- boundary_instability;
- insufficient_oscillation;
- monotonic_trend;
- structural_breakdown;
- ambiguous_multiscale_context.

Allow an optional short note but do not make free text a model feature.

Persist:

- task id;
- user id;
- annotation id;
- revision;
- timestamp;
- label-schema version;
- dataset version;
- candidate-plugin version/config hash;
- decision date T;
- security id;
- daily/weekly/monthly tensor hashes;
- render hashes;
- contamination/repeat state where applicable.

Real human annotations remain local/ignored unless the existing repository policy explicitly allows metadata-only provenance. Do not commit private label payloads.

## 9. Training-ready export contract

Implement an export that joins human labels to the **numeric** tensors without making the visualization image a model input.

A training example should resolve to a structure similar to:

```text
sample_id
security_id
decision_date
split
daily_tensor
weekly_tensor
monthly_tensor
scale_masks
shape_label
position_label
confidence
dataset_version
normalization_version
candidate_plugin_version
source_hashes
```

No future outcome columns may appear in the model-input artifact.

Export should support deterministic PyTorch-style dataset loading without requiring the training process to open the historical database.

## 10. Numeric deep-learning scaffold

Implement a minimal, research-grade **training scaffold**, not a profitability model.

Preferred baseline architecture:

```text
Daily OHLCV  -> 1D sequence encoder ---\
Weekly OHLCV -> 1D sequence encoder ----> fusion representation
Monthly OHLCV-> 1D sequence encoder ---/
                                      |--> Shape head
                                      \--> Position head
```

A lightweight 1D CNN or TCN-style encoder is acceptable. Keep the first implementation small and auditable.

Requirements:

- numeric sequence only;
- multi-scale masks for unavailable scales;
- separate shape and position heads;
- configurable seeds;
- deterministic split manifests;
- class-weight / imbalance handling configurable, not hard-coded to observed validation performance;
- checkpoint metadata includes code/config/data hashes;
- metrics include per-class precision, recall, F1, confusion matrix, and calibration diagnostics if probabilities are interpreted probabilistically;
- no random sample-level split that places heavily overlapping windows from the same security into both Train and Validation.

Do not build ResNet/ViT/image encoders in this task.

### 10.1 Training execution boundary

Real production-quality model training is **not required to complete this engineering work order**, because a valid human-labeled corpus may not yet exist.

Codex may:

- implement the trainer;
- run unit/integration tests;
- run a tiny smoke fit on synthetic/fixture labels to verify the pipeline.

Codex must **not fabricate human labels**, must not use future outcomes as substitute labels, and must not claim model quality from smoke data.

The user will perform real labeling before substantive supervised training.

## 11. Reuse before rewrite

Prefer reuse of existing components where their contracts match:

- Research Infrastructure v1;
- causal hash/provenance helpers;
- v3 local authenticated annotation server pattern;
- SQLite transactional store pattern;
- deterministic rendering primitives;
- existing tests for future isolation.

Do not force this new task into legacy `BlindRequest` / Observe / Entry semantics. Create new versioned contracts.

Do not couple this labeling pipeline to Strategy Lab portfolio execution.

## 12. Required tests and leakage audits

At minimum add automated coverage for:

1. **post-T mutation invariance** — changing all bars after T changes nothing upstream;
2. **partial week correctness** — no Friday close appears in a Wednesday-T weekly bar;
3. **partial month correctness** — no post-T session appears in the T-month bar;
4. **history-provider boundary** — provider rejects/omits all future rows;
5. **candidate-plugin purity** — plugin has no database/network/future-label access;
6. **candidate determinism** — identical input/config => identical result;
7. **sampling controls** — positive, boundary, and unconditional-control strata are all present;
8. **UI payload isolation** — no future outcome, prefilter score, or hidden post-T metadata in page/API payload;
9. **tensor/render binding** — task hashes bind the exact numeric inputs shown to the human;
10. **annotation revision integrity** — no silent overwrite of original labels;
11. **training export isolation** — no future-derived field can enter X;
12. **overlap/group split guard** — adjacent/overlapping windows cannot trivially leak across Train/Validation;
13. **frozen source integrity** — Research Infrastructure v1 protected hashes unchanged;
14. full targeted regression for existing v3 labeling infrastructure.

Run targeted tests first, then the relevant full project suite once. Report actual pass/fail counts and any pre-existing failures separately.

## 13. Deliverables

Required deliverables:

1. versioned `box_labeling_v1` implementation;
2. isolated `loose_box_v1` candidate plugin and explicit config;
3. additive causal history provider if not already available;
4. multi-scale daily/weekly/monthly as-of-T tensor builder;
5. local three-panel labeling UI;
6. versioned label contracts and transactional persistence;
7. training-ready numeric dataset exporter;
8. lightweight multi-scale 1D CNN/TCN training scaffold;
9. unit/integration/leakage tests;
10. operator documentation with exact local startup commands and labeling URL;
11. acceptance report documenting hashes, data boundary, task counts, tests, and known limitations.

Do not commit real market data, model training data, real human labels, credentials, or large generated artifacts.

## 14. Explicit non-goals

Do not:

- train an image CNN;
- use PNG/SVG pixels as default model inputs;
- run portfolio backtests;
- optimize for future returns;
- access QC Cloud;
- run LEAN for strategy profitability;
- resume Q1/Q2 implementation work;
- tune candidate thresholds against Test/Fresh or forward returns;
- expand/rebuild frozen market databases;
- use current-survivor membership in historical sampling;
- generate labels from GPT/VLM and treat them as human truth;
- merge implementation to `main` without later explicit user approval.

## 15. Acceptance criteria

The task is complete only when all of the following are true:

- a historical date T can be sampled from the supported Train/Validation domain;
- a permissive, replaceable candidate plugin can generate suspicious-box / boundary / control tasks without reading future data;
- the user can open the local web page and see Daily/Weekly/Monthly charts whose latest observation is exactly as-of-T;
- the user can persist BOX / NOT_BOX / UNCERTAIN and position labels efficiently;
- those labels can be exported into deterministic, numeric OHLCV training examples;
- the numeric deep-learning trainer can consume that export in a smoke run;
- post-T data mutation provably cannot alter candidate generation, resampling, renderings, tensors, or pre-label task payload;
- no protected Research Infrastructure v1 artifact is modified;
- no profitability or alpha claim is made.

## 16. Codex stop condition

Implement and validate the engineering pipeline above, then stop.

Do not initiate substantive real-label model training, return evaluation, strategy backtesting, or model-selection campaigns until the user has produced a real labeled corpus and explicitly authorizes the next research stage.
