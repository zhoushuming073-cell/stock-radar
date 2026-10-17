# Box candidate high-density Validation parity — 2026-10-15

**Result: all 225 near-lower contexts on the highest-count day of the
verified Validation prefix exactly match a complete independent full-state
scan.** This extends observed target-state preservation across density and
split boundaries, but does not prove all-date parity, preserve non-target
states, certify detector structure truth or measure returns.

The Validation date 2024-10-28 was selected from the complete, verified
candidate prefix through that date **before** its full-state run. The full
scanner processed every one of 3,995 eligible security-days among 4,500
indexed, producing 16 immutable private chunks. Its total new detector
compute was 827.722 seconds across a one-chunk bounded start and the
remaining 15-chunk run. The independent comparator reopened both complete
file sets, checked their provenance and denominators, filtered the full scan
to the exact target state, and required equality of each private context row
including detector-specific content.

| 2024-10-28 Validation reference | Observed |
| --- | ---: |
| Indexed / eligible security-days | 4,500 / 3,995 |
| Necessary gate possible / certainly not | 2,510 / 1,485 |
| Full-state verified chunks | 16 / 16 |
| Candidate / full-state near-lower contexts | 225 / 225 |
| Exact private context equality | Yes |
| Provider exclusions | 0 |

The previous five complete reference dates matched 927/927 observed target
rows. This sixth date raises the bounded comparison total to **1,152/1,152**.
The [public evidence](../evidence/box-candidate-validation-high-density-parity-2026-10-15.json)
binds both private file-set hashes, source versions and aggregate counts;
identities and price rows remain only in ignored local `data`.

Focused scanner/gate tests: **14 passed**. No source changed, so the last
full Native-inclusive project regression remains **795 passed, 8 skipped**;
it was not rerun for this data-only comparison. The high-density issuer/raw
metadata audit on the same date remains a separate dependency finding:
26 candidates are only observationally conflict-free and metadata-complete,
not officially identified or LEAN-ready. Both long-running Train/Validation
candidate scans remain separate. No future OHLCV values, outcomes, human
labels, Test/Fresh decisions or box LEAN portfolio run entered the parity
comparison.
