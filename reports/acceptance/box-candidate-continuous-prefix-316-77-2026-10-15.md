# Box candidate continuous-prefix verification — 2026-10-15

**Result: the immutable background candidate scans now have independently
verified continuous prefixes through 2022-12-01 Train and 2025-01-21
Validation.** This is partial engineering coverage, not a completed detector
study, a signal stream or a return result.

The existing `box-candidate-source-basis-audit-v2` first ran the candidate
scanner's read-only `--verify-only` mode over each frozen interval. It then
bound aggregate source/basis counts to the ordered SHA-256 set of verified
private chunks. Both selected intervals had zero missing chunks. The
[aggregate receipt](../evidence/box-candidate-continuous-prefix-316-77-2026-10-15.json)
records the auditor, Research Infrastructure v1 semantic and chunk-file-set
hashes. Private candidate identities, price rows and daily mappings remain
outside Git.

| Verified continuous prefix | Train | Validation |
| --- | ---: | ---: |
| Dates | 2021-09-01–2022-12-01 | 2024-09-30–2025-01-21 |
| Frozen sessions covered | 316/753 | 77/235 |
| Eligible security-days | 614,959 | 306,005 |
| Verified/missing chunks | 1,209/0 | 580/0 |
| Near-lower contexts | 27,444 | 10,863 |
| Legacy Alpaca SIP / split | 27,439 | 9,332 |
| Legacy public EOD / split | 5 | 0 |
| Dolt / raw | 0 | 1,531 |

The first 125 Train sessions remain zero-candidate warmup; 191 Train and 77
Validation sessions have at least one candidate. The five Train public-EOD
rows remain a separate provenance stratum from legacy Alpaca SIP. A shared
split-adjusted basis does not make them the same price source. No alternative
source was substituted for execution inputs.

Compared with the previous sealed checkpoint (274/753 Train, 43/235
Validation), this verifies 42 additional Train and 34 additional Validation
sessions. There remain 437 Train and 158 Validation sessions outside these
verified continuous prefixes. The live low-priority workers were not
stopped or changed. Per-session compute varies with the eligible universe,
so no reliable completion time is claimed from these two checkpoints.

The source-audit/scanner code and frozen data were unchanged for this
checkpoint; the preceding code change passed full Native-inclusive pytest
with **810 passed, 8 skipped, 1 existing warning**. No new regression was
needed for this read-only data receipt. Neither audit reads future OHLCV
values or outcomes. Official identity, accepted same-source raw execution
prices, corporate actions/factors, complete signals and portfolio rules
remain open; no box LEAN backtest ran.
