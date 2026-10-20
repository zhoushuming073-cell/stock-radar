# Box candidate full Validation reference-support audit — 2026-10-17

**Result: all 3,729 Dolt/raw candidate-days in the frozen 235-session Validation split have an independently checked, decision-dated CIK/Nasdaq mirror-support classification.** The audit aggregates 26 disjoint receipts. It re-hashed each receipt's candidate interval, checked that every one of the 235 candidate-session directories was covered exactly once, and re-hashed the complete 1,748-chunk candidate file set to the independently verified SHA-256 `80f7f641045051fd80cae446ba1ebad7ab2c78694d6c76e1260e4054a6b33c96`. An older one-day 2025-08-21 receipt is excluded because the later 2025-08-21–22 receipt supersedes it; otherwise that day would be double counted.

| Mirror support available by decision T under the frozen 31-day freshness rule | Candidate-days |
| --- | ---: |
| Both compatible CIK and Nasdaq mirrors | 1,607 |
| Compatible CIK only | 798 |
| Compatible Nasdaq only | 819 |
| Neither recent compatible mirror | 505 |
| **Total** | **3,729** |

The independent T-dated issuer-observation classification totals 3,452 without a *known* conflict, 206 contemporaneous issuer aliases and 71 known conflicts. All 3,729 candidate windows stay within one observed ticker episode; the reference join found zero recent name/exchange incompatibilities. Another 1,324 candidate-days have an older compatible CIK observation but no *recent* one, reflecting the frozen mirror's limited later coverage. These are observation counts, not official issuer or share-class certificates. In particular, neither a dual-mirror match nor an absence of known conflict proves legal identity. The current official trust catalog has zero exact security-ID overlap with this Dolt/raw stratum, as separately documented in the [catalog-overlap audit](box-candidate-trust-overlap-2026-10-17.md).

The [aggregate receipt](../evidence/box-candidate-reference-full-2026-10-17.json) records the source-receipt-set digest, all interval and complete file-set checks, frozen rule/database hashes, and only summary counts. No private securities, dates paired with identities, OHLCV or labels are published. Existing receipt queries used observations with `available_on <= T`; this aggregation read only their verified summaries and candidate file hashes. No future price values or outcomes, Test/Fresh, orders or box LEAN portfolio backtest were used.

This closes the **Validation mirror-support accounting task**, not the formal identity or executable-data gate. Source-dated official issuer/class and corporate-action evidence, accepted same-source executable prices/factors, complete signals and frozen portfolio rules remain open. No source code changed; the latest full Native-inclusive pytest remains 818 passed, 8 skipped, one existing warning.
