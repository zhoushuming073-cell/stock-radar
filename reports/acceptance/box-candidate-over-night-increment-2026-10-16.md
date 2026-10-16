# Box candidate overnight adjacent-segment verification — 2026-10-16

**Result: independently verified new Train and Validation candidate chunks now extend the adjoining covered intervals to 453/753 and 189/235 frozen sessions.** The unchanged `box-candidate-source-basis-audit-v2` checked only days after the prior 365/120-session checkpoint: Train 2023-02-14–2023-06-21 (88 sessions) and Validation 2025-03-25–2025-07-02 (69 sessions). Both background workers remained live. The current incomplete day folders were excluded.

| Newly verified interval | Train | Validation |
| --- | ---: | ---: |
| Sessions | 88 | 69 |
| Eligible security-days | 290,493 | 269,274 |
| Verified chunks | 548 | 508 |
| Near-lower contexts | 11,970 | 8,984 |
| Legacy Alpaca SIP / split | 11,970 | 8,029 |
| Dolt / raw | 0 | 955 |

Each increment passed the scanner's read-only `--verify-only` path and the separate file-set SHA-256, source/basis and count audit. [Aggregate evidence](../evidence/box-candidate-over-night-increment-2026-10-16.json) contains both verified segment hashes and source versions; private security/date mappings and prices remain ignored local data. The previous [365/120 checkpoint](box-candidate-segment-increment-2026-10-15.md) ends immediately before these segments. Arithmetic across the separately verified, nonoverlapping intervals yields:

| Adjoining verified coverage | Train | Validation |
| --- | ---: | ---: |
| Frozen sessions | **453/753 (60.2%)** | **189/235 (80.4%)** |
| Eligible security-days | 1,065,978 | 744,079 |
| Verified chunks | 2,074 | 1,389 |
| Near-lower contexts | 44,845 | 26,700 |

These are engineering coverage figures, not whole-project completion, detector structure accuracy, order signals or return evidence. Train remains on split-adjusted legacy source series, except five previously documented public-EOD contexts. Validation combines source-separated legacy split and Dolt raw contexts; no series are stitched for execution. Full Train/Validation scans, official historical identity, accepted same-source execution prices and corporate actions/factors, complete signals and frozen portfolio rules remain open. No future OHLCV values, outcomes, Test/Fresh, human labels or box LEAN portfolio backtest were used.

No code changed for this data-only checkpoint. The two successful real read-only verifications and aggregate hash/count checks are its acceptance. The latest full Native-inclusive project regression remains **818 passed, 8 skipped, one existing warning**; it was not repeated for unchanged code.
