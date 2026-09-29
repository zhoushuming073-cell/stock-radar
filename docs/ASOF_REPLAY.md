# Strict As-Of Daily Replay

The current-snapshot research mode first freezes a current active US-equity
survivor cohort. For each signal date `t`, membership in `U_t` then depends only
on a bar observed at `t`, the price at `t`, trailing ADV20, and the number of
historical observed sessions through `t`. The current asset's `tradable` and
`exchange` fields do not act as historical state. Elasticity components are
ranked within `U_t` on each date; breadth counts only eligible members with a
known MA20 distance.

`radar.research.asof.strict_asof_day` reads bars with `date <= t` and
recalculates that day's features, eligibility, Elasticity, and breadth. The
materialized pipeline remains the fast engine. `strict_strategy_day` passes
those recalculated features through the production plugin adapter, allowing
candidate scores and ranks to be compared too. `tests/test_asof_replay.py`
compares both engines, then mutates all later stock and SPY/QQQ bars plus the
current mutable trading metadata and checks that the earlier outputs remain
unchanged.

`scripts/verify_asof_build.py --database <candidate> --day YYYY-MM-DD` is the
read-only promotion gate. It requires a full-cohort completed build and compares
the strict and fast engines on the specified historical dates. Sample dates
should include Train and Validation, with at least one random date. A Test date
may be checked for implementation parity without examining performance.

The v3 table was built separately from the v2 table and promoted after
full-cohort backfill and three real-date strict replay checks. The frozen v2
database is retained in `data/phase2-research-v2-frozen.duckdb`. A
`--max-symbols` build is incomplete and cannot be promoted. The daily Alpaca
task updates `market.duckdb`; research data is refreshed through a separately
recorded backfill/build, preserving the data snapshot used by earlier runs.

This does not remove survivor bias, retroactive vendor bar revisions, or
researcher exposure to the old Test slice. Formal PIT membership requires a
verified historical Security Master and terminal-event source. New rolling ML
must enforce label maturity and As-Of fitting. ES/NQ/YM features need an
explicit timestamp gate before they can enter strategy context.
