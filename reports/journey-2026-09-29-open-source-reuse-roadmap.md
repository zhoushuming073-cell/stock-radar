# Stock Radar Journey — Open-source Reuse Roadmap 2026-09-29

> Purpose: identify project areas that are still incomplete or likely to become expensive to maintain, and map them to mature open-source components that can be reused instead of reimplemented.
>
> This is a planning/audit document only. It does not imply that any dependency below has already been installed or integrated.
>
> Audit baseline: `main @ 7585ae9863fe49ca5afbfc50b1695b3b925f140e`

---

## Executive summary

Stock Radar already owns the parts that should remain project-specific:

- causal/as-of feature generation;
- Scanner semantics;
- forward-label definitions;
- strategy-plugin contract;
- next-session-open backtest semantics;
- reproducibility hashes and immutable Run evidence;
- research export bundle;
- project-specific candidate-quality metrics.

The next stage should avoid rebuilding generic infrastructure that mature projects already solve well.

Highest-value reuse candidates:

```text
Huey
→ local experiment/task queue

Label Studio
→ human chart ground-truth labeling

Optuna
→ bounded parameter search

exchange_calendars
→ exchange/session/timestamp calendar logic

Pandera
→ dataframe/data-quality contracts

Hypothesis
→ property-based bug discovery

mplfinance
→ standardized causal candlestick snapshots

QuantStats
→ portfolio-report appendix

LightGBM + scikit-learn
→ future probability models

SHAP
→ future model explanations

MLflow or Aim
→ later-stage ML experiment tracking

DVC
→ later-stage dataset/model versioning
```

---

# 1. Local experiment execution — reuse Huey

Repository:

https://github.com/coleifer/huey

## Why it fits

Stock Radar currently owns a growing amount of generic queue infrastructure:

- queued/running/completed/failed state;
- local worker launch;
- process recovery;
- cancellation;
- concurrency limits;
- experiment fan-out;
- long-running background work;
- future priorities/retries.

Huey already provides:

- Python task queue;
- SQLite backend;
- process/thread worker models;
- retries;
- task priorities;
- scheduled tasks;
- result storage;
- task expiration;
- rate limits/timeouts;
- pipelines/chains;
- groups and fan-out.

## Recommended boundary

Do **not** replace `RunStore`.

Use Huey only as the execution scheduler.

Recommended architecture:

```text
Huey
├─ queue order
├─ worker dispatch
├─ retries
├─ priority
└─ scheduling

Stock Radar RunStore
├─ immutable Run configuration
├─ provenance
├─ metrics
├─ candidates
├─ trades/equity/events
├─ hashes
└─ research audit evidence
```

Research truth must remain in Stock Radar's own Run records.

## Adoption priority

**High.**

Especially useful before the Experiment Platform grows to long multi-run workloads.

---

# 2. Human chart ground truth — reuse Label Studio

Repository:

https://github.com/HumanSignal/label-studio

## Why it fits

The roadmap still requires a human-labelled chart-snapshot dataset.

Do not build a custom annotation application from scratch.

Label Studio already supports:

- image annotation;
- time-series annotation;
- custom labeling forms;
- local deployment;
- SQLite-backed projects;
- dataset export;
- multiple annotation fields.

## Proposed Stock Radar workflow

```text
historical signal date t
→ truncate OHLCV at t
→ render standardized chart
→ Label Studio
→ human labels
→ exported Ground Truth dataset
```

Possible label fields:

```text
prior_strength        0–3
pullback_quality      0–3
downside_exhaustion   0–3
support               0–3
early_reversal        0–3
overall_setup         0–3
```

The annotation view must never expose future bars.

## Adoption priority

**High.**

This directly supports the planned Human GT → Logistic → LightGBM research path.

---

# 3. Parameter search — reuse Optuna

Repository:

https://github.com/optuna/optuna

Optuna Dashboard is also available in the Optuna ecosystem.

## Why it fits

Stock Radar currently supports bounded grids/ablations.

That becomes inefficient when many numeric parameters are searched jointly.

For example:

```text
5 choices × 10 parameters = 9,765,625 grid combinations
```

Optuna already provides:

- adaptive parameter sampling;
- pruning;
- parallel studies;
- reproducible storage;
- visualization/dashboard;
- parameter importance tooling.

## Research-policy boundary

Optuna must not be allowed to destroy the current research discipline.

Recommended rule:

```text
Train
→ parameter search

Validation
→ model/parameter selection check

Historical viewed Test
→ exploratory only

Fresh OOS
→ protected final evidence
```

Do not optimize directly on Validation/Test/Fresh OOS.

Persist:

- Optuna version;
- sampler;
- seed;
- search space;
- objective definition;
- study budget.

## Adoption priority

**High, but after the current experiment correctness backlog is stable.**

---

# 4. Exchange/session/timestamp logic — reuse exchange_calendars

Repository:

https://github.com/gerrymanoim/exchange_calendars

## Why it fits

