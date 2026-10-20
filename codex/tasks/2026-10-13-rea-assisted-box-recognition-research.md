# Codex Research Work Order — Evidence-led Box/Range Recognition (REA-assisted)

> Date: 2026-10-13
> Status: **PROPOSED / NOT ACTIVE — documentation only**
> Research family: **Quant-only box-recognition baseline**, not a fourth top-level research family. Under the [revised path](../../docs/BOX_RESEARCH_DEVELOPMENT_PATH.md), causal open-source-assisted detection is the next **proposed** engineering priority; numeric CNN/TCN remains an optional later comparator.
> Repository: `zhoushuming073-cell/stock-radar`
> Integration target: Draft [PR #21 — Box Labeling v1](https://github.com/zhoushuming073-cell/stock-radar/pull/21)
> Primary outcome: an independently implemented, causally correct, interpretable box detector and a reproducible comparison protocol against `loose_box_v1` and independent human structure labels

## 0. Activation and authority — read this before doing anything

**This file is a Codex-ready proposed work order, NOT implementation authorization.** Creating or reading it must not change the active priority. Obey `AGENTS.md` and `codex/tasks/ACTIVE.md`. Until the user explicitly activates this work order in `ACTIVE.md`, Codex may review/design the proposal but MUST NOT start implementation, training, backtests, database changes, or merge PRs on the authority of this file alone.

When explicitly activated, synchronize latest `main`, inspect the worktree and uncommitted changes without destroying them, then read in order:

1. `AGENTS.md`
2. `reports/journey-2026-09-30-0651-📌当前总账.md`
3. `docs/RESEARCH_MASTER_GUIDE.md`
4. `codex/tasks/ACTIVE.md`
5. This work order and `docs/RESEARCH_INFRASTRUCTURE_V1.md`
6. Draft PR #21's exact head SHA, diff and acceptance report; `docs/BOX_LABELING_V1.md` and `src/radar/box_labeling/*` **on its actual branch**, not assumed to be present on `main`
7. Relevant Q2 historical notes only as background; older work orders do not override current authority.

Check whether PR #21 has been merged/updated before coding. Prefer a separate experiment branch or, if expressly authorized and technically safer, a branch based on its current head. **Do not merge PR #21 or silently cherry-pick/overwrite experimental sources**. Do not rewrite old status, frozen artifacts, acceptance receipts, source hashes or completed Run records.

## 1. Research question and conceptual split

Given past-only OHLCV available at a historical decision cutoff `T`, can Radar independently recognize persistent horizontal/slow-drifting boxes and ranges, locate the current price within their structural boundaries, tolerate limited noise/false undercuts, and separate consolidation from a monotonic downtrend **without look-ahead**?

Distinguish four different objects:

- **Candidate retrieval:** permissive `loose_box_v1`, high recall, not ground truth.
- **Rule-based structural baseline:** proposed `pivot_rectangle_baseline_v1`; interpretable, conservative and versioned.
- **Human structure labels:** `BOX / NOT_BOX / UNCERTAIN` and `LOWER / MIDDLE / UPPER / BREAKDOWN / UNCERTAIN`, judged on blinded as-of-T Daily/Weekly/Monthly charts.
- **Numeric learning model:** possible later 1D CNN/TCN on causal OHLCV tensors; not an image model, and neither training nor alpha claims are authorized by this document.

Do **not** conflate rectangle recognition, manual chart drawing, profitable entries, and forward-return prediction. A visually coherent box may have no predictive edge. The first target is **reproducible structure recognition**, not strategy profitability.

## 2. External evidence, REA boundaries and falsifiability

### 2.1 Public behavioral reference (not recovered proprietary code)

Use the official TradingView education page as a **documented reference specification only**:

- [TradingView — Chart Pattern Rectangle](https://www.tradingview.com/support/solutions/43000653216/). It publicly describes searching the last 600 bars; 5/5 pivot-based pattern endpoints; close-based breakout confirmation; and an `In Progress` mode in which the final endpoints need not be confirmed pivots. Treat these as documented **observable product behaviors**, not proof of its underlying source implementation.
- The `600` lookback is a product-specific documented search horizon, **not** a mandatory choice for Radar. Record any chosen independent window configuration.
- Explicitly separate what the public documentation states, what local authorized experiments show, what is inferred, and what remains unknown. Attach source URL, observation/access date, screenshots or hashes only where permitted, and a confidence/limitation statement.

Do not describe the deliverable as "recovering TradingView's algorithm", matching proprietary ranking, or reproducing hidden heuristics. Do not present approximate parity as verified without independent evidence.

### 2.2 REA: narrow, optional, authorized inspection

REA source: [morluto/rea](https://github.com/morluto/rea). REA may provide evidence-led analysis of **Radar's own local labeling UI** (rendering, coordinates, event flow, state transitions, chart/annotation consistency) or an explicitly authorized test target. Prefer official product docs for TradingView behavior.

If REA is installed and the operator has authorized its use, check its current README/setup/tool contracts first (`npx rea-agents setup` is an **operator-reviewed** setup action, not permission for Codex to install tools unattended). REA website inspection has passive and separately controlled interactive paths; determine actual capability rather than assume it can inspect server-side detection logic.

**Hard prohibition:** No unauthorized access to TradingView internals; no circumvention of authentication, bot controls, rate limits or technical safeguards; no extraction, harvesting, retention, replay or redistribution of TradingView OHLCV, indicators, proprietary pattern outputs, scripts, WebSocket payloads or sessions for Radar's non-display/algorithmic usage. No unapproved scripted large-scale page interaction. Do not feed protected outputs into the dataset, student model, or ground truth. Do not copy site source code or attempt a drop-in clone.

TradingView's current market-data use policy is restrictive for non-display and algorithmic purposes: [Terms/policies](https://www.tradingview.com/policies/). If an observation's authorization or permitted reuse is unclear, **skip it** and continue with official documentation and Radar's owned local UI/data. Absence of REA must **not block** the independent baseline.

Required research receipt: a `source_evidence_matrix` with columns `claim, evidence_type, source_url_or_local_path, observed_at, permission_scope, confidence, limitations`. If a capability is not observable, record `UNVERIFIED` instead of speculating.

## 3. Data and temporal contracts — non-negotiable

Use frozen `Research Infrastructure v1` through the authorized read-only history capability and preserve `security_id` identity across ticker episodes. Keep membership `confirmed/probable/unknown` semantics, source provenance, corporate-action quarantine and missingness explicit. Never default to current survivors for historical populations. Never splice adjusted and raw execution-price series. Do not edit/rebuild any frozen DuckDB, PIT master, source snapshot or manifest.

**Only information knowable by T is legal input.** This includes selection, pivots, box geometry, score, weekly/monthly aggregation, normalization, human task content, ranking and sampling. Do not preload or serialize post-T data in any annotation payload.

For incomplete week/month at T: use first known open, max/min high/low up to T, last known close through T, sum volume through T; explicitly flag `partial_asof_T`. The nominal week/month-end label must not be interpreted as an observed future timestamp.

A 5-left/5-right pivot centered at bar `i` is **not confirmed until bar `i+5` has completed**. At time `T < i+5` the detector must not use that confirmed pivot. Preserve both `pivot_event_date` and `first_confirmable_date`. Model signal time uses the latter.

The `DEVELOPING` path may use unconfirmed trailing candidate extrema based exclusively on the prefix through T, but must label them provisional and expose invalidation risk; never backdate later confirmation. A post-T change must leave all artifacts for T exactly unchanged.

Preserve one consistent coordinate system for geometry and positional tests (prefer log-price with explicit conversion for user-facing boundaries). Do not combine linear-price thresholding with log-price channel positioning unintentionally.

## 4. Baselines and precise output contract

### 4.1 Keep the high-recall plugin intact

`src/radar/box_labeling/candidate_plugins/loose_box_v1.py` in Draft PR #21 uses quantile bands, occupancy, smoothed close turning counts, drift, undercut and position. Its job is **candidate retrieval**, not calibrated structure truth.

Do not rewrite or retune its semantics silently. Treat existing version, configuration and hash as a fixed baseline; any improvement is a distinct version. In particular, do not turn candidate scores into annotations or labels.

### 4.2 Add a separate independent detector

Implement (only when authorized) a separately versioned `pivot_rectangle_baseline_v1` under an appropriate `src/radar/box_labeling/` submodule or plugin interface; minimize coupling to current `web.py`, `dataset.py` and `trainer.py`.

Research and define, before choosing numeric thresholds:

1. **Confirmed pivot geometry:** actual 5/5 confirmation delay; ties/plateaus policy; minimum pivot prominence and sample spacing. Avoid counting five adjacent touches as five independent support tests.
2. **Support/resistance zones:** robust boundaries derived from multiple independent extrema; width/tolerance normalized by contemporaneous volatility or box width; no exact horizontal-price equality requirement.
3. **Non-perfect channels:** optional bounded, slow drift with approximately compatible upper/lower slope; distinguish a drifting rectangle from persistent directional collapse.
4. **Repetition and alternation:** distinct upper/lower tests, alternating swings, occupancy and time persistence; reject micro-noise masquerading as meaningful oscillations.
5. **Developing and confirmed states:** maintain evidence of unconfirmed structure separately from confirmed pivots and structural confidence; explicit no-pattern and uncertain outcomes.
6. **Current location:** normalized [0,1] structural position inside the same log-price box; positions below 0 or above 1 are **out-of-range**, not automatically ideal low entries. Map independently to the existing position labels.
7. **Breakdown/undercut semantics:** wick-only intraperiod penetration vs close-based breach, magnitude, duration and past-only recovery evidence; do not call an undercut "recovered" until recovery has happened by T. Treat severe closing breaks and accelerating decline as risk/rejection evidence.
8. **Multi-scale diagnostics:** optional weekly/monthly agreement, with incomplete-history masks and no silent extra future bars. Disagreement should be observable rather than always a hard filter.

Suggested typed result (adapt to existing project types rather than introduce a competing API):

```text
BoxDetectionResult:
  detector_id / semantic_version / config_hash
  security_id / observed_through / source_hashes
  status: NONE | DEVELOPING | CONFIRMED | BREAKDOWN | UNCERTAIN
  position_label: LOWER | MIDDLE | UPPER | BREAKDOWN | UNCERTAIN
  lower_log / upper_log / optional_slope / width / normalized_position
  first_detectable_at / pivot_event_dates / pivot_confirmed_at
  confidence_or_score (explicitly uncalibrated unless validated)
  diagnostics: independent touches, alternations, occupancy,
               persistence, prominence, trend_penalty, undercut,
               recoveries_known_by_T, missingness, scale_agreement
  reason_codes / quality_flags / source_provenance
```

If metadata would expose future information in the human UI, keep it in a separate private receipt. Never send `loose_box_v1` score, stratum, detector status or source-derived future context to the annotator before they commit a blind label.

### 4.3 Frozen semantics and optional variants

Do **not** optimize the definition of "box" by future returns. Establish a small predeclared rule baseline; leave any robustness variants as separate named configs. Record detector/feature/config hashes. Avoid a parameter grid over unseen portfolio outcomes or dozens of opportunistic rescue iterations.

## 5. Human annotation and evaluation design

Keep PR #21's human UI / DB and synthetic smoke labels separate. The reported PR #21 engineering sample (30 windows / 90 charts) and tests are **engineering smoke evidence**, not a real labeled evaluation set or trained model. Do not claim 200–300 labels currently exist; that is a **suggested future corpus target**, subject to user effort and explicit authorization.

If/when real human labeling is authorized, propose an initial 200–300 unique, deliberately varied historical windows from **Train/Validation development domains only**, not Historical Test/Fresh. Maintain a broad sampling design akin to ~70% permissive candidates, ~20% near-miss/disagreement, ~10% unconditional controls; log exact realized fractions and coverage. Include monotonic crashes, persistent uptrends, noisy random walks, narrow low-volatility ranges, large-wick fake breaks, split/quarantine cases, weak/partial weekly-monthly history, and disappeared-security contexts where supported.

- Blind annotation: hide identity (where feasible), calendar date, prefilter/detector scores, strata, and future outcomes. Use private as-of-T OHLCV renderings, not TradingView market data.
- Separate the user's `BOX/NOT_BOX/UNCERTAIN` from detector predictions; keep revision history, uncertainty, position and confidence intact. Do not overwrite labels after viewing predictions.
- Group by `security_id` / issuer where feasible and contiguous overlapping episodes, apply purging/embargo to prevent near-duplicate leakage, and evaluate on holdout development groups/dates not used to tune rules.
- Repeated blind tasks may measure intra-rater reliability. They are not independent examples.
- Do not create fictional labels, treat model/TradingView outputs as human truth, or assert inter-rater agreement with only one annotator.

Pre-register a comparison on the **same identity-bounded as-of-T universe, label set and cutoff**:

| Method | Purpose |
| --- | --- |
| `loose_box_v1` | High-recall retrieval baseline; evaluate recall and sampling bias |
| `pivot_rectangle_baseline_v1` | Interpretable structural baseline with confirmed/developing modes |
| Optional simple numeric descriptors / classical model | Only when separately authorized and actual labels are sufficient |
| Multi-scale 1D CNN / TCN | Scaffold only at this stage; real-label training requires a new explicit authorization |

Measure and stratify:

- BOX recall, precision, F1 and confusion matrix (including abstention/UNCERTAIN handling defined in advance);
- false-positive rate on annotated `NOT_BOX`, especially monotonic declines and noisy false oscillations;
- position-label accuracy / macro-F1 on actually labeled boxes;
- boundary error normalized by box width or as-of-T volatility **only if** independent reference bounds exist; otherwise report `NOT_MEASURABLE`;
- detection latency in **first-knowable** sessions (not hindsight pivot center);
- developing-to-confirmed transition and rate of provisional invalidation, scored without leaking this future state into earlier predictions;
- per-year, regime, volatility, holding-history completeness, disappearance and source-trust strata;
- cluster-aware confidence intervals by security/episode where sample size permits.

A recall improvement that comes from labeling every market as a box is not a success. Do not choose numeric performance targets ex post. Report sample sizes and uncertainty rather than proclaiming superiority from 30 engineering windows.

## 6. Mandatory tests and negative controls

Before reporting completion, add deterministic fixtures and tests for all items below:

1. **Post-T mutation invariance:** changing/adding every bar after T does not modify any T-time candidate, feature, drawing, score, chart, tensor or hash.
2. **Pivot knowledge latency:** `i+1` through `i+4` never confirm a 5/5 pivot centered at i; first confirmation at `i+5` only if rules hold. Explicit ties/plateaus test.
3. **Partial week/month correctness:** Wednesday T cannot include later Friday high/close; mid-month T cannot include remaining month.
4. **Geometry consistency:** log/linear conversion roundtrip and wide-box positional mismatch regression; price-level rescaling invariance where economically meaningful.
5. **Pattern positives:** well-formed sideways box; noisy but persistent band; slow bounded drift; mild undercut with recovery already visible.
6. **Pattern negatives:** monotonic selloff with tiny rebounds; trend channel falsely mistaken for a box; random walk with accidental close turns; major support breakdown; out-of-range current price.
7. **Future recovery trap:** a post-T rebound cannot retroactively classify T undercut as recovered or supply an earlier entry signal.
8. **Identity/PIT:** reused ticker different `security_id`; delisted/disappeared episode; absent/unsafe price rows; split-adjustment discontinuities quarantined; unknown membership not coerced to "not a member".
9. **Plugin purity:** no network, arbitrary filesystem, DuckDB opening, Test/Fresh outcome or future-label access from detector plugin.
10. **Sampling/holdout:** candidate-negative controls retained; adjacent windows not split across Train and Validation; repeat tasks not inflated into independent observations.
11. **UI independence:** human blind payload contains no detector score, pattern adjudication, source secret or future outcome.
12. **Reproducibility:** stable ordering, explicit versions, evidence hashes, same-config same-result; protected Research Infrastructure v1 hashes unchanged.

Run targeted tests and relevant full-project regression only if the implementation is later authorized. Report exact pass/fail/skip counts, warnings, environment and unresolved dependencies. Do not present unexecuted test scenarios as passed.

## 7. Bounded execution plan — only after explicit activation

**Stage A — Inspect and design.** Audit latest PR #21 and the real local labels (counts only, no disclosure). Review the exact existing modules/interfaces. Read official public TradingView rectangle documentation and current REA docs. Decide whether an authorized local REA experiment is actually informative. Produce the source-evidence matrix and short design ADR. Do not modify Radar data.

**Stage B — Independent baseline.** Implement the detector and typed output in an additive isolated module, implement fixture tests, and compare its structural predictions with unchanged `loose_box_v1` on past-only synthetic and permitted local development windows. Do not use future outcomes or retrospectively hand-pick favorable examples.

**Stage C — Blinded human protocol.** Wire optional shadow diagnostics privately (not into the label UI) and prepare a reproducible audit/evaluation script. If no legitimate human-label corpus exists, **STOP with LABELS_NOT_READY** and report engineering results only. Do not fabricate labels or start real-label DL training.

**Stage D — Human-label comparison, only if actual labels and scope authorization exist.** Freeze detector configuration before opening the evaluation set. Evaluate both methods on the same held-out labeled examples, report group-aware errors and limitations. Distinguish structural recognition results from tradable alpha.

Stages are separate acceptance gates. Missing REA, unsupported site inspection, or a blocked external license must not trigger a data-scraping workaround.

## 8. Expected artifacts, acceptance and stop condition

When implementation is authorized, deliver:

1. `docs/research/BOX_RECTANGLE_EVIDENCE_MATRIX.md` or equivalent dated evidence receipt, with verified sources and limitations;
2. a small ADR defining horizontal vs drifting box, confirmed vs developing, causal pivot lag, tolerances and undercut semantics;
3. `pivot_rectangle_baseline_v1` implementation and immutable/versioned config, no mutation of original `loose_box_v1` semantics;
4. typed/hashed result contract, deterministic diagnostic audit export and optional visualization on Radar-owned charts;
5. targeted causal/identity/property tests and applicable full regression;
6. evaluation protocol plus real-label results **only if those labels exist**; otherwise `LABELS_NOT_READY`;
7. honest limitations and decision record: `PROMISING`, `INCONCLUSIVE` or `REJECT`, with evidence for the selection.

**Engineering acceptance** requires fully reproducible past-only outputs, proper pivot-knowledge timing, sensible negative controls, preserved hashes and a stable UI/annotation boundary. **Research efficacy is NOT established** unless a sufficiently independent real-label experiment is actually completed. No arbitrary numerical pass mark should be invented after seeing results.

**Explicit non-goals:** scraping/copying TradingView market data or proprietary code; reverse-engineering protected server logic; bulk PIT/database expansion; altering the frozen Strategy 2 semantics; changing PR #21 by stealth; supervised training on fake/insufficient labels; Historical Test/Fresh selection, portfolio/LEAN/QC backtests, broker actions, paid services, alpha claims, or merging to `main` without user approval.

**Stop:** once the bounded, authorized stage is completed, publish a source-backed summary and evidence links. Never promote this proposed document to active implementation merely because it was pushed to GitHub.
