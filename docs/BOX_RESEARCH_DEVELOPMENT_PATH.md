# Box research: consolidated development path

> Reviewed 2026-10-13. **Planning only; not a new implementation authorization.**
> Entry authority remains AGENTS → canonical ledger → Research Master Guide → ACTIVE.
> Owner requested consolidation of four briefs and a development sequence. No proposal is activated by this document.

## Four briefs, two research tracks

| Document | Responsibility | Recommended disposition |
| --- | --- | --- |
| [Box/range design](../codex/tasks/2026-10-13-box-range-structure-research-design-prompt.md) | Product intent, historical segment search, geometry, quality, eventual +5% event question | Design reference for the box track; later economic sections remain gated |
| [REA-assisted recognition](../codex/tasks/2026-10-13-rea-assisted-box-recognition-research.md) | Independent pivot-based detector, confirmation latency, interpretable diagnostics | Detector implementation specification after measurement foundations |
| [BOX-LQ1](../codex/proposals/2026-10-13-box-structure-label-quality-v1-1.md) | Label ontology, sampling independence, reliability and numerical masks | Recommended next bounded engineering priority |
| [S1 shock/resilience](../codex/proposals/2026-10-13-shock-transmission-resilience-s1.md) | Independent market/peer shock feasibility and later response study | Separate backlog; start only with S1.0 feasibility authorization |

The first three documents describe complementary parts of one box research track, not three competing platforms. S1 does not need the box detector and is not a prerequisite for labeling. Numeric sequence learning remains the master's shared sequence control / Quant numeric structure work; these briefs do not create a fourth research family.

## Verified starting point and evidence limits