Daily-only research can often infer sessions from stored SPY dates.

That is not sufficient once Stock Radar adds:

- NASDAQ premarket context;
- ES/NQ/YM;
- minute data;
- exact signal timestamps;
- DST handling;
- half-day sessions;
- different cash/futures session schedules.

`exchange_calendars` provides formal exchange calendars and session/minute queries.

## Recommended use

Use exchange calendars for:

- valid trading sessions;
- previous/next session;
- open/close timestamps;
- half days;
- exact session-aware timestamp gating.

Keep provider data timestamps as the final source of actual observation availability.

Calendar validity does not itself prove that data was available.

## Adoption priority

**High before premarket/futures/intraday work.**

---

# 5. Dataframe contracts — reuse Pandera

Repository:

https://github.com/unionai-oss/pandera

## Why it fits

Stock Radar currently performs many manual dataframe checks.

Pandera can formalize contracts such as:

- required columns;
- nullability;
- numeric bounds;
- uniqueness;
- index structure;
- category/value constraints.

Candidate examples:

```text
symbol != null
signal_date != null
close > 0
rank >= 1
0 <= probability <= 1
(date, symbol) unique
```

## Recommended boundary

Use Pandera for structural/data-quality validation.

Do not expect it to enforce time-causality by itself.

As-Of, future-mutation, label-maturity and PIT rules remain project-specific tests.

## Adoption priority

**Medium-high.**

Useful for research exports, candidate snapshots, feature tables and future external datasets.

---

# 6. Automated edge-case bug discovery — reuse Hypothesis

Repository:

https://github.com/HypothesisWorks/hypothesis

## Why it fits

Current bug mining relies heavily on manually imagined regression cases.

Hypothesis can generate many edge cases automatically and shrink a failure to a minimal reproducible example.

Candidate targets:

- missing sessions;
- duplicate rows;
- NaN/inf values;
- one-symbol universes;
- zero-volume bars;
- signal on final available date;
- horizon beyond data end;
- pathological candidate rankings;
- malformed plugin outputs;
- terminal events;
- split-boundary invariants.

## Recommended approach

Encode research invariants rather than random implementation-specific tests.

Examples:

```text
future mutation cannot change past signal state

rank must be deterministic for identical input

candidate selection cannot fabricate symbols

adding later sessions cannot move frozen historical split membership

export round-trip must preserve row counts and Run identity
```

## Adoption priority

**High for future bug mining.**

This can complement Codex/manual audits rather than replacing them.

---

# 7. Standardized chart generation — reuse mplfinance

Repository:

https://github.com/matplotlib/mplfinance

## Why it fits

The future Human GT and Vision branches require standardized chart images.

The chart renderer should not become another custom UI project.

`mplfinance` already handles financial OHLC/candlestick and volume plotting.

## Proposed standardized snapshot contract

For every Ground Truth image:

- identical historical lookback;
- identical image size;
- identical chart layout;
- identical indicator set;
- fixed handling of missing sessions;
- no bars after signal date;
- no future-derived annotations.

Example:

```text
60 historical sessions
+ candlesticks
+ volume
+ selected causal moving averages
→ fixed PNG
```

## Adoption priority

**High together with Label Studio.**

---

# 8. Portfolio-report appendix — reuse QuantStats

Repository:

https://github.com/ranaroussi/quantstats

## Why it fits

Stock Radar's primary research report should remain Scanner-specific.

However, Backtest Runs can benefit from a mature portfolio tear sheet.

QuantStats provides:

- return/risk statistics;
- drawdown analysis;
- rolling statistics;
- monthly/yearly views;
- benchmark comparison;
- HTML report generation.

## Important semantic warning

QuantStats analyzes a return series.

Some metrics such as win rate may be period-based rather than Stock Radar's discrete trade-level definition.

Therefore:

```text
Scanner report
→ Stock Radar native

trade-level Backtest metrics
→ Stock Radar native

portfolio-return appendix
→ QuantStats optional
```

Never allow QuantStats to redefine fill/execution/accounting semantics.

## Adoption priority

**Medium.**

Useful when generating more polished research reports.

---

# 9. Future tabular probability models — reuse scikit-learn + LightGBM

Repositories:

https://github.com/scikit-learn/scikit-learn

https://github.com/lightgbm-org/LightGBM

## Why they fit

Stock Radar's future dataset is naturally tabular:

```text
row = stock × signal date

columns =
elasticity
pullback
support
reversal
volatility
market context
...
```

Recommended model ladder remains:

```text
rules
→ Logistic Regression
→ calibration
→ LightGBM
→ calibration
```

scikit-learn is suitable for:

- Logistic Regression;
- preprocessing;
- calibration;
- standard metrics.

LightGBM is suitable for:

- nonlinear tabular relationships;
- efficient tree boosting;
- larger feature sets.

## Critical host requirement

Do not let model libraries decide causal training windows.

Stock Radar must enforce:

```text
training rows available as-of t
+
label_available_at <= training_as_of
```

