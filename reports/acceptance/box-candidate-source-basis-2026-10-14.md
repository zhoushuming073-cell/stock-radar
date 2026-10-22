# Box candidate source/basis provenance — 2026-10-14

**Result: the current frozen research-price source/basis contract is a
structural obstacle to same-source raw execution data for most candidates.**
This is a read-only provenance and coverage finding, not a rule change or a
claim about candidate quality or portfolio returns.

The new `scripts/audit_box_candidate_source_basis.py` first runs the existing
`--verify-only` scanner, then reopens exactly those private chunks and matches
their ordered file-set SHA-256 and near-lower count before producing aggregate
source/basis counts. No identity, ticker, OHLCV value, human label or future
outcome enters its public output. [Aggregate evidence](../evidence/box-candidate-source-basis-2026-10-14.json)
binds the result to the RI semantic hash, auditor source hash and both verified
private file sets.

| Continuous verified prefix | Train 2021-09-01–2022-07-22 | Validation 2024-09-30–2024-10-09 |
| --- | ---: | ---: |
| Frozen sessions | 224 / 753 | 8 / 235 |
| Verified chunks | 668 / 668 | 62 / 62 |
| Near-lower contexts | 14,358 | 1,140 |
| `legacy:alpaca:sip` / `split` | 14,357 | 965 |
| `legacy:post-no-preference/stocks:public_eod` / `split` | 1 | 0 |
| `Dolt:post-no-preference/stocks` / `raw` | 0 | 175 |

An independent read-only `shape_price` aggregate grouped by year, source and
basis found only one security in the `Alpaca SIP` raw series during 2021–2023:
85 rows in late 2021, 251 in 2022 and 83 through 2023-05-02. It found no
`legacy:alpaca:sip` raw row anywhere in the checked frozen Train/Validation
range. `Dolt:post-no-preference/stocks` raw begins on 2023-12-12 in this
research snapshot, with 62,865 rows in the remainder of 2023, 1,269,028 in
2024 and 875,619 through 2025-09-08. These are database row counts, not an
official full-market population or quality certificate.

The [cross-era candidate audit](box-candidate-cross-era-gates-2026-10-14.md)
independently found 0/2,280 same-source raw follow-up sessions for 2022 Train
and 243/1,440 for the 2024 Validation boundary; all 24 complete raw horizons
on the latter day came from `Dolt` raw candidates, while 119 `legacy:alpaca:sip`
split candidates had none. Thus merely finding a raw row under another source
does not close the current execution contract. Cross-source raw substitution
would require a new, explicitly versioned price/identity/action reconciliation
contract and acceptance; this audit does **not** adopt that design. Official
historical identity, corporate actions/factors, execution and portfolio rules
remain open. No box LEAN, QC, Historical Test/Fresh or future-outcome run was
performed.

## Regression

The focused source-audit/scanner tests passed (**6 passed**). Full project
pytest with `STOCK_RADAR_TEST_LEAN=1` passed **795 tests, 8 skipped**, with one
existing `websockets.legacy` deprecation warning in 149.05 s. The opt-in
native LEAN fixture tests were enabled; no box portfolio backtest was run.
