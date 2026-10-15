# Box candidate longer continuous prefixes — 2026-10-15

**Result: both running Train/Validation candidate writers have extended their
sealed continuous prefixes, and the independent read-only source audit passes
over the newly closed intervals.** These are still partial scans and do not
establish structure accuracy, official historical identity, executable prices
or returns.

The unchanged `box-candidate-source-basis-audit-v2` first reran the candidate
scanner's `--verify-only` path over each selected interval. It then checked
the ordered chunk-file SHA-256, exact expected chunk count, frozen Research
Infrastructure v1 semantic hash, row counts and source/basis metadata. Both
intervals had zero missing chunks. Public aggregate values and hashes are in
[the evidence](../evidence/box-candidate-longer-prefix-source-2026-10-15.json);
candidate identities and price rows remain in ignored local `data`.

| Continuous verified prefix | Train | Validation |
| --- | ---: | ---: |
| Dates | 2021-09-01–2022-10-03 | 2024-09-30–2024-11-27 |
| Frozen sessions covered | 274/753 | 43/235 |
| Eligible security-days | 477,536 | 171,656 |
| Verified/missing chunks | 947/0 | 334/0 |
| Near-lower contexts | 20,689 | 5,962 |
| Legacy Alpaca SIP / split | 20,685 | 5,056 |
| Legacy public EOD / split | 4 | 0 |
| Dolt / raw | 0 | 906 |

The Train legacy public-EOD stratum contains four observations across two
private security IDs and four days. It was already present in the earlier
prefix (three observations through 2022-09-08); it is kept separate from
legacy Alpaca SIP despite sharing the split-adjusted basis. The previous
report's combined “split-adjusted legacy” count is a basis/category total,
not a claim that every Train candidate has the same source. No alternative
source has been substituted for an execution price.

Train has 125 zero-candidate warmup sessions and 149 positive sessions;
positive daily counts range from 6 to 437 with median 116. Validation has
43 positive sessions, 60–228 contexts/day with median 144. These are counts
of detector contexts and cannot be interpreted as independent examples,
precision or tradable signals.

Focused source/scanner tests: **8 passed**. The source code was unchanged;
the prior full Native-inclusive regression remains **800 passed, 8 skipped**
and was not rerun for this data-only checkpoint. Both background workers
remained live. The rest of the frozen Train/Validation sessions, issuer
provenance, same-source raw action/factor economics and portfolio rules remain
open. No future OHLCV values, outcomes, human labels or box LEAN backtest
were used.
