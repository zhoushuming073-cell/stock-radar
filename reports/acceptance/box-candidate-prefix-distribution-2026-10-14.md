# Box candidate prefix coverage and daily distribution — 2026-10-14

**Result: two longer continuous Train/Validation prefixes passed independent
chunk verification. The early Train zero-population sessions are an explicit
126-session warmup, not candidate-free market observations.** Both frozen
splits remain incomplete.

The existing candidate scanner's `--verify-only` path rechecked every expected
chunk against the frozen eligible population, causal gate selection,
configuration/code/RI/runtime fingerprints and payload hashes. A second
read-only pass recomputed the ordered private file-set SHA-256 and near-lower
row total before calculating the daily distribution. Only [aggregate counts
and hashes](../evidence/box-candidate-prefix-distribution-2026-10-14.json)
enter Git; identities, daily rows, market data and dates remain in ignored
local receipts.

| Verified continuous prefix | Train | Validation |
| --- | ---: | ---: |
| Inclusive interval | 2021-09-01 to 2022-07-28 | 2024-09-30 to 2024-10-14 |
| Frozen trading sessions | 228 / 753 | 11 / 235 |
| Eligible security-days | 328,407 | 43,827 |
| Possible near-lower security-days | 132,292 | 21,732 |
| Near-lower union contexts | 14,891 | 1,670 |
| Verified / missing chunks | 698 / 0 | 90 / 0 |
| Provider exclusions / unknown retained | 0 / 0 | 0 / 0 |

The **first 125 Train sessions** have zero eligible 126-session windows; all
125 zero-population sessions form one initial contiguous prefix. Among the
remaining **103 eligible Train sessions**, daily near-lower context counts
range from 6 to 313, median 134; the ten highest-count sessions contribute
18.7% of the 14,891 contexts. The eleven Validation sessions all have
eligible windows; their daily counts range from 85 to 223, median 151. These
descriptive figures do not establish structure accuracy, independent examples,
market-wide coverage or future return lift. They prevent the misleading
interpretation that 228 Train sessions all contributed eligible security-days.

The prior [source/basis audit](box-candidate-source-basis-2026-10-14.md)
remains bound to its earlier, smaller prefix and is not silently extended by
this receipt. The two low-priority full-split processes continue in private
directories. No scanner source or frozen data was changed. The last full
project Native-inclusive regression is **795 passed, 8 skipped**; this
read-only addendum did not rerun it. Official issuer identity, raw execution
prices/actions/factors and frozen portfolio rules remain open. No human label,
future outcome, Test/Fresh decision or box LEAN run was used.
