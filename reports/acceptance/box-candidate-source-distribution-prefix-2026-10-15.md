# Box candidate longer-prefix source and distribution — 2026-10-15

**Result: the resumed Train/Validation scans passed independent continuous
prefix verification, while source/basis coverage remains a formal execution
blocker.** The public distribution audit is now source-controlled and
repeatable as `box-candidate-source-basis-audit-v2`; it reads sealed private
candidate receipts without exposing identities or daily candidate rows.

The candidate `--verify-only` path reopened every expected chunk and checked
the frozen population, selection, configuration, code, Research
Infrastructure v1 and runtime bindings. The separate read-only auditor then
recomputed the ordered file-set SHA-256 and provenance counts, required the
number of day folders to equal verified sessions, and computed only aggregate
daily distribution figures. [Public evidence](../evidence/box-candidate-source-distribution-prefix-2026-10-15.json)
contains the two file-set hashes and source hashes; row-level securities and
market data stay in ignored local `data`.

| Continuous verified prefix | Train | Validation |
| --- | ---: | ---: |
| Dates | 2021-09-01–2022-09-08 | 2024-09-30–2024-11-14 |
| Frozen sessions covered | 257/753 | 34/235 |
| Eligible security-days | 422,293 | 135,703 |
| Verified/missing chunks | 869/0 | 259/0 |
| Near-lower contexts | 17,732 | 4,812 |
| Split-adjusted legacy contexts | 17,732 | 4,090 |
| Dolt raw contexts | 0 | 722 |

The 125 zero-candidate Train sessions are the same initial 126-session
warmup previously established as zero-eligible; the other 132 Train sessions
have 6–342 contexts per day (median 114.5). All 34 Validation sessions have
71–228 per day (median 146). The top ten days account for 2,870/17,732
Train and 1,975/4,812 Validation contexts. The latter share is naturally
larger in a 34-day prefix and is not a concentration comparison against the
much longer Train prefix. These counts describe scanner output, not detector
truth, independent examples, signal quality or future performance.

Every verified Train candidate still uses a split-adjusted legacy price
series. Validation has 722 Dolt raw candidates, but 4,090 remain on the
split-adjusted legacy series. No alternate-source raw rows were substituted;
official historical identity, raw prices/actions/factors and frozen
execution/portfolio rules still block a formal box LEAN result. Both
background scans remain incomplete and continue against unchanged immutable
scanner code.

The new auditor's focused source/scanner tests passed **12 tests** before the
all-zero warmup boundary case was added; that case separately passed with
the focused source tests (**4 passed**). Final full project pytest with
`STOCK_RADAR_TEST_LEAN=1` passed **797, skipped 8**, with one existing
`websockets.legacy` deprecation warning in 161.06 s. Native LEAN fixture
tests were enabled; no box portfolio backtest was run. No future OHLCV
values, outcomes, human labels, Test/Fresh decisions or QC job were used.
