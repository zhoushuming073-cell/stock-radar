# Box candidate background-prefix checkpoint — 2026-10-15

**Result: both resumed Train/Validation candidate scans are running, and their
completed continuous prefixes independently reverify without missing chunks.**
This is a bounded engineering checkpoint, not a finished history, structure
quality score, signal or portfolio result.

| Verified continuous prefix | Train | Validation |
| --- | ---: | ---: |
| Dates | 2021-09-01–2022-08-05 | 2024-09-30–2024-10-22 |
| Frozen sessions covered | 234/753 | 17/235 |
| Eligible security-days | 347,835 | 67,749 |
| Verified/missing private chunks | 740/0 | 141/0 |
| Near-lower contexts | 15,512 | 2,564 |

`--verify-only` reopened the immutable private receipts and checked the
expected chunk sets and source/config/RI/runtime binding. The separate
source/basis auditor verified the same file-set hashes before its aggregate.
The [public evidence](../evidence/box-candidate-background-prefix-checkpoint-2026-10-15.json)
records both file-set SHA-256 values; private security IDs, dates at row level
and price data remain under ignored local `data`.

Every Train candidate in this prefix is on a split-adjusted legacy series:
15,511 `legacy:alpaca:sip` and one public EOD row. Validation has 2,178
split-adjusted `legacy:alpaca:sip` candidates and 386 `Dolt` raw candidates.
This expands the earlier source/basis sample but does not create same-source
raw execution prices for the legacy series. Cross-source substitution is not
adopted. Official historical issuer identity, action/factor continuity and
frozen execution/portfolio rules remain open LEAN gates.

Both hidden low-priority background workers and their child processes were
live when checked; stderr and stdout logs were empty. The in-progress date
directories were excluded from these exact prefix totals. No scanner or
database source was changed, so the last full Native-inclusive regression
remains **795 passed, 8 skipped**; this checkpoint ran the actual receipt
and source/basis verifiers rather than a new pytest run. No future OHLCV
values, outcomes, human labels, Test/Fresh rows or box LEAN backtest were used.
