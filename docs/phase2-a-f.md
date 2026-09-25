# Phase 2A–2F research handoff

This implementation follows `../../stock_radar_phase2_backtest_spec.md` through
Phase 2F. It does **not** define the final Strategy 2 rank, capital allocator,
or portfolio backtest. Those require a review of the exploratory evidence.

## Local data and reproducibility

The live daily updater still writes `data/market.duckdb`. The five-year research
backfill and derived tables are in `data/phase2-research.duckdb`. The backfill
script copies the live database on first run and refuses the live path as its
output. Both database files stay local and are excluded by `.gitignore`.

```powershell
.\.venv\Scripts\python.exe scripts\backfill_research.py --max-symbols 2000 --start 2021-09-01 --end 2026-09-24
.\.venv\Scripts\python.exe scripts\build_research.py --max-symbols 2000
.\.venv\Scripts\python.exe scripts\factor_study.py
.\.venv\Scripts\python.exe scripts\audit_phase2_data.py
.\.venv\Scripts\python.exe -m pytest -q
```

The backfill uses the existing Alpaca SIP, split-adjusted daily-bar provider and
ingestion code. Symbols are selected by recent dollar volume from the current
asset snapshot; this is a practical research subset, **not** a point-in-time
historical universe. SPY and QQQ are benchmarks even though they are ETFs.

The frozen local source snapshot is
`data/phase2-source-snapshot.duckdb`. Its SHA-256 is recorded in
`reports/phase2/data_snapshot.txt`. It was copied after backfill, then the
earlier exploratory feature, label, and run tables were removed. `daily_bars`
and `assets` are the frozen source inputs for this run.

## Causality contract

- Features on date `t` use only observations through the close of `t`.
- Historical five-session burst outcomes are shifted by five sessions before
  entering an Elasticity feature.
- Stocks and QQQ are aligned to the SPY session calendar; missing bars are not
  filled.
- Labels are separate from features. The entry reference is next-session
  Open. Executable exits use only Open and Close; High and Low appear only in
  diagnostic MFE/MAE labels.
- No final-test bars are passed to the forward-label engine. The event study
  reads Train and Validation only, with a ten-session embargo at boundaries.
- Same-date Elasticity percentiles use the selected current-snapshot universe.
  Their rank depends on this cohort and should be rebuilt if it changes.

## Research outputs

- `reports/phase2/data_audit.json`: data dates, provenance, coverage, raw
  anomalies, and coarse security-type audit.
- `reports/phase2/elasticity_distribution.csv`: movement capacity by score
  band on Train and Validation.
- `reports/phase2/strategy2_factor_study.csv`: Train-fitted factor buckets,
  applied unchanged to Validation.
- `reports/phase2/strategy2_interaction_study.csv`: exploratory overlaps of
  Elasticity, drawdown, prior return, and wick.
- `reports/phase2/factor_spearman_train.csv`: factor redundancy check.
- `reports/phase2/security_name_proxy_sensitivity.csv`: sensitivity after
  removing names explicitly indicating ETF/ETN; this is not a validated
  security classification.
- `reports/phase2/strategy2_factor_study_metadata.yaml`: split dates, cohort,
  fixed exploratory thresholds, and caveats.
- `reports/phase2/findings.md`: interpretation and Phase 2F stop decision.

Costs shown in the event-study CSVs are sensitivity scenarios for a $10,000
whole-share order under the **unconfirmed** uSMART US-stock PRO profile copied
from the Phase 2 specification. The user's actual account plan, portfolio
allocation, overlapping holdings, and cash drag are not modeled yet.

## Limits before 2G–2I

The current active asset list has survivorship bias. `us_equity` contains ETFs
and other securities; name matching can flag some, but is not a dependable
common-stock classifier. This work keeps the coarse universe and labels the
limitation. Backfill rejects provider bars with invalid VWAP rather than
silently accepting them. Event rows overlap in time and should not be treated
as independent trials. Test-period performance has not been examined.