- Remote main at review: `5165f98b250751ee1a1eea0882ad1980deadf1a8`.
- Box implementation: unmerged draft [PR #21](https://github.com/zhoushuming073-cell/stock-radar/pull/21), head `07222782657d2ba2068dd5f7ae41cc5b6e72b2aa`.
- Its dated acceptance reports 30 historical tasks, 90 charts, 0 human annotations and 719 passed / 17 skipped. Those are **2026-10-11 receipts**, not freshly measured label counts or new test results.
- Source review confirms `numeric_bundle()` sets `available` only for full-length scales; `load_export()` carries that boolean and `MultiScaleBox.forward()` zeroes the whole partial-scale embedding. Valid partial monthly/weekly history is therefore discarded by the scaffold. This is a verified representation defect to fix before substantive training; it does not mean the displayed partial candles are fabricated.
- The permissive selector uses 126 daily sessions while the close-up daily display has 42. This is a definition/display tradeoff, not by itself evidence of leakage.
- Only 6/30 tasks had 48 monthly bars at the acceptance snapshot. RI v1 begins September 2021; four prior years cannot be invented for early Train cases. Preserve observed lengths.
- This review did not rerun pytest, read future outcomes, recount private labels, train a model, or run LEAN/QC. External references are the briefs' proposed reading list; this pass does not certify external algorithms, licenses or scientific claims.

## Resolve overlaps before coding

1. **Four independent objects:** structure existence, structure quality, trading suitability, entry state. High beta or +5% headroom must not determine whether a human calls a structure BOX.
2. **Past formation versus current state:** record formation start/end, first knowable detection time, observed-through T, and current state separately. An old valid box can be expired or broken at T. Human questions must specify the interval being judged.
3. **Windows:** retain the user's 42D / 52W / 48M defaults. Use the existing weekly overview for long structure context; consider an optional versioned 126D context panel only after a pilot shows it is needed. Never silently replace the defaults.
4. **Sampling:** v1's 70/20/10 remains immutable historical evidence. For a new audit pool, prefer BOX-LQ1's provisional 40% candidates / 30% near-miss or detector disagreement / 30% unconditional controls. Record real sampling denominators and probabilities. This is a proposed v1.1 choice, not an already executed change. Increase control coverage to expose prefilter misses.
5. **Size:** 150–300 prepared cases is a candidate-pool target; begin with 20–40 actual human judgments plus 10–20% blinded delayed repeats. Do not require the user to label 300 cases before testing the ontology. Repeat tasks never count as independent cases.
6. **Boundaries and subtypes:** use optional boundaries with null semantics for NOT_BOX/UNCERTAIN. Distinguish horizontal box, wide/drifting range and failed structure. Trend pullback and breakout/retest may be useful separate structures; they are not automatically BOX positives.
7. **Detection algorithms:** keep unchanged `loose_box_v1` for retrieval. Put robust quantile and pivot-cluster estimators behind one versioned interface. The REA pivot baseline is a comparator within this system, not another web app or duplicated detector stack.
8. **Causality:** model pivots by both event time and confirmation time. A 5/5 pivot becomes usable only after five right bars complete. Historical completed-window scoring and the UI's as-of-T partial week/month are different contracts and must be tested separately.
9. **Tool reuse:** assess existing Pandas/NumPy and available SciPy/scikit-learn components first. Evaluate the design brief's pytrendline/support_resistance references for license, maintenance, complexity and causal semantics before adopting code. REA is optional local UI inspection; its absence does not block the detector. This plan installs no dependencies.

## Proposed delivery sequence and stop gates

| Step | Concrete deliverable | Exit gate / next decision |
| --- | --- | --- |
| P0 — baseline audit | Exact PR #21 dependency receipt; current human/smoke counts, coverage, versions and gap register | Distinguish verified bug, design choice and data limit; preserve all v1 artifacts |
| P1 — labeling v1.1 foundation | Length-aware observed-step masks; separate coverage metadata; mask-aware encoder/pooling; versioned ontology, handbook and additive label storage | Partial real bars contribute; padding cannot change equivalent observed-input predictions; post-T changes leave T artifacts unchanged; regression + real browser smoke |
| P2 — independent structure detector | Small typed result contract; quantile baseline and pivot-zone comparator; bounded 8–26 completed-week searches within available prior 52 weeks; touches, swings, clarity, uniformity, expiry | Causal fixtures and negative controls pass; deterministic runtime/candidate counts on real permitted history; no human-accuracy claim yet |
| P3 — blinded human pilot | New versioned 150–300-case pool if safe coverage permits; first 20–40 human judgments; delayed repeats and independently chosen controls | Report real uncertainty/repeat agreement and boundary dispersion; revise ontology if unreliable; no invented numeric success threshold |
| P4 — structural comparison | Freeze detector settings before evaluating independent labeled groups; compare rule/base-rate, simple descriptor model and only then small CNN/TCN if authorized | Group/time-separated macro/class metrics, calibration, scale/stratum ablations and uncertainty; enough independent labels required |
| P5 — entry/outcome research | Separately authorized +5% event contract, valid T+1 entry and adverse/time barriers, missing/terminal treatment | Keep shape H separate from future Y; freeze definitions before inspecting outcomes; previously inspected Test/Fresh cannot be claimed untouched |
| P6 — execution validation | Frozen signals into existing local LEAN and existing Stock Radar result UI | Trusted execution-price/corporate-action gates and explained fills/costs; Cloud remains on hold unless separately cleared |

P1 can precede P2 because masks and label semantics do not depend on a better detector. P2 is deliberately small: first complete the two transparent baselines, then justify optional common-slope or multi-window variants. P3 may begin with an existing safe pool after P1 if detector work would delay feedback; freeze each pilot's sampling/version before annotation.

Training in P4 is **not** authorized by completing P1–P3. Start with the cheapest defensible comparator; a deep network must demonstrate value beyond simple models. A few dozen labels can test the workflow and ontology but cannot establish broad-market performance.

S1 stays outside this dependency chain. If activated later, first audit historical benchmark/peer availability, identity coverage and independent shock-date clusters. Today's industry codes cannot define historical peers; pre-T return-similarity peers are only statistical proxies. A credible NO_GO is an acceptable S1.0 result. Future-Y, GNN and profitability work require later gates.

## Recommended next bounded work order

Activate **P0 + P1 / BOX-LQ1 foundations** first when the owner asks to implement the next phase. Base code work explicitly on the verified PR #21 head; use one dependent implementation branch. If PR #21 remains unmerged, make that dependency visible in the PR rather than copying sources into main.

Expected scope: audit receipts; corrected partial-history representation; label v1.1 handbook/schema/storage compatibility; isolated human/smoke UI; targeted causal/mask tests; full regression and browser acceptance. Stop at pilot readiness. Neither real-label training nor detector expansion, future-Y or backtests belongs to this first work order.

Owner involvement begins with a small pilot after engineering readiness: judge structure and position, flag ambiguous definitions, then inspect aggregate reliability. The assistant handles candidate preparation and persistence; it cannot supply subjective human Ground Truth.

## Document and branch organization

The four source briefs are preserved with their dates/statuses. This page is the planning synthesis; [the proposal index](../codex/proposals/README.md) is the navigation hub. ACTIVE continues to point to the October 11 implementation order. This is not a second completion ledger.

Consolidation belongs to [PR #23](https://github.com/zhoushuming073-cell/stock-radar/pull/23). The box/range design file is copied byte-for-byte from `origin/docs/box-range-structure-codex-prompt-20261013`; REA is already in main. Retire redundant documentation branches only after verifying preservation. Keep experimental code branches with unique changes and local private-data worktrees. Historical acceptance files remain unchanged.
