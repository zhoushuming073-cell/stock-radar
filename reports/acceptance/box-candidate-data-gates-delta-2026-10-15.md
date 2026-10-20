# Box candidate Validation data-gate increment — 2026-10-15

**Result: 38 newly sealed Validation sessions add 690 Dolt/raw candidate-days to the prior 77-session audit.** The unchanged read-only `box-candidate-prefix-data-gates-v1` auditor independently verified 2025-01-22–2025-03-17, checked candidate and source hashes, and intersected accepted T-day price status, decision-dated issuer observations, and ten-session same-source raw **metadata**. This increment does not rescan the earlier 77 days.

| New 38-session interval | Raw metadata complete | Incomplete | Total |
| --- | ---: | ---: | ---: |
| Exact accepted T-day price; no known issuer conflict observed | 239 | 0 | 239 |
| Exact accepted T-day price; contemporaneous issuer alias | 10 | 0 | 10 |
| Missing accepted T-day row; no known issuer conflict observed | 373 | 19 | 392 |
| Missing accepted T-day row; contemporaneous issuer alias | 22 | 11 | 33 |
| Missing accepted T-day row; known identity conflict | 16 | 0 | 16 |
| **Total** | **660** | **30** | **690** |

The 690 candidates imply 6,900 diagnostic in-split session slots; 6,860 have a same-source raw metadata record. Overlapping issue counters show 40 unavailable/ambiguous raw slots and 29 not research-ready slots. No split-censored task was observed. These counters are slot-level and can overlap; they are not numbers of distinct candidate-days.

The [previous 77-session audit](box-candidate-prefix-data-gates-2026-10-15.md) and this strictly following interval together cover the [independently verified 115-session Validation prefix](box-candidate-continuous-prefix-358-115-2026-10-15.md). Adding their nonoverlapping aggregate populations gives **2,221** Dolt/raw candidate-days: **798** exact accepted T-day price matches and **1,423** missing accepted T-day rows; **2,154** have ten complete same-source raw metadata sessions and **67** do not. Of the 798 exact accepted T-day matches, 797 have complete raw metadata. These are descriptive intersections across two hash-bound intervals, not an authorization to stitch source data or run LEAN.

The actual private audit produced the [aggregate evidence](../evidence/box-candidate-data-gates-delta-2026-10-15.json). Its 38-session candidate set, accepted-price database, construction database, RI semantic contract and auditor sources are hash-bound; the candidate file-set hash differs from the previous interval as expected. Aggregate task conservation and source-hash equality were checked after the run. No private ID/date/symbol/price mapping is committed.

The issuer classes are as-of-T **observations**, not official historical identity certification. The older accepted-price exclusion uses a retrospective whole-closure gate and cannot be applied as a causal historical selection rule. Raw metadata do not certify actual executable price values, corporate actions/factors or tradability. The ten sessions are only a coverage diagnostic, not a holding rule. No post-T OHLCV values, future outcomes, Test/Fresh, human labels, orders, returns or box LEAN backtest were used. Train's legacy split-adjusted stratum remains separate and unbridged.

No code changed for this data-only increment. The latest full Native-inclusive project regression remains **815 passed, 8 skipped, one existing warning**. The two immutable low-priority background scans continue without modification or restart. Full Train/Validation coverage and official identity, execution-price/action/factor, signal and portfolio gates remain open.
