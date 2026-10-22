# Box candidate Validation-prefix T-day accepted-price overlap — 2026-10-15

**Result: 549/1,531 Dolt/raw candidate-days in the sealed 77-session
Validation prefix have an exact T-day match in the separate accepted
Research-grade raw-price database; 982/1,531 have no accepted row for the
same private security ID and decision date.** None of the matched rows had
a symbol, provenance or OHLCV mismatch. This is a price-coverage finding,
not identity or execution certification.

The read-only `box-candidate-prefix-tday-v1` auditor first invokes the
unchanged candidate source auditor's full `--verify-only` path for
2024-09-30–2025-01-21, confirming all 580 private chunk files and binding
their ordered SHA-256 set. It then re-reads that same file set, selects only
`Dolt:post-no-preference/stocks / raw` candidate contexts, and compares
`security_id`, date, symbol, OHLCV and accepted provenance at **decision
date T only**. The accepted database and its manifest are SHA-256 checked.
No ticker-only, legacy-source or split-adjusted fallback is used.

| Validation-prefix measure | Observed |
| --- | ---: |
| Frozen sessions | 77/235 |
| Dolt/raw candidate-days | 1,531 |
| Days with Dolt/raw candidates | 77 |
| Exact accepted T-day matches | 549 |
| Accepted T-day row missing | 982 |
| Other T-day discrepancies | 0 |

The counts and source hashes are in [aggregate evidence](../evidence/box-candidate-prefix-tday-2026-10-15.json).
Private security IDs, symbols, prices and candidate-date mappings remain
only in ignored local data. The 1,531 population has **not** been filtered
for the as-of-T issuer-risk or complete same-source execution-horizon gates.
It is therefore broader than the earlier four-day 51-candidate intersection
and its 18 accepted T-day matches. These counts must not be treated as an
officially eligible or tradable population. Train candidates in the verified
prefix use legacy split-adjusted sources, so they are not silently bridged
into this Dolt/raw comparison.

The new test checks that changing T+1 prices cannot change a T-day result
and that legacy-source candidates are not included. Focused bridge tests:
**6 passed**. The actual audit completed on the local frozen database and
produced the linked evidence. Full regression used
`STOCK_RADAR_TEST_LEAN=1` to include Native LEAN fixture tests.

**Regression: 811 passed, 8 skipped, 1 existing `websockets.legacy`
deprecation warning.** No box portfolio backtest ran.

The auditor did not read T+1 OHLCV values, future outcomes, Test/Fresh
data or human labels, and it did not run LEAN. Official issuer identity,
accepted raw prices throughout the execution period, corporate
actions/factors, complete signal stream and portfolio rules remain open.
The immutable Train/Validation background candidate writers continue.
