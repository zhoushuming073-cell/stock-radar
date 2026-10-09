# Q1/Q2 Quant research v1

This is Quant-only Stage 1 research. No Vision/Human labels or future outcomes enter either selector. Strategy 2 and Research Infrastructure v1 remain frozen. No Fresh OOS claim or deployable trading edge is established.

## Q1: fuzzy-shape-v1

`radar.research.fuzzy_shape` is an independent copy of the accepted causal fuzzy feature calculation. It has no Vision import. The original `radar.vision.quant_features` remains byte-preserved for old labeling artifacts. The accepted score knots/weights are read from `config/quant_vision_labeling_v1.yaml`; they were not optimized on returns.

The dimensions are prior strength, pullback structure, exhaustion, OHLCV support proxies, early strengthening and extension. OHLCV support is not verified active buying. Primary ranking uses the 126-session window; 60-session parity is tested, not used to choose the best-looking score. Qualified: accepted Quant score >=65 with extension score <45; Wait: shape score >=55 with extension conflict >=45; Watch: Quant score >=50. Other rows are rejected. Bands classify candidate workflow and do not alter accepted feature scores.

Exactly equal outputs were checked on 50 actual frozen historical windows and with Hypothesis-generated 60/126-session inputs. Structural chart inspection is developer QA, not user H or accuracy labeling.

## Q2: parallel-channel-v1.1

Selectively derived from Draft PR #10, head `7bb27096fefa648f0074ea08ec67f787b10f3910`, not merged wholesale. Config: `config/parallel_channel_v1.yaml`. Existing log-price robust slope and quantile channel fits are retained. Review fixes:

- Position is consistently `log(C/L) / log(U/L)`.
- A mild lower-band undercut receives a continuous penalty; deeper breakdown is rejected.
- A confirmed local low, material rally to a confirmed high, subsequent retracement and current stabilization are separate causal stages. A token one-bar uptick is insufficient.
- Multiple windows must agree on direction, width and lower-band position. A single lucky window cannot qualify the setup.
- Weekly/monthly buckets record the actual last observation, bucket end and incomplete-period flag separately. Actual exchange sessions and early closes determine completeness.
- Monotonic decline, noisy false channels, future-prefix invariance and window disagreement are covered by tests.

New initial prominence/stability defaults have shape intuition, explicit version and configuration. They were chosen before any strategy portfolio outcomes. No optimization was performed to fill a Top 10 list. A valid empty Qualified list is expected when no confirmed setup exists.

## Common candidate contract

Pydantic `Candidate`: method/version, decision date, security ID, display symbol/name, score, rank, status, subscores, reasons, window metadata, quality flags and provenance. Finite scores only, no unknown extra fields. Ranking is method-local Qualified-first, score descending, stable private security ID tie break. Q1 and Q2 scores are not numerically comparable; overlap is membership, not Q3 or a combined alpha score.

Current and historical adapters are distinct:

- **Daily:** current Phase-1 eligible assets, latest completed session, homogeneous causal bar prefix, explicit current-membership/source-action limitations. Includes supported US equity-like assets, not a certified common-stock-only universe.
- **Historical:** frozen supported confirmed/probable membership at T; authoritative 126-session safe gate. Q2 requires an additional safe, homogeneous, contiguous long prefix of up to430 sessions. Unknown membership is excluded, never replaced with today's survivors. Historical normalized prices do not certify absolute-price/liquidity eligibility.

Data and candidate hashes are private; safe aggregate counts and acceptance evidence are public. Neither selector reads Y. Post-selection diagnostics reuse existing Scanner `build_labels` / `candidate_metrics`: 10-session +5% target-touch, Top5/10/20, ten-session security-ID event cooldown, same-T eligible background, no Top-K refill. Missing/unsafe future paths and raw split-crossing paths are censored and counted. These are vendor-price proxy research outcomes, not Human Ground Truth.

## Reproduction and boundaries

`scripts/run_quant_research.py` freezes source, config, Native identity, fees and data contract before execution. `--signals-only`, `--execute-only`, `--split train|validation`, `--method q1|q2` separate causal signals from later execution. Private outputs: `data/research/quant-research-v1/`. Existing artifacts are immutable; a drifted freeze fails closed.

The v1 pilot dates were selected before portfolio outcomes: Train signals2023-01-03–2023-02-15, reserved execution through2023-03-02; Validation signals2024-09-30–2024-11-12, reserved execution through2024-11-26. These bounded continuous intervals are not a full Train/Validation census. Historical Test and Fresh are NOT_RUN. Candidate source restrictions and missing data limit generalization.

See [Daily workflow](DAILY_QUANT_SCANNER.md), [local execution](Q1_Q2_LEAN_METHODOLOGY.md) and [Cloud status](Q1_Q2_QC_CLOUD.md). Actual pass/blocker and numerical outcomes belong to the dated acceptance report, not to this specification.
