# Box near-lower gate implication audit — 2026-10-15

**Result: the unchanged Stage D necessary gate passed a cross-module
implication test and an independent high-density real-data exclusion audit.**
No scanner, gate, Stage C context or immutable candidate receipt was changed.

The gate excludes only when a condition necessary to Stage C's
`NEAR_LOWER_STABILIZING` state is violated: final-day and three-day extension,
final-day decline, recent-low decline, missing volume baseline or excessive
volume ratio. Stage C also tests geometry and headroom; omitting those from
the fast gate makes it conservative. The bulk T-only query requires 20
contiguous, dated, source/basis-matched, ready sessions; any untrusted or
unknown recent prefix is retained for the full detector.

The new cross-module test constructs a provenance-bound, simulated confirmed
range and calls the actual Stage C `assess_lower_band` and Stage D
`necessary_near_lower` implementations. A deterministic positive case ensures
the implication is not vacuous, then Hypothesis checks 200 deterministic
generated OHLCV scenarios. The combined focused gate/context suite passed
**11 tests**. This checks the metric/state implication; simulated confirmed
ranges do not validate real box recognition.

Separately, the existing independent gate auditor reopened the sealed
full-state Train 2022-10-03 reference. It observed 3,258 eligible
security-days with 3,258 trusted recent prefixes. The gate retained 2,037
and excluded 1,221; **all 437** full-state near-lower contexts were in the
retained set, with **zero observed false exclusions**. Rejection reason
counts overlap and therefore do not sum to 1,221. Source and file-set hashes
are in [public evidence](../evidence/box-fast-gate-implication-2026-10-15.json);
private identities and OHLCV remain in ignored local `data`.

Full project regression with `STOCK_RADAR_TEST_LEAN=1`: **805 passed, 8
skipped, 1 existing `websockets.legacy` deprecation warning**. The Native
LEAN fixture path was enabled; no box portfolio backtest ran.
This audit is stronger evidence for the necessary-condition optimization,
not a proof of all-date pipeline parity, other detector states, structure
truth or returns. Full Train/Validation coverage and official issuer/raw
execution-data gates remain open. No human labels, future outcomes,
Test/Fresh data or box LEAN portfolio backtest were used.
