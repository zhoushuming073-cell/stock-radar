# Box candidate Validation-prefix data-gate intersection — 2026-10-15

**Result: 1,494/1,531 Dolt/raw candidate-days have ten complete same-source raw *metadata* sessions, but none is thereby certified as a formal LEAN signal.** This read-only audit intersects that coverage with accepted T-day price status and issuer evidence known at decision T. It uses the same 77 sealed Validation sessions (2024-09-30–2025-01-21) as the earlier full-prefix audits; the background scan has since progressed beyond that frozen comparison interval.

The `box-candidate-prefix-data-gates-v1` auditor reruns the [T-day bridge](box-candidate-prefix-tday-2026-10-15.md), verifies the immutable candidate file set and accepted-price database hashes, and reuses the existing as-of-T [issuer query](box-candidate-prefix-issuer-at-t-2026-10-15.md) and same-source raw [horizon metadata query](box-candidate-execution-metadata-2026-10-14.md). The ten subsequent in-split sessions are a **coverage diagnostic**, not a proposed holding period. The aggregate [evidence](../evidence/box-candidate-prefix-data-gates-2026-10-15.json) binds the data, configuration semantics and auditor source hashes without exposing candidate identities, dates, symbols or prices.

| T-day accepted-price status | T-dated issuer observation | Ten-session raw metadata complete | Incomplete |
| --- | --- | ---: | ---: |
| Missing accepted T-day row | No known conflict observed | 844 | 32 |
| Missing accepted T-day row | Contemporaneous issuer alias | 73 | 4 |
| Missing accepted T-day row | Known identity conflict | 29 | 0 |
| Exact accepted T-day match | No known conflict observed | 534 | 1 |
| Exact accepted T-day match | Contemporaneous issuer alias | 14 | 0 |
| **Total** | | **1,494** | **37** |

The raw metadata query observed 15,310 expected in-split session slots and 15,206 available raw records. Its overlapping issue counters are 104 missing/ambiguous same-source rows, 20 records not research-ready and seven action flags; those counters must not be summed as distinct candidate-days. Of the 549 exact accepted T-day matches, 548 have complete same-source raw metadata, but 14 of those still have contemporaneous issuer alias observations. Of the 982 missing accepted T-day rows, 946 have complete raw metadata; metadata availability does not reverse the older accepted-price table's retrospective rejection or supply an accepted execution price.

Issuer classes are **observations from evidence available by T**, not official issuer certification. Accepted-price inclusion is not an identity, corporate-action, factor, tradability or full execution-period price certificate. The audit intentionally read no post-T OHLCV values or future outcomes. It did not use Test/Fresh, human labels, orders, returns or a box LEAN backtest. No candidate is promoted to an executable signal by this intersection.

The diagnostic covers only 77/235 Validation sessions and only the Dolt/raw source stratum. Train's legacy split-adjusted data remain separate; a cross-source substitution would need a new explicit contract and independent validation. Full Validation/Train candidate scans, official historical issuer identities, accepted execution-period prices and actions/factors, full signal formation and frozen portfolio rules remain open. The low-priority immutable background workers were neither changed nor stopped.

Focused intersection and reused auditor tests: **6 passed**. Full project regression ran with `STOCK_RADAR_TEST_LEAN=1` (Native LEAN fixture opt-in): **815 passed, 8 skipped, one existing `websockets.legacy` deprecation warning**. No box portfolio backtest ran.
