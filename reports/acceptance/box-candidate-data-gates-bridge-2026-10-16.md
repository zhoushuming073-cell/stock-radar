# Box candidate Validation data-gate bridge — 2026-10-16

**Result: the five-session gap in the Validation three-gate audit has been closed.** The unchanged read-only auditor independently reverified 2025-03-18–2025-03-24: 44 sealed chunks containing 1,269 near-lower contexts, of which 108 were Dolt/raw candidate-days. Its file-set hash exactly matches the prior [independent source/basis audit](box-candidate-segment-increment-2026-10-15.md). No private candidate identities, dates or prices are published.

| Newly audited 108 Dolt/raw candidate-days | Complete ten-session raw metadata | Incomplete | Total |
| --- | ---: | ---: | ---: |
| Exact accepted T-day price; no known issuer conflict observed | 47 | 0 | 47 |
| Exact accepted T-day price; contemporaneous issuer alias | 4 | 0 | 4 |
| Missing accepted T-day row; no known issuer conflict observed | 51 | 4 | 55 |
| Missing accepted T-day row; contemporaneous issuer alias | 2 | 0 | 2 |
| **Total** | **104** | **4** | **108** |

Across the prior 115-session audit, this five-session bridge and the [next 69-session audit](box-candidate-data-gates-next-2026-10-16.md), the **continuous 189/235-session Validation prefix** now has three-gate aggregate evidence for **3,284** Dolt/raw candidate-days: **1,255** exact accepted T-day matches, **2,029** missing accepted T-day rows, and **3,185** complete ten-session same-source raw-metadata tasks. These totals are sums of three independently hash-verified, disjoint intervals; the interval boundaries are consecutive frozen sessions. The bridge's [aggregate evidence](../evidence/box-candidate-data-gates-bridge-2026-10-16.json) binds source/database/config/query hashes. Cell, interval and cross-report arithmetic were checked.

The 108 bridge candidates imply 1,080 diagnostic in-split session slots. 1,065 have same-source raw metadata; 15 slots are unavailable/ambiguous and two are not research-ready. Slot issue counters may overlap. The ten-session length is a coverage diagnostic, not a selected holding period. The as-of-T issuer classes are observations, not official issuer/share-class certification. The older accepted-price gate is retrospective and cannot be used as a causal historical filter. Raw metadata are not executable prices, action economics or adjustment factors. Legacy split-adjusted candidates remain separate. No future price values, future outcomes, Test/Fresh, portfolio orders, returns or box LEAN backtest were read or run.

The real audit exited successfully, using the same auditor whose focused test passed **1/1** for the adjoining 69-session audit. No code changed; latest full Native-inclusive pytest remains **818 passed, 8 skipped, one existing warning**. Formal identity, execution-data, complete-signal and frozen-portfolio gates remain open.
