# Box/Range Structure Research — Codex Design Prompt

> **Date:** 2026-10-13
> **Status:** DESIGN REFERENCE / NOT THE ACTIVE WORK ORDER
> **Audience:** Codex / repository agents
> **Scope:** historical box/range discovery, pattern-quality measurement, future 5% rebound-event research, and later ML/DL extensions
> **Critical (updated 2026-10-13):** this historical design reference does **not** supersede `codex/tasks/ACTIVE.md`. The owner subsequently authorized a docs-only priority revision toward open-source-assisted causal detection; see the [consolidated path](../../docs/BOX_RESEARCH_DEVELOPMENT_PATH.md). The older numeric-DL labeling order is no longer the next detector priority. This note does not authorize implementation.

## 0. Repository protocol and execution boundary

Before using this design prompt, synchronize latest `main` and read:

1. `AGENTS.md`
2. `reports/journey-2026-09-30-0651-📌当前总账.md`
3. `docs/RESEARCH_MASTER_GUIDE.md`
4. `codex/tasks/ACTIVE.md`
5. the [current consolidated box path](../../docs/BOX_RESEARCH_DEVELOPMENT_PATH.md); consult the October 11 numeric-labeling work order only for historical implementation context
6. this document

Treat this file as a **research / implementation design reference**. Do not begin a new training campaign, future-return optimization, Historical Test/Fresh evaluation, LEAN/QC run, broker action, paid service, or merge solely because this file exists.

Preserve Research Infrastructure v1, Q1/Q2 historical baselines, prior acceptance evidence, frozen hashes, and existing work orders.

Do not commit private human annotations, detailed user-labeled ticker/date mappings, credentials, or market-data payloads. User-specific labeled examples remain local/ignored and may be referenced only through their local dataset identifiers.

---

## 1. Research objective

The target structure is not merely “a stock that is low” and not merely “two parallel lines.”

The user prefers liquid, usually high-beta/high-volatility U.S. equities whose recent history contains a recognizable non-trending or gently drifting trading range with enough amplitude to repeatedly capture a partial rebound.

Economic intent:

- recent history contains a support zone and resistance zone that price repeatedly respects;
- price oscillates between them multiple times;
- the range is wide enough that a +5% move is only part of a normal internal swing;
- the strategy does not need to buy the exact low or hold to the exact upper boundary;
- capital may be rotated after approximately +5%, then redeployed;
- multiple related structures are legitimate: clean box, wide range, local box, gently drifting range, false-breakdown recovery, breakout-retest, trend pullback, volatility-contraction/expansion;
- structure recognition and trade-entry recognition are separate problems.

Primary structural question:

> Given only information available at historical decision time T, did the recent past contain a persistent, tradable range structure with repeated oscillations and stable support/resistance geometry, rather than a coincidental high-low span created by trend, collapse, or a few outliers?

Later outcome question, requiring separate authorization:

> Conditional on an eligible structure and an entry context, what is the probability that price reaches a +5% profit barrier before a loss barrier or maximum holding horizon?

Do not use future returns to define the structural Ground Truth.

---

## 2. Industry reference projects and what Stock Radar should learn from them

These references are conceptual and architectural. Their proprietary formulas must not be copied, reverse-engineered, or represented as Stock Radar’s own. Use only publicly documented behavior and independently implement transparent equivalents.

### 2.1 Autochartist — Market Scanner / Inside the Range / Pattern Quality

Public references:

- https://bank.autochartist.com/products/market-scanner/
- https://support.autochartist.com/en/knowledgebase/article/non-trending-pattern-types
- https://support.autochartist.com/en/knowledgebase/article/chart-pattern-quality-indicators
- https://support.autochartist.com/en/knowledgebase/article/pattern-results-details

Relevant public concepts:

- automated chart-pattern discovery;
- non-trending pattern setups;
- “Inside the Range” / fade-style trading around horizontal floors and ceilings;
- `Clarity`: alignment of price action with pattern boundaries;
- `Uniformity`: temporal spacing of boundary touches;
- overall pattern quality;
- breakout strength and volume context.

