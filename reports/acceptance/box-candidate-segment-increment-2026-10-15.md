# Box candidate adjacent-segment verification — 2026-10-15

**Result: the unchanged read-only source/basis verifier passed the new days immediately after the prior 358/115-session checkpoint.** Train added seven frozen sessions through 2023-02-13 and Validation added five through 2025-03-24. The current-day folders were excluded. The immutable low-priority workers remain live.

| Newly verified, nonoverlapping interval | Train | Validation |
| --- | ---: | ---: |
| Sessions | 7 | 5 |
| Eligible security-days | 22,936 | 19,593 |
| Verified chunks | 40 | 44 |
| Near-lower contexts | 399 | 1,269 |
| Legacy Alpaca SIP / split | 399 | 1,161 |
| Dolt / raw | 0 | 108 |

Each new interval independently passed the scanner's `--verify-only` path, then exact candidate file-set hashes and source/basis counts. [Aggregate evidence](../evidence/box-candidate-segment-increment-2026-10-15.json) records both segment hashes and source version, without private identities or price rows. The [preceding checkpoint](box-candidate-continuous-prefix-358-115-2026-10-15.md) ends on the immediately prior frozen session in each split. Its separately verified totals plus these nonoverlapping increments cover **Train 365/753 sessions** (1,526 chunks, 32,875 contexts) and **Validation 120/235 sessions** (881 chunks, 17,716 contexts). This is arithmetic across independently verified adjoining intervals, not a newly computed whole-prefix file-set hash.

Scan coverage is now 48.5% of Train and 51.1% of Validation sessions. It is not total project completion. Contexts remain research observations, not structure truth, order signals or return evidence. Train remains exclusively split-adjusted legacy sources in this interval; source substitution for execution is not implied. No future OHLCV values, outcomes, Test/Fresh, human labels or box LEAN portfolio run were used. Official issuer identity, accepted raw execution prices, corporate actions/factors, complete signals and frozen portfolio rules remain open.

No code changed. The two real read-only verifications and their count/hash checks are the data acceptance for this increment. The latest full Native-inclusive project regression remains **815 passed, 8 skipped, one existing warning**; it was not rerun for unchanged code.
