# Frozen Q1/Q2 local LEAN pilot

Stock Radar is the only selector. Independent Native QuantConnect LEAN consumes fixed signals and owns portfolio cash, positions, orders, fills and fees. LEAN never imports Q1/Q2 selection logic. The configurable independent installation remains outside this repository (this machine: `D:\QuantConnect-LEAN`).

Primary contract: per-method Qualified Top10, T+1 regular-open daily proxy, maximum10 positions, equal available cash across remaining slots, no overlapping holding of the same security, no hidden replacement from lower ranks, exit at the **tenth holding-session close**, no TP/SL optimization. Native MarketOnClose orders are submitted before the close; actual16:00 and early13:00 closes are tested. There is no anticipation of the closing fill price.

Freeze records selectors/configurations, historical membership semantic hash, source revision, engine commit/DLL identity, execution,10bps slippage and existing fee profile. Fees remain illustrative/unconfirmed. A freeze drift blocks execution. Prices, signal manifests, aliases, journals and original Native output stay private. The adapter reconciles Native orders, fills, fees and final equity before publishing to the existing Run History/Backtest/Compare.

This is explicitly **bounded Shape Research exploratory proxy simulation**, `universe_mode=shape_research_v1`; it is not the existing formal raw PIT domain. The strict formal PIT gate remains unchanged. Unsupported source switches, unsafe identity/class boundaries, missing required entry/holding/exit bars or raw splits inside any possible holding dependency block the entire method. Difficult candidates are not removed using future data. A raw action outside all possible holdings does not create an execution dependency.

Homogeneous vendor split-adjusted units are usable only with explicit adjustment/share/fee bias limitations. Dividends, unknown corporate actions, terminal entitlements, actual auction microstructure and intraday liquidity are not certified. Stable private security aliases prevent ticker reuse from merging identities. Missing ticker/issuer continuity remains a reported research limitation.

The fixed-horizon execution adapter is separate from `radar.lean.algorithm`: the old Native/QC frozen campaign source is byte-preserved. Generic exports select the new variant only for this explicit execution timing. Frozen Strategy2 and old QC manifests are not rewritten to fit this pilot.

Result schema and existing UI are retained. Metrics include Native equity/drawdown, return, SPY benchmark, Sharpe/Sortino where computable, fees, turnover, trade count/win rate and trade-return distribution. CAGR is null for pilots shorter than252 sessions. Cost addback uses actual filled quantities and is labeled attribution, not a no-cost counterfactual portfolio. Candidate MFE/MAE/Precision/Lift/event cooldown are separate post-selection analytics; they do not drive execution.

Train runs before Validation; dates and reserved final10-session windows are listed in [research contract](Q1_Q2_QUANT_RESEARCH.md). Historical Test/Fresh are not evaluated. A sparse Q2 portfolio is a result to report, not justification to tune its gate.

## Private execution dependency audit

Run `.venv\Scripts\python.exe scripts/audit_quant_execution_closure.py` from the repository root. It verifies the existing frozen receipt/kernel, reconstructs exact ten-session dependencies and writes an immutable content-addressed private worksheet. The printed counts are diagnostics, not a price-acceptance certificate. Original-byte hashes, full OHLCV comparisons, dated security continuity and corporate actions must bind to a validated versioned supplement before execution; matching closes or a news explanation alone cannot clear existing safety flags. No source/basis conversion or frozen-database edit is performed.
