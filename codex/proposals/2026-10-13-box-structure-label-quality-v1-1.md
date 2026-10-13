# Research Proposal B1 — Box Structure Ontology, Label Reliability & Multi-scale Numeric Representation v1.1

> Date: 2026-10-13
> Status: **PROPOSED / NOT ACTIVE / NOT AN IMPLEMENTATION AUTHORIZATION**
> Research classification: **Quant-only numeric structure representation**, with shared historical human-label infrastructure (NOT an additional top-level research family).
> Dependency: draft [PR #21](https://github.com/zhoushuming073-cell/stock-radar/pull/21), branch \`feature/box-labeling-v1-20261011\`. Its code **is not merged into main**.
> Authority: \`AGENTS.md\` → canonical ledger → \`docs/RESEARCH_MASTER_GUIDE.md\` → \`codex/tasks/ACTIVE.md\`. This proposal does not override that chain.
> Activation: only when the owner explicitly approves this scope and updates \`codex/tasks/ACTIVE.md\`. Until then, **read/review only**. No unattended implementation.

## Codex mission and research question

You are the research engineer responsible for **measurement validity**, not for producing a profitable equity curve. Investigate whether historical OHLCV contains a **well-defined, reproducible, learnable range/box structure**. Build the minimum trustworthy labels and numeric representations needed to test:

- RQ-B1: Can one distinguish BOX, NOT_BOX, and genuinely ambiguous transitions from historical data ending at decision close T?
- RQ-B2: Can a repeatable human ontology describe box duration, upper/lower boundaries, structural position, undercut/breakdown, and uncertainty?
- RQ-B3: After controlling for rule-generated labels and sample-selection bias, do numeric methods reproduce *independent human judgments* on held-out historical securities/dates?
- **NOT this stage:** whether boxes predict positive forward returns. That is a distinct, later authorized research question.

H0: human box definitions are unstable across repeats or models do not outperform trivial/rule baselines on truly independently labeled cases.
H1: after defining a stable ontology, a held-out numeric learner can detect these structures with reproducible performance above those baselines.

A high accuracy against \`loose_box_v1\` automatically generated labels **does not establish H1**. Nor does code passing tests establish predictive validity.

## Scientific anchors (read abstracts, preserve distinctions)

1. Lo, Mamaysky & Wang (2000), *Foundations of Technical Analysis: Computational Algorithms, Statistical Inference, and Empirical Implementation*, **Journal of Finance**. Technical patterns can be operationalized statistically; visual subjectivity is a core measurement problem. https://doi.org/10.1111/0022-1082.00265
2. Ratner et al. (2017), *Snorkel: Rapid Training Data Creation with Weak Supervision*, **Proceedings of the VLDB Endowment**. Weak-label functions assist dataset construction, but are not independent truth. https://doi.org/10.14778/3157794.3157797
3. Gu, Kelly & Xiu (2020), *Empirical Asset Pricing via Machine Learning*, **Review of Financial Studies**. Nonlinear interactions motivate *later* model comparison; do not assume neural networks win. https://doi.org/10.1093/rfs/hhaa009
4. Fama (1970), *Efficient Capital Markets: A Review of Theory and Empirical Work*, **Journal of Finance**. Recognition of visual shapes is not evidence of tradeable alpha. https://doi.org/10.1111/j.1540-6261.1970.tb00518.x

Bibliographic reference is **not** a claim that any of these papers received a Nobel Prize. Fama is a 2013 Nobel economics laureate; Lo, Ratner, Gu, Kelly and Xiu are not cited as laureates.

## Current verified engineering baseline — audit before modifying

At the PR #21 acceptance snapshot (2026-10-11):

- 30 real historical human-review tasks, **zero actual human Ground Truth labels**; 21 prefiler positive, 6 boundary/near-miss, 3 unconditional control; 30 unique securities.
- Three historical views: **42 daily sessions, 52 weekly bars, 48 monthly bars** as of T. Only **6 of 30** have complete 48-month history; do not fabricate 2021-preceding data.
- Causal past-only numeric inputs, authenticated local annotation UI, versioned export, SHA-256 provenance and a *synthetic-smoke-only* 1D CNN scaffold exist on that **draft branch**, not necessarily on main.
- Full acceptance at that snapshot was **719 passed / 17 skipped**. That is engineering evidence, not a generalization metric.
- \`src/radar/box_labeling/candidate_plugins/loose_box_v1.py\` uses quantile bands, occupancy, turns, drift, width and undercut as a permissive retrieval heuristic. It cannot define human Ground Truth.
- **Concrete mask issue to audit:** \`numeric.py\` sets scale availability using \`len(frame) == LENGTHS[name]\`; \`trainer.py\` multiplies a scale encoder embedding by this boolean. Thus **any valid partial monthly/weekly sequence contributes zero at fusion**. Replace this semantic conflation with length-aware masks if evidence confirms; preserve missingness and never pretend padded bars are observed.
- Candidate window length **126D** differs from detailed human daily view **42D**. Review the semantic mismatch before changing accepted default views; optionally introduce a *separate*, versioned 126D diagnostic panel.
- \`trainer.py\`'s global average pooling may erase terminal location; this is a **hypothesis to benchmark later**, not authorization to build a larger model.

Synchronize main, inspect \`AGENTS.md\`, canonical ledger, master guide, ACTIVE, PR #21 branch tree and acceptance report. Check current code before assuming any snapshot remains accurate. Preserve \`box-labeling-v1\` evidence and user label stores unchanged. **Do not silently cherry-pick or merge PR #21.** If approved to implement B1, base dependent changes explicitly on the accepted PR #21 head/worktree or request a dependency decision.

## Scope / work packages in dependency order

### B1.0 — Reproducible gap audit (mandatory first)

Produce a machine-checkable inventory of:
- actual annotation schema and fields; human vs smoke DB separation; counts of genuinely saved revisions, repeats, skips and uncertainties;
- candidate strata and sampling denominators by year, split, security membership, price source/basis, observed vs disappeared participation;
- input coverage histograms for all three scales; impact of missing/partial masks on the exact model path;
- where 126D candidate diagnostics are/are not visible to reviewers;
- tested privacy gates and historical as-of-T invariance.

Create a discrepancy register: VERIFIED BUG / DESIGN TRADEOFF / DATA LIMIT / NEEDS HUMAN DECISION. If PR #21 is unavailable locally, **stop with a clear dependency report** instead of reimplementing the system on main.

### B1.1 — Versioned operational ontology (human-defined, not future-return-defined)

Design \`box-structure-label-v1.1\` without overwriting v1 revisions. Minimum fields:
- primary: BOX / NOT_BOX / UNCERTAIN (allowed, not penalized);
- current location: LOWER / MIDDLE / UPPER / BREAKDOWN / UNCERTAIN, conditionally valid;
- evidence interval \`[t_start, T]\` and approximate lower/upper boundary, with deterministic coordinate semantics and bounds checks;
- structure subtype/reason tags: sideway range, gently drifting channel, noisy consolidation, monotonic trend, transient undercut/recovery, persistent breakdown, insufficient history;
- reviewer confidence, short rationale, version, task ID, save/revision provenance.

Do **not** force artificial crisp limits where experts cannot agree. Explicitly distinguish “undecidable on visible history” from “negative”. Preserve original v1 labels, and use migrations/additive storage only if separately approved. Do not reveal ticker, year, candidate score, next-day candle, outcomes, or sampling stratum to human review.

Produce an **annotation handbook** with example *definitions* and failure modes, not selectively chosen “winning” charts. Where box lower/upper boundaries are absent for NOT_BOX or UNCERTAIN, validate null semantics instead of manufacturing values.

### B1.2 — Sampling with discoverable false negatives

Build a **new versioned candidate pool**, never overwrite the existing 30-task batch. Initial design target: **150–300 tasks for audit/candidate selection**, *not* a demand for 150–300 human labels. Proposed stratification (subject to audited availability):
- approximately 40% permissive candidate positives;
- approximately 30% hard negatives/near misses/disagreement;
- approximately 30% true unconditioned historical controls.

Maintain fixed reproducible seed, real denominators, date/issuer-group safeguards, membership-status sensitivity, available-length coverage, and deterministic task hashes. Include stress examples across volatility, trend, market condition, history length, and year; record unexplained exclusions. Enrich candidate diversity via alternate causal detection functions (robust swing pivots, boundary touches separated in time, range durability, monotonic-trend penalty), **without using future outcomes to select them**. These functions are weak annotators/retrievers only.

Quantify coverage: prefilter recall **against independent manually adjudicated unconditional controls only**, with uncertainty intervals and sample-size warnings. Do not claim representative full-market recall from the selected 30-task batch.

### B1.3 — Human reliability pilot before supervised model training

Deliver a small **blind pilot protocol**, not fabricated reviews. Suggested starting design: 20–40 manually judged cases drawn across strata plus 10–20% blind delayed repeats where feasible; ask the owner to perform real judgments via existing local UI. Report true label-count, class distribution, UNCERTAIN rate, within-rater agreement on repeats, boundary dispersion, and optional between-rater agreement *only if a second reviewer actually exists*. A single reviewer cannot supply inter-rater reliability.

Predefine adjudication procedure: revisits remain separate immutable revisions, disagreements retained; uncertainty not dropped to improve accuracy. Keep gold evaluation cases **isolated from weak-label construction and tuning**. No invented consensus or LLM-generated ground truth.

**Stop gate:** if reliable label ontology cannot be achieved, revise measurement design and return with examples of ambiguity, not a supervised-model score.

### B1.4 — Causal representation and mask integrity

Preserve approved 42D/52W/48M data contract unless introducing a **new version with explicit migration**. Investigate the 126D selector/42D display gap; propose whether a 126D additional diagnostic view is required for fair review. Avoid exposing current-date charts on historical tasks.

Represent each scale using:
- observed-step mask / observed length;
- separate coverage-quality/missingness metadata;
- mask-aware pooling/encoding so 12 genuine monthly bars contribute without 36 padded zeros becoming fictitious observations;
- an explicit rule for *truly missing or unsafe* scales.

Test as-of-T partial week/month aggregation, price-scale invariance, no post-T mutation impact, tensor/figure hash determinism, varied lengths, hash tampering, and identical forward pass for equivalent padded inputs. Do not silently substitute missing records with forward-filled prices.

### B1.5 — Pretraining comparison protocol (DESIGN ONLY)

Specify eventual evaluation ladder: majority/rule classifier → interpretable geometric descriptors + logistic/tree → numeric 1D CNN/TCN with sequence masks → optional self-supervised encoder. Pre-register subject/time splits, repeated-window grouping, classwise F1, calibration, boundary errors, agreement-adjusted ceiling, ablations by scale and by sampling stratum. Report both micro and macro averages with confidence intervals.

**No real-label training or returns research in this proposal without distinct user authorization.** Synthetic-only smoke of an existing trainer does not authorize experiment claims.

## Integrity, stop conditions and anti-goals

1. Data source is read-only \`shape_research_universe_v1\`, with original identity/basis/source hash and unresolved historical membership preserved.
2. For any feature/render/label task at T, no observation, normalization parameter, candidate selection or metadata may depend on dates >T. Add adversarial post-T mutation tests.
3. Train/Validation for developmental work only. Do not select examples, tune parameters or inspect outcome labels using Historical Test or Fresh. Do not relabel previously inspected historical windows as untouched OOS.
4. Never commit real OHLCV, raw SVG/PNG, symbol mapping, private security IDs, real annotations, sessions or tokens. Aggregate audit evidence/documented schemas only.
5. Do not rewrite acceptance history, activate or merge a PR, modify frozen database, run LEAN/QC, invoke paid resources, trade, or assert Alpha.
6. If human labeling is not available, deliver **pilot-ready design and engineering validation**, explicitly \`HUMAN_GROUND_TRUTH_NOT_COLLECTED\`. Do not fabricate counts or labels.
7. Any consequential change to input window, label semantics or sample universe requires a new version and before/after receipts.

## Expected Codex outputs **after separate activation**

- Code/diff for the smallest additively versioned fixes, test suite, schema and reproducible configuration.
- \`docs/BOX_LABELING_V1_1.md\` with label ontology/guide and storage compatibility.
- \`reports/acceptance/box-label-quality-v1-1-<date>.md\`: measured checks, counts, decisions and blockers, NOT “success” without actual evidence.
- Machine-readable aggregated diagnostics/hashes under \`reports/evidence/\`; private tasks/labels local-only.
- Reviewed PR; summarize files changed, baseline vs new coverage, mask test results, verified vs unverified assumptions, remaining human decisions.
- Exit decision among **GO_TO_HUMAN_PILOT / REDEFINE_ONTOLOGY / BLOCKED_BY_DATA_OR_DEPENDENCY**, no arbitrary completion percentage.

## Explicit owner activation example (not effective until user actually authorizes)

“Authorize B1 Box Label Quality v1.1 as the ACTIVE Codex task. Update \`codex/tasks/ACTIVE.md\` with the scope and stop gates from \`codex/proposals/2026-10-13-box-structure-label-quality-v1-1.md\`. Preserve the prior v1 work order and PR #21 provenance. Start B1.0 first.”
