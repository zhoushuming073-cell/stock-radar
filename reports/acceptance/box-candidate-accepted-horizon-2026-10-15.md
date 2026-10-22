# Box candidate accepted-price horizon metadata audit — 2026-10-15

**Result: 18/18 previously T-day-matched candidates have matching accepted
raw-price *metadata* records on each of the next ten in-split exchange
sessions (180/180 records).** This is a bounded coverage diagnostic, not a
ten-day holding rule, a price-series reconciliation, or LEAN readiness.

The read-only `box-candidate-accepted-horizon-v1` auditor starts from the
four sealed Train/Validation source-gate days. It reuses the hash-bound
[T-day accepted-price bridge](box-candidate-tday-price-bridge-2026-10-15.md)
to select only the 18 exact private security-ID/date/symbol/OHLCV matches.
For subsequent sessions it queries only the accepted database's `symbol`,
`provider`, `feed` and `adjustment` fields. It selects session dates from
the frozen Research Infrastructure v1 calendar and stops at each split end.
It does not select future OHLCV values or future outcomes. The accepted
database, gate evidence, candidate files, private issuer/horizon receipts,
frozen RI semantic hash and both auditor versions are bound by SHA-256 in
[aggregate evidence](../evidence/box-candidate-accepted-horizon-2026-10-15.json).
No private security identifier, price, signal, account detail or historical
mapping is published in that evidence.

| Previously audited split/date | Exact T-day matches | In-split sessions checked | Matching Dolt/raw records | Known symbol transitions |
| --- | ---: | ---: | ---: | ---: |
| Train 2022-05-04 | 0 | 0 | 0 | 0 |
| Train 2024-07-01 | 5 | 50 | 50 | 0 |
| Validation 2024-10-28 | 10 | 100 | 100 | 0 |
| Validation 2025-06-02 | 3 | 30 | 30 | 0 |
| **Total** | **18** | **180** | **180** | **0** |

This only shows that dated rows with the expected accepted raw provenance
exist for those 18 names. The future-session OHLCV values have **not** been
compared with the candidate database, and the rows have not passed official
issuer identity, corporate-action/factor completeness, delisting/terminal
handling, benchmark, full signal-stream or portfolio execution gates. The
33 other selected Dolt/raw candidates still lack accepted T-day rows. The
four dates were nonrandom and neither the 18/18 nor the 180/180 figure may
be extrapolated to the unfinished Train/Validation scans. This audit did not
launch a LEAN run, inspect returns, or use Test/Fresh data.

Focused auditor/source-gate tests: **8 passed**. The new tests use a DuckDB
fixture without OHLCV columns to prove the post-T query needs no price
values, and cover missing, duplicate, wrong-provenance and symbol-transition
records. A real local audit produced the linked evidence. Full-project
regression was run with `STOCK_RADAR_TEST_LEAN=1`.

**Regression: 810 passed, 8 skipped, 1 existing `websockets.legacy`
deprecation warning.** Native LEAN fixture tests were enabled; no box
portfolio backtest ran.

Candidate scanner/gate code, frozen research data and existing private
receipts were not modified. Both immutable background candidate scans
continue. Formal LEAN remains blocked; the next data gate is independent
price/action/factor and issuer certification rather than relaxing the
current constraints.
