# Box candidate decision-dated reference support increment — 2026-10-16

**Result: the later 69-session Validation interval has much weaker recent dual-mirror coverage than the earlier 120-session interval.** The unchanged read-only reference-support auditor independently reverified the 2025-03-25–2025-07-02 sealed candidate file set, then used only T-dated CIK/Nasdaq historical **mirror observations** under the frozen 31-calendar-day freshness rule. It checked 955 Dolt/raw candidate-days; the exact candidate file-set hash matches the separate [data-gate audit](box-candidate-data-gates-next-2026-10-16.md).

| Later 69-session candidate-days | Both recent compatible | CIK only | Nasdaq only | Neither recent | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| No known issuer conflict observed | 58 | 18 | 506 | 311 | 893 |
| Contemporaneous issuer alias | 0 | 0 | 25 | 18 | 43 |
| Known identity conflict | 0 | 0 | 17 | 2 | 19 |
| **Total** | **58** | **18** | **548** | **331** | **955** |

The auditor also finds 879 candidates with an older compatible CIK mirror observation that fails the 31-day freshness rule. A separate aggregate SQL inventory on the same SHA-256-verified frozen construction database finds the latest `membership_evidence.available_on` for CIK at **2025-02-28**, whereas Nasdaq has 2,919–2,927 mirror observations per month during March–July 2025. Under the frozen 31-day rule, a CIK observation on February 28 ceases to be recent after March 31. This source chronology explains the sharp later loss of recent CIK support; it is a data-source coverage change, **not an inference about box quality, issuer identity or stock returns**. See [aggregate chronology](../evidence/box-reference-chronology-2026-10-16.json) and [hash-bound candidate audit](../evidence/box-candidate-reference-support-next-2026-10-16.json).

Across the earlier [120-session reference audit](box-candidate-reference-support-2026-10-15.md) and this consecutive interval, the continuous 189-session Validation prefix has 3,284 Dolt/raw candidate-days: 1,607 with both recent compatible mirrors, 798 with only CIK, 548 with only Nasdaq, and 331 with neither. The 183 contemporaneous aliases and 64 known identity conflicts are independent issuer-query observations; matching one or two mirrors does not resolve them. The mirror dates do not prove upstream official announcement timing, complete market coverage or share-class identity. Official identity and executable prices/actions/factors, complete signals and frozen portfolio rules still gate formal LEAN verification. No future price values, outcomes, Test/Fresh, human labels, orders, returns or box LEAN backtest were used.

The real read-only audit exited successfully; row-count conservation and the independent candidate file-set hash matched. The frozen construction database SHA-256 was independently rechecked before the source chronology query. Focused reference-support tests: **3 passed**. No code changed; latest full Native-inclusive pytest remains **818 passed, 8 skipped, one existing warning**.