Stock Radar lesson:

**Pattern quality should not be one crude high-low statistic.** Independently implement auditable analogues of boundary clarity, temporal uniformity, oscillation completeness, and structural integrity.

### 2.2 TrendSpider — Automated Horizontal Channels / Support-Resistance Heatmaps

Public references:

- https://help.trendspider.com/kb/automated-technical-analysis/automated-chart-pattern-recognition
- https://help.trendspider.com/kb/automated-technical-analysis/horizontal-support-and-resistance-heatmaps
- https://trendspider.com/product/analyze-and-chart-any-market-asset/

Relevant public concepts:

- automated horizontal-channel recognition;
- short-term / long-term pattern horizons;
- support/resistance scanning;
- tolerance for some historical price-level violations if the broader structure remains respected;
- discarding stale or played-out patterns;
- support/resistance zones derived from repeated price confluence.

Stock Radar lesson:

**A valid box is a zone, not an exact mathematical rectangle.** Allow limited wick/temporary violations while penalizing repeated closes outside the structure. Add explicit pattern-age and structural-expiry semantics.

### 2.3 Trading Central — Technical Insight / Technical Views

Public references:

- https://investor.tradingcentral.com/tutorials/getting-started-with-technical-insight
- https://investor.tradingcentral.com/technical-insight
- https://www.tradingcentral.com/tc-products/tc-technical-insight
- https://research2.fidelity.com/fidelity/research/reports/release2/Research/TradingCentral.asp

Relevant public concepts:

- technical-event screening over large security universes;
- consolidation/range as an explicit market state;
- support/resistance generation based on repeated touches near a price level;
- higher significance for levels with more repeated tests;
- price/volume and market context as screenable dimensions;
- scenario + invalidation + targets rather than one unconditional prediction;
- combination of automated algorithms and expert validation.

Stock Radar lesson:

Use **touch density and proximity-weighted support/resistance significance**, but keep the formulas transparent. Separate structure, preferred scenario, invalidation, and target feasibility.

### 2.4 Recognia / Fidelity Technical Events

Public references:

- https://research2.fidelity.com/fidelity/research/reports/release2/Research/Recognia.asp
- https://www.fidelity.com/products/atbt/help/ActiveTraderTools_Chart_Help.html
- https://www.fidelity.com/webcontent/ap010098-etf-content/22.05.0/help/research/learn_er_technical_analysis.shtml

Relevant public concepts:

- automated pattern recognition across many instruments;
- support/resistance lines;
- short/intermediate/long trading horizons;
- classic-pattern events;
- opportunity screening and ranking;
- minimum formation duration / liquidity-type filters in some published screeners.

Stock Radar lesson:

The detector should expose **pattern horizon, formation duration, support/resistance zones, subtype, strength, and reason codes**, not just one scalar score.

### 2.5 Open-source reference: ednunezg/pytrendline

Repository:

- https://github.com/ednunezg/pytrendline

Public implementation ideas:

- pivot-point detection;
- exhaustive support/resistance trendline search;
- normalized point-to-line error tolerance;
- breakout tolerance;
- scoring that rewards low line error and more supporting points;
- grouping near-duplicate lines by slope and terminal price.

Stock Radar lesson:

This is useful as a reference for **candidate-line generation and duplicate grouping**, not as a final market-wide algorithm because exhaustive search can be expensive and the project is trendline-centric rather than full range-quality-centric.

### 2.6 Open-source reference: day0market/support_resistance

Repository:

- https://github.com/day0market/support_resistance

Public implementation ideas:

- ZigZag pivots;
- agglomerative clustering of pivots into price levels;
- minimum bars between peaks;
- median/mean level selection;
- touch-based level scoring.

Stock Radar lesson:

Price-level clustering is a strong alternative to raw quantile boundaries. Implement it as a competing detector behind a common interface and compare structural-label precision/recall, not future returns.

### 2.7 Academic anchor: Lo, Mamaysky, Wang

