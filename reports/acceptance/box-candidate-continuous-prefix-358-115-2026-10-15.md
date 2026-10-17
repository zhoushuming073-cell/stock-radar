# Box candidate continuous-prefix checkpoint 358/115 — 2026-10-15

**Result: the unchanged read-only verifier passed longer continuous candidate prefixes in both active Train/Validation background scans.** Train now reaches 2023-02-02; Validation reaches 2025-03-17. Both low-priority immutable workers remain live. Full split coverage and formal data gates remain open.

The `box-candidate-source-basis-audit-v2` reran each scanner's `--verify-only` path and checked all immutable chunk hashes, count totals and source/basis distributions. The two successful local command results are captured as aggregate [evidence](../evidence/box-candidate-continuous-prefix-358-115-2026-10-15.json); private security/date mappings and price rows stay outside Git.

| Verified continuous prefix | Train | Validation |
| --- | ---: | ---: |
| Frozen sessions | 358/753 (47.5%) | 115/235 (48.9%) |
| Eligible security-days | 752,549 | 455,212 |
| Verified chunks | 1,486 | 837 |
| Near-lower contexts | 32,476 | 16,447 |
| Legacy Alpaca SIP / split | 32,471 | 14,226 |
| Legacy public EOD / split | 5 | 0 |
| Dolt / raw | 0 | 2,221 |

Since the prior [333/88 checkpoint](box-candidate-continuous-prefix-333-88-2026-10-15.md), the verified continuous intervals grew by 25 Train and 27 Validation sessions. Train's first 125 sessions are zero-candidate 126-session warmup, not evidence of complete candidate coverage. The source strata remain separate; no alternate source was substituted as an execution price.

These percentages describe **background scan coverage only**, not total project completion. Near-lower contexts are not detector accuracy, validated trade signals or return evidence. The separate [77-session three-gate audit](box-candidate-prefix-data-gates-2026-10-15.md) still has narrower coverage. Official historical issuer identity, accepted same-source execution prices/actions/factors, complete signal formation and frozen portfolio rules remain open. No post-T OHLCV values, future outcomes, Test/Fresh or box LEAN portfolio backtest were read or run.

No code changed for this data-only checkpoint. The latest full Native-inclusive pytest remains **815 passed, 8 skipped, one existing warning** from the preceding three-gate audit. The background writers were not modified, stopped or restarted.
