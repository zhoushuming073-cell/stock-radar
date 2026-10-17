# Box candidate T-day accepted-price overlap — 2026-10-15

**Result: same-source raw metadata coverage does not imply coverage by the
separately accepted Research-grade raw-price database.** Among 51 Dolt/raw
candidates previously classified as observationally having no known issuer
conflict and a complete ten-session same-source raw **metadata** horizon,
only 18 have a single matching accepted-price record on decision date T.
The other 33 have no accepted-price row for the same private security ID and
date. The 18 matched rows have exactly equal T-day symbol and OHLCV values
and the accepted `Dolt / post-no-preference/stocks / raw` provenance fields.

The new `box-candidate-tday-price-bridge-v1` read-only auditor verifies the
four sealed candidate/issuer/horizon populations by their prior hashes,
rechecks the frozen Research Infrastructure v1 semantic hash, and streams
the accepted-price database SHA-256 from its local manifest before querying.
It requires an exact `security_id` and T-date match; there is no ticker-only
or alternative-source fallback. SQL selects **only decision date T**, so it
does not read post-T OHLCV values or outcomes. Only aggregate counts and
hashes are published in [the evidence](../evidence/box-candidate-tday-price-bridge-2026-10-15.json).

| Previously audited split/date | Selected Dolt candidates | Exact T-day accepted-price match | Missing accepted T-day row |
| --- | ---: | ---: | ---: |
| Train 2022-05-04 | 0 | 0 | 0 |
| Train 2024-07-01 | 15 | 5 | 10 |
| Validation 2024-10-28 | 26 | 10 | 16 |
| Validation 2025-06-02 | 10 | 3 | 7 |
| **Total** | **51** | **18** | **33** |

The accepted-price manifest itself labels its rows as accepted prices with
portfolio readiness separate. Its database contains daily bars, while the
formal PIT preflight additionally requires verified issuer/class mappings,
licensed raw coverage for every required session, complete action evidence,
terminal handling, benchmark and LEAN input reconciliation. This T-day audit
does **not** inspect the later OHLCV series or certify dividends, splits,
factors, delistings or executable prices. It does not make even the 18 matched
rows LEAN-ready. The 51 selected rows are from four nonrandom days and cannot
be extrapolated to the full unfinished Train/Validation scans.

Focused bridge/source-gate tests: **8 passed**, including T+1 mutation
invariance, same-day value drift, missing/duplicate rows, wrong provenance,
database hash drift and a private-path restriction. Full project regression
with `STOCK_RADAR_TEST_LEAN=1`: **808 passed, 8 skipped, 1 existing
`websockets.legacy` deprecation warning**. Native LEAN fixture tests were
enabled; no box portfolio backtest ran. Candidate scanner,
frozen research database and prior private receipts were unchanged. No
orders, return metric, Test/Fresh rows, human-label substitution or box LEAN
backtest was involved.