Reference:

- Lo, Mamaysky, Wang, “Foundations of Technical Analysis,” Journal of Finance (2000)
- public paper copy: https://www.mit.edu/~wangj/pap/LoMamayskyWang00.pdf

Research lesson:

**visual intuition → explicit geometric/statistical descriptors → causal automated detection → independent outcome evaluation.**

Stock Radar should follow this sequence rather than optimizing pattern geometry directly against forward P&L.

---

## 3. Separate four concepts

Do not mix the following into one opaque score.

### 3.1 Structure existence

Does a historical box/range actually exist?

### 3.2 Structure quality

How clean, stable, repeated, and tradable is it?

### 3.3 Trading suitability

Does the security satisfy liquidity, beta, volatility, and market-participation requirements?

### 3.4 Entry state

Is price currently in a favorable internal location with sufficient stabilization / remaining upside?

A mathematically excellent box in an illiquid, low-beta stock can remain a valid structure while being rejected as a trade candidate.

A high-beta security can be suitable for the user’s +5% rebound style even when its structure is better classified as `wide_range` than `clean_box`.

---

## 4. Historical search semantics

The detector must answer:

> Did a good box/range exist somewhere in the recent historical past?

It must **not** be restricted to:

> Is the stock inside a box today?

For every historical decision date `T`:

1. use only source observations with `date <= T`;
2. construct causal daily/weekly/monthly views;
3. search a recent-history domain, initially approximately the prior 52 completed weeks;
4. enumerate continuous candidate windows, initially 8–26 completed weeks;
5. score every candidate window independently;
6. return the best historical segment(s), not only the segment ending at T;
7. retain start/end, boundaries, subtype, diagnostics, and detector version.

The active human-labeling pipeline may display an as-of-T partial current week/month. Historical closed-window scoring may use completed bars only. This distinction must be explicit.

---

## 5. Candidate boundary estimators

Implement a common `BoundaryEstimator` interface and support at least two independent algorithms.

### 5.1 Robust quantile band baseline

Initial transparent baseline:

    lower = Q14(weekly_low)
    upper = Q86(weekly_high)
    width = upper - lower
    mid   = (upper + lower) / 2

Quantiles are versioned research defaults, not permanent constants.

### 5.2 Pivot-cluster level estimator

Alternative:

1. detect ZigZag / prominence-based swing lows and highs;
2. normalize distances by ATR, price, or candidate range width;
3. cluster lower pivots and upper pivots separately using an auditable clustering method;
4. define robust level centers by median;
5. derive support/resistance confidence from cluster membership, temporal dispersion, and distance residuals.

### 5.3 Optional parallel-channel estimator

Later allow common-slope robust bands:

    L(t) = exp(a_L + b*t)
    U(t) = exp(a_U + b*t)

where `b` is robustly estimated and heavily penalized if the accumulated drift becomes trend-like.

Do not pick the winning boundary estimator by future P&L. Compare first against human structural labels.

---

## 6. Independent touches and support/resistance quality

A valid range requires repeated **independent** tests.

### 6.1 Pivot confirmation

A simple historical baseline:

    pivot_low[t]  if low[t]  <= low[t-1]  and low[t]  <= low[t+1]
    pivot_high[t] if high[t] >= high[t-1] and high[t] >= high[t+1]

For online causal recognition, a pivot using `t+1` becomes confirmed only after `t+1` exists.

More robust prominence/ATR-based pivots are allowed.

### 6.2 Boundary contact

Normalize by range width:

    lower_distance = abs(pivot_low - lower) / width
    upper_distance = abs(upper - pivot_high) / width

A research starting tolerance can be 0.18–0.20, but it must remain configurable.

### 6.3 De-duplicate touch clusters

Several adjacent candles near the same support zone are one test, not many.

Require either:

- minimum 2–3 weekly bars between independent tests; or
- clustering in time-price space.

Expose:

- `lower_touch_count`
- `upper_touch_count`
- `lower_touch_dates`
- `upper_touch_dates`
- `touch_cluster_count`
- mean / median normalized boundary residual.

