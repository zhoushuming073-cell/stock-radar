# Box candidate Validation start and boundary parity — 2026-10-14

**Result: the first four frozen Validation sessions are independently verified,
and the first day's near-lower candidate contexts match a complete full-state
reference exactly.** This addendum extends the earlier three-day parity
receipt without changing its original dated evidence.

The `--verify-only` path reopened every candidate chunk from 2024-09-30
through 2024-10-03, recomputing eligible populations, T-only gate selections,
configuration/code/RI/runtime fingerprints and payload hashes. All 28 expected
chunks existed; none was missing. The first date is the frozen Validation
boundary. Its detector history can include earlier known lookback sessions,
but decision selection and the 20-bar gate end at that Validation T.

| Verified Validation prefix | Actual |
| --- | ---: |
| Trading sessions | 4 / 235 frozen Validation sessions |
| Eligible security-days | 15,920 |
| Sent to both full detectors | 6,581 |
| Certainly outside near-lower state | 9,339 |
| Near-lower union contexts | 464 |
| Verified / missing candidate chunks | 28 / 0 |

For 2024-09-30 alone, the complete independent full-state scan processed all
3,980 eligible rows in 16 immutable chunks. The existing comparator verified
both file sets and found **144/144 exact near-lower context matches**, including
detector-specific content. This is the fourth real comparison date; the four
dated comparisons together have 614/614 exact observed target rows. It does
not prove full-history parity or preservation of other detector states.

The full-state boundary-day detector compute took 852.976 s. The candidate
day was produced inside a multi-day background run, so isolated candidate
compute time and a speedup ratio are not reported. The remaining Validation
history continues to run in an independent low-priority private process.
Only [aggregate hashes and counts](../evidence/box-candidate-validation-start-2026-10-14.json)
enter Git. No future OHLCV value, outcome, human label, Test/Fresh decision,
portfolio order or box LEAN backtest was used. Official issuer identity,
raw-price/action/factor closure and frozen execution rules remain open.

Focused scanner/gate regression after this read-only addendum: **12 passed**.
Scanner and comparator source did not change from the earlier Native-inclusive
full project run (**793 passed, 8 skipped**); that historical result is not
presented as a newly executed full suite.