Any fitted transform must obey the same boundary.

## Adoption priority

**Future research stage.**

Do not rush this before Ground Truth and baseline Scanner evidence are stable.

---

# 10. Future model explanations — reuse SHAP

Repository:

https://github.com/shap/shap

## Why it fits

Once LightGBM or another nonlinear model is used, Candidate Inspector should be able to explain why a stock received a high/low probability.

SHAP supports model-level and per-prediction feature attribution, including efficient support for LightGBM/tree models.

Potential Candidate Inspector view:

```text
prediction: 0.73

elasticity         +0.14
support            +0.09
early_reversal     +0.07
NQ weakness        -0.05
realized_vol       -0.03
```

## Important interpretation rule

SHAP explains a model's output.

It does **not** prove economic causality.

## Adoption priority

**After ML models exist.**

---

# 11. ML experiment tracking — evaluate Aim or MLflow later

Repositories:

https://github.com/aimhubio/aim

https://github.com/mlflow/mlflow

## Why this may eventually matter

Stock Radar already has:

- Runs;
- Experiments;
- parameter/config hashes;
- artifacts;
- comparison;
- export.

Therefore replacing the current system now would create duplication.

These tools become more valuable when Stock Radar begins managing many trained models and calibration variants.

### Aim

Useful for:

- large numbers of experiment Runs;
- visual comparison;
- grouping;
- metadata queries;
- a dedicated experiment UI.

### MLflow

Useful for:

- model-training experiment tracking;
- parameters/metrics/artifacts;
- model lifecycle/registry;
- future model-management workflows.

## Recommendation

Do **not** install both.

Delay the decision until the ML phase.

Keep Stock Radar's research-run provenance as the canonical trading-research record.

## Adoption priority

**Later.**

---

# 12. Dataset/model versioning — evaluate DVC later

Repository:

https://github.com/treeverse/dvc

## Why it may help later

DVC provides:

- large-data versioning;
- data/code pipeline dependencies;
- experiment tracking;
- reproducible artifact references.

However, directly versioning one frequently-mutated multi-GB DuckDB file is not necessarily efficient.

DVC becomes more attractive if datasets become partitioned artifacts such as:

```text
data/
  year=2024/month=01/*.parquet
  year=2024/month=02/*.parquet

ground_truth/
models/
research_bundles/
```

## Adoption priority

**Later.**

Do not add DVC merely because a large database exists.

---

# Components not recommended as core replacements

## bt / vectorbt

Previously audited in:

`docs/phase3-open-source-audit.md`

They may be useful for independent cross-checks, but should not replace the canonical Stock Radar backtest engine.

Stock Radar has explicit semantics that generic engines may not match automatically:

```text
t Close signal
→ t+1 Open execution
→ explicit gap gate
→ project-specific fees/slippage
→ terminal-event handling
→ PIT/As-Of contracts
→ immutable candidate provenance
```

A second engine is useful only if it is validated against hand-calculated golden cases.

## Prefect

Repository:

https://github.com/PrefectHQ/prefect

Prefect is a capable general workflow orchestrator with scheduling, retries, caching and monitoring.

For the current single-machine Windows/local-first design it is probably heavier than necessary.

Recommended escalation path:

```text
current local machine
→ Huey

future multi-machine / service-oriented pipelines
→ reconsider Prefect
```

---

# Recommended adoption sequence

## Near term

```text
1. Hypothesis
   → stronger automatic bug mining

2. exchange_calendars
   → formal session/timestamp foundation

3. Pandera
   → data contracts

4. Huey
   → mature local Experiment scheduling

5. mplfinance + Label Studio
   → Human Ground Truth pipeline
```

## Research expansion

```text
6. Optuna
   → bounded Train-only parameter search

7. QuantStats
   → portfolio-report appendix
```

## ML phase

```text
8. scikit-learn Logistic + calibration
9. LightGBM
10. SHAP
11. Aim OR MLflow
```

## Dataset-management phase

```text
12. DVC, only if artifact/data layout makes it worthwhile
```

---

# Architectural rule

Open-source reuse should remove generic infrastructure work, not weaken research guarantees.

Keep these as Stock Radar-owned contracts:

```text
As-Of causality
PIT boundaries
label maturity
split protection
Scanner outcome definitions
candidate ranking semantics
execution timing
research provenance
Run immutability
comparison compatibility
```

External libraries may implement mechanics underneath these contracts, but must not silently redefine them.

---

# Current recommendation

The three highest-impact external components for the roadmap are:

```text
Huey
→ Experiment execution infrastructure

Label Studio
→ Human Ground Truth

Optuna
→ parameter-search infrastructure
```

The three highest-impact correctness/support components are:

```text
Hypothesis
→ bug discovery

exchange_calendars
→ time/session correctness

Pandera
→ data-contract validation
```

This division should guide future Codex work: reuse mature infrastructure where possible, while preserving Stock Radar's project-specific causal and research semantics.