---

## 7. Oscillation completeness

A range should contain actual back-and-forth movement, not merely lows and highs.

Sort touch events by time:

    L -> H -> L -> H -> L

Compute:

- `alternation_count`
- `full_swing_count`
- `midline_cross_count`
- `median_swing_fraction`
- `swing_duration_distribution`

A full swing should require meaningful traversal of the box, not a tiny move that happens to flip labels. An initial rule may require movement through >= 55–65% of range width between alternating boundary zones.

This dimension is central to the user’s eventual +5% rebound objective.

---

## 8. Clarity — independent Stock Radar definition

Implement a transparent boundary-clarity metric inspired by the public concept, not Autochartist’s proprietary formula.

Suggested components:

### 8.1 Boundary residual clarity

For confirmed lower/upper pivots:

    residual_i = distance_to_assigned_boundary / width

Use robust aggregation:

    residual_score = 1 - clip(median(residual_i) / tolerance_scale, 0, 1)

### 8.2 Containment clarity

    containment = fraction(close within [lower - eps, upper + eps])

Track body violations separately from wick violations.

### 8.3 Outlier dependence

Measure how much fitted boundaries change after removing the most extreme 1–2 bars.

A box whose geometry depends on one spike should receive a strong penalty.

Combine these into `channel_clarity_score` with explicit subcomponents.

---

## 9. Uniformity — independent Stock Radar definition

Touch count alone is insufficient.

If four support tests all occur within three weeks, they should not look equivalent to four tests spread across six months.

For each side:

1. calculate intervals between independent touch dates;
2. normalize by candidate-window length;
3. compute dispersion relative to an approximately even spacing.

Possible baseline:

    cv = std(touch_intervals) / mean(touch_intervals)
    side_uniformity = exp(-cv)

Then combine support/resistance sides, while penalizing too few touches.

Also calculate:

- first-touch / last-touch coverage of the window;
- temporal concentration score;
- longest no-touch gap.

Expose `touch_uniformity_score`.

---

## 10. Structural stability

### 10.1 Trend drift

Let weekly closes be `C_t`.

Estimate a robust or OLS diagnostic slope and normalize accumulated drift:

    drift = slope(C) * (N - 1) / mid

Strongly negative drift should be penalized because a descending channel is not the user’s preferred box.

Strongly positive drift may indicate an already-established trend rather than a range.

### 10.2 Half-window boundary shift

Fit first and second halves independently:

    (L1, U1), (L2, U2)

Define:

    boundary_shift =
      (abs(L2-L1) + abs(U2-U1)) / (2 * width)

Small values indicate that the same support/resistance geometry persists.

### 10.3 Multi-window stability

Evaluate neighboring windows, e.g. 12/16/20/24/26 weeks or local +/- 2–4 week perturbations.

A high-quality box should not disappear completely after moving the start/end by one or two weeks.

Expose:

- `multi_window_stability`
- `boundary_shift`
- `drift_normalized`
- `neighbor_window_agreement`.

---

## 11. Width and 5% feasibility

Define range width consistently:

    width_pct_mid = (upper - lower) / ((upper + lower) / 2)

Also expose:

    lower_to_upper_return = upper / lower - 1

Do not assume one “correct” box width.

For the user’s +5% rotation objective, an economically useful structure usually needs enough internal room that +5% is not nearly the entire available move.

Later trading-suitability features may include:

    remaining_upside_to_resistance
    five_percent_headroom = (upper / candidate_entry - 1) - 0.05

Structure quality itself should not be tuned to guarantee future +5% outcomes.

---

## 12. Limited boundary violations and structural expiry

A valid range may contain:

- wick undercuts;
- false breakdowns;
- short-lived overshoots;
- intraperiod spikes.

Track separately:

- wick violation count;
- close violation count;
- maximum normalized violation;
- recovery time back into range;
- repeated consecutive closes outside range.

Do not immediately reject one wick.

Do reject or strongly penalize persistent structural failure.

