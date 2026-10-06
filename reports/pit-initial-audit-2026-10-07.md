# PIT migration: initial source-code and database audit

Audit baseline: `3521ce3a998679ddfcc05d9b142dff56e8e6036d`, verified against
`origin/main`. This document records the pre-implementation state; the final
acceptance report records subsequent changes. All four existing DuckDB stores
were inspected with `read_only=True`; their hashes are retained locally in
`data/pit/reports/original-database-hashes.json`.

1. **Current Snapshot origin.** `AlpacaProvider.get_assets()` requests only
   active US equities. `run_sync()` upserts these into `assets`; the initial
   live universe additionally requires current tradability and major exchanges.
   Research backfill and feature construction independently select the active
   asset cohort. The latter is the historical Scanner's surviving population.
2. **Current metadata.** Name, exchange, asset class, status, tradability,
   fractionability, shortability and borrowing fields are mutable observations.
   `first_seen` is ingestion time, not an IPO date. The asset primary key is
   `symbol`; no stable security identity is present in raw prices or features.
3. **Daily Scanner eligibility.** Causal `tradability_pass` uses that date's
   close, trailing ADV20 and observed-history count. Required numerical features
   must be finite. Current exchange/tradability do not define historical daily
   eligibility, but the feature population was already restricted to survivors.
4. **Remaining bias.** Missing historical listings/retired tickers, current
   cohort selection, symbol-keyed feature histories, vendor ticker remapping,
   retroactively split-adjusted prices, and missing terminal economics remain.
   Filtering a survivor-built feature table through PIT does not reconstruct
   the missing cross-section or recompute its percentile ranks.
5. **Existing PIT capabilities.** Dated CSV mappings, stable IDs at the adapter
   boundary, overlap/coverage checks, source hashes and queued-source rejection;
   Scanner labels follow identity over renames. Optional terminal policy values
   explicit USD cash acquisition evidence only. Formal readiness remains gated.
6. **Missing code and data.** No real historical importer or complete external
   master is installed. Local security-master and terminal-event files are
   absent. The research builder still selects current active assets and rolls
   by ticker. Both data acquisition and causal identity-safe feature plumbing
   require work. LEAN explicitly rejects PIT at queue and execution time; this
   fail-safe must remain.
7. **Price coverage.** Live bars: 4,644,042 rows / 13,274 tickers through
   2026-10-05. Research bars: 12,151,417 rows / 13,564 tickers through
   2026-09-28. Both start 2021-09-01 and use Alpaca/SIP/split. All stored assets
   are active; extra research tickers do not prove retired-security coverage.
   Existing prices cannot establish complete delisted OHLCV or terminal payouts.

The frozen v2 research and source snapshot remain comparison evidence. The
strategy, parameters, UI and LEAN selection/execution logic are outside this
migration's scope. Synthetic tests demonstrate software behavior, not complete
real-world identities or membership.
