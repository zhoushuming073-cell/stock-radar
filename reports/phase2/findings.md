# Phase 2A–2F preliminary findings

> Historical pre-v3 research artifact. Its split dates and name-based ETF/ETN filters are not the current Strategy Lab contract. See `config/research.yaml` and `docs/RESEARCH_PARAMETER_CONTRACT.md`. Numeric results below were not regenerated.

## Scope and data

The frozen local source database has 6,133,793 Alpaca SIP, split-adjusted daily
bars through 2026-09-24. SPY and QQQ each have 1,271 sessions from 2021-09-01.
The research run selected 2,000 current active, tradable major-exchange symbols
by recent dollar volume; 1,804 non-benchmark symbols in the database have at
least 1,000 sessions. The rest of the wider database mostly retains shorter
history. Three Alpaca rows (AVS, BLCR, SPCX) were rejected for VWAP=0.

The chronological Train sample ends 2024-08-28 after embargo. Validation runs
2024-09-27 to 2025-09-04 after embargo. The final Test starts 2025-09-19 and
has not been used for factor evaluation. There are 1,290,010 gated Train
symbol-days and 438,513 gated Validation symbol-days; these are overlapping
events, not independent trades.

## Elasticity movement capacity

| Validation group | Rows | 5d mean absolute close return | Diagnostic 5d MFE ≥5% | Executable TP ≤5d | Executable SL ≤5d |
|---|---:|---:|---:|---:|---:|
| Elasticity top 20% | 69,861 | 8.54% | 58.3% | 45.3% | 17.2% |
| Elasticity bottom 20% | 70,184 | 1.35% | 2.5% | 1.8% | 0.7% |

This supports Elasticity as a **movement-capacity** measure in this sample. It
does not establish a profitable entry strategy. The top group also has much
higher stop incidence. Elasticity and ATR%20 have Train Spearman correlation
0.902, so the composite may double-count volatility; validate incremental
information before locking its weights.

## Strategy 2 factors

Deep 20-day pullback (lowest drawdown quintile) had 48.4% diagnostic MFE ≥5%
on Validation, versus 11.3% for the shallowest quintile. The Elasticity plus
deep-drawdown exploratory intersection reached 60.1%, with 46.6% executable
TP and 18.4% executable SL within five sessions. That is a high-movement,
high-risk region, not yet a complete signal.

High prior 60-day return, large lower wick, and volume contraction did not
show a clear incremental improvement in the univariate or simple interaction
tables. In Validation, the highest prior-return quintile had 32.1% diagnostic
MFE ≥5%, versus 42.7% for the lowest quintile. Adding a high prior-return
condition to Elasticity plus drawdown did not improve executable outcome rates
materially. This challenges the presumed prior-strength requirement; it needs
conditional research before being made a hard filter.

Illustrative $10,000 whole-share event trades with the **unconfirmed** fee
profile and 20 bps slippage per side had a 4.68% median net outcome for the
Validation Elasticity top-20% group. This is per-event outcome conditioned on
the 10-session exit rule. It omits competing signals, position overlap, cash
limits, allocation, and portfolio drawdown; it is **not** a portfolio return.
All 0/5/10/20 bps scenarios are in the CSVs.

## Security-universe sensitivity

The current Alpaca `us_equity` master does not reliably distinguish common
stock from funds and related securities. Of the 2,000 selected symbols, 418
have `ETF` in their names and four have `ETN`; this is only a name-based hint.
After excluding names explicitly indicating ETF/ETN, Validation Elasticity
top-20% still showed 58.0% diagnostic MFE ≥5% and 44.8% executable TP ≤5d.
The sensitivity is encouraging but is not a point-in-time stock-only universe.

## Decision at the Phase 2F stop

Keep Elasticity and pullback depth as research candidates. Do not freeze a
Strategy 2 score or portfolio logic yet. Investigate volatility redundancy,
conditional prior strength, entry gap effects, point-in-time security type and
survivorship, and the user's actual fee plan. Final Test remains sealed until
the rules and cost assumptions are fixed.

All figures are descriptive associations for a current-snapshot universe.
The factor and interaction CSVs contain the exact counts, outcome denominators,
Train/Validation buckets, and cost scenarios.