Define a stale/expired pattern state when:

- price remains materially outside the band;
- the old boundaries stop attracting pivots;
- a new range forms elsewhere;
- boundary shift becomes excessive.

Historical detector output should retain both formation and expiration dates where identifiable.

---

## 13. Pattern taxonomy

Do not force all useful structures into `BOX`.

Recommended research subtypes:

- `clean_box` — stable horizontal boundaries, repeated complete oscillations;
- `wide_range` — broad zone with large swings but less textbook geometry;
- `local_box` — high-quality short-duration range embedded in a larger changing regime;
- `drifting_range` — oscillatory structure with modest boundary drift;
- `undercut_recovery` — false breakdown / spring-like recovery around an established lower zone;
- `breakout_retest` — former resistance becomes support;
- `trend_pullback` — strong trend followed by retracement;
- `volatility_contraction` — compressed range awaiting expansion;
- `not_range` / `uncertain`.

These may later become multi-label rather than mutually exclusive classes.

---

## 14. Structure-quality output

Never return only `score=82`.

Minimum structured diagnostics:

    detector_version
    estimator_type
    window_start
    window_end
    duration_weeks
    lower_bound
    upper_bound
    width_pct_mid
    lower_to_upper_return
    lower_touch_count
    upper_touch_count
    alternation_count
    full_swing_count
    midline_cross_count
    boundary_residual_median
    channel_clarity_score
    touch_uniformity_score
    containment_ratio
    wick_violation_count
    close_violation_count
    max_violation_norm
    drift_normalized
    boundary_shift
    multi_window_stability
    subtype
    quality_score
    rejection_reason_codes

The scalar `quality_score` is a convenience ranking metric, not Ground Truth.

---

## 15. Initial transparent quality-score baseline

For engineering diagnostics only, a baseline score can combine normalized sub-scores:

    quality =
        0.18 * boundary_touch_quality
      + 0.18 * alternation_quality
      + 0.14 * full_swing_quality
      + 0.14 * clarity
      + 0.12 * uniformity
      + 0.12 * structural_stability
      + 0.07 * containment
      + 0.05 * width_suitability

This is deliberately only a starting point.

Rules:

- keep every component visible;
- version all weights;
- do not optimize weights on future return;
- compare against human box labels first;
- perform ablation: each feature family must justify itself;
- allow the final ML/DL structure model to replace this handcrafted score if it generalizes better.

---

## 16. Trading-suitability gate — separate from structure

Later trade-candidate research should evaluate a separate market-activity layer.

Candidate variables may include:

- `beta_spy_126`
- `beta_spy_60`
- `beta_qqq_126`
- `adv20_dollar`
- `adv60_dollar`
- `atr20_pct`
- realized volatility;
- upside-day vs downside-day dollar-volume ratio;
- relative dollar-volume expansion;
- relative strength vs SPY/QQQ.

Research starting gates previously discussed:

- Beta(SPY,126) >= ~2.0;
- ADV20 dollar >= ~$50M;
- Beta >= ~2.5 and ADV20 >= ~$100M receives priority.

These are **research hypotheses**, not approved permanent production thresholds.

Use Alpaca SIP or the repository’s historical source consistently. Do not mix IEX partial-volume data with SIP full-market volume in one threshold.

---

## 17. Later +5% event-label research

Not authorized by this design-reference file alone.

When separately approved, formulate the trading objective as an event-label problem rather than “did price look bullish.”

Example triple-barrier experiment:

- upper barrier: +5%;
- lower barrier: configurable risk barrier, e.g. -3% only as an initial experiment;
- vertical barrier: configurable maximum holding horizon, e.g. 5/10/15 sessions.

For signal time `T` and actual executable entry price `P_entry`:

    tau_up   = first time price reaches P_entry * 1.05
    tau_down = first time price reaches loss barrier
    tau_time = maximum holding horizon

Label by the first event.

Explicitly handle:

- overnight gaps;
- same-bar upper/lower touches with unknown intraday ordering;
- halts;
- delisting;
- missing bars;
- corporate actions;
- fees and slippage.

Do not optimize structural labels using these outcomes.

---

## 18. ML / DL roadmap

The active project correctly treats candlestick charts as **human annotation views**, while numeric OHLCV sequences are the default model input.

Recommended future comparison order:

1. handcrafted deterministic detector;
2. classical ML on explicit descriptors;
3. LightGBM/CatBoost structure classifier;
4. multi-scale 1D CNN / TCN over normalized Daily/Weekly/Monthly OHLCV;
5. fusion of learned representation + explicit geometry;
6. only later, if justified, image/model-control experiments.

Primary structure-model metrics:

- BOX / NOT_BOX precision and recall;
- subtype macro-F1;
- probability calibration;
- boundary-location error;
- human-model disagreement;
- false-positive reason distribution;
- robustness under small window perturbations.

Do not use strategy Sharpe as the first model-selection metric for structural recognition.

---

## 19. Sampling and anti-selection-bias design

The candidate detector must remain a **high-recall retrieval tool**, not the definition of Ground Truth.

Human-label corpus should include:

- high-scoring candidates;
- near-miss / boundary cases;
- detector-disagreement cases;
- unconditional controls;
- trend controls;
- low-liquidity / low-beta controls when studying structure independently.

Hide detector score from the human labeling UI.

Prevent overlapping windows from the same security leaking across Train/Validation.

Never put user-specific ticker/date labels into source code as whitelists or blacklists.

---

## 20. Required future validation

When this design becomes an authorized implementation task, require:

1. post-T mutation invariance;
2. correct partial-week/month semantics;
3. deterministic historical-window enumeration;
4. raw-extrema outlier resistance;
5. adjacent-touch de-duplication;
6. touch-uniformity tests;
7. clarity tests;
8. descending-channel rejection;
9. multi-window stability tests;
10. false-breakdown tolerance;
11. stale-pattern expiry;
12. detector-ablation report;
13. human-label precision/recall on Train/Validation;
14. no Test/Fresh or future-return tuning during structure development;
15. no protected Research Infrastructure v1 mutation.

---

## 21. What not to do

Do not:

- identify a box using only rolling max/min;
- call several adjacent candles “several independent touches”;
- accept a persistent downtrend just because two parallel lines can be fitted;
- require perfectly horizontal lines;
- reject every wick outside the boundary;
- search only the window ending today;
- tune geometry thresholds until known favorite tickers pass;
- encode named tickers into rules;
- optimize structural thresholds using +5% future returns;
- mix structure quality, beta, liquidity, and entry state into one unexplained score;
- overwrite Q2 historical baselines;
- modify `ACTIVE.md` unless the user explicitly authorizes a priority change.

---

## 22. Expected Codex deliverable when later activated

If/when the user promotes this design into an active work order, Codex should produce:

1. a versioned `RangeDetector` interface;
2. robust-quantile and pivot-cluster implementations;
3. historical rolling-window search;
4. independent touch clustering;
5. Clarity and Uniformity metrics;
6. oscillation/full-swing metrics;
7. drift and boundary-shift diagnostics;
8. multi-window stability;
9. pattern subtype classifier/rules;
10. structured diagnostics and reason codes;
11. integration into the active human-labeling pipeline as a replaceable high-recall candidate plugin;
12. tests and leakage audits;
13. a local comparison report against human structural labels;
14. an industry-reference design note documenting what was independently implemented versus merely used as inspiration.

Stop before profitability optimization unless a separate work order explicitly authorizes it.

---

## 23. Core research principle

The project should aim to quantify what an experienced human sees when saying:

> “This stock has spent months repeatedly bouncing between approximately the same support and resistance zones, the swings are large enough to trade, and the structure is stable enough that the next internal rebound is worth studying.”

The detector’s job is to identify and describe that structure **without seeing the future**.

The later strategy model’s job is to decide whether a particular occurrence offers enough probability and payoff to justify attempting the user’s approximately +5% rebound trade.

Keep these two jobs separate.
