# Box candidate high-density full-state parity — 2026-10-15

**Result: all 313 observed near-lower contexts on the highest-count day of
the previously verified Train prefix match a complete independent full-state
scan exactly.** This strengthens target-state preservation evidence on a
deliberately challenging date; it does not prove all-date parity, other-state
preservation, detector accuracy, signal validity or profitability.

The date was selected **before** the full-state run by counting near-lower
contexts across the hash-verified 2021-09-01–2022-07-28 Train prefix. On
2022-05-04, the candidate path had 313 near-lower contexts among 3,193
eligible security-days. The separate full-state scanner processed all 3,193
in 13 immutable private chunks, taking 709.064 s of new detector compute.
The existing independent comparator reopened and verified both file sets,
filtered the complete scan to the exact target state, and required equality
of every private context row, including detector-specific contents.

| High-density Train reference, 2022-05-04 | Observed |
| --- | ---: |
| Indexed / eligible security-days | 3,568 / 3,193 |
| Fast gate possible / certainly not | 1,823 / 1,370 |
| Full-state verified chunks | 13 / 13 |
| Candidate / full-state near-lower contexts | 313 / 313 |
| Exact private context equality | Yes |
| Provider exclusions | 0 |

The prior four complete reference dates matched 614/614 observed target rows.
This fifth date raises the observed comparison total to **927/927**. Its
source/payload hashes and aggregate counts are in the [public evidence](../evidence/box-candidate-high-density-parity-2026-10-15.json);
private security IDs and rows remain only under ignored local `data`.

The previous long-running Train and Validation backfill process handles were
absent after the overnight interruption. Neither original log had a normal
completion summary or an error, and neither private split had `.partial`
files. Before restarting, `--verify-only` independently passed continuous
Train through 2022-08-03 (**232/753 sessions, 727/727 chunks, 15,345 target
contexts**) and Validation through 2024-10-17 (**14/235 sessions, 120/120
chunks, 2,166 contexts**). The two full-split scans were then restarted in
separate hidden, low-priority processes against the same immutable receipt
directories. Existing chunks are reverified on resume; no historical market
database or scanner source was altered.

Focused scanner/gate tests: **12 passed**. Last full project Native-inclusive
regression remains **795 passed, 8 skipped**; this data-only follow-up did
not rerun it. No human labels, future outcomes, Test/Fresh rows, portfolio
orders or box LEAN backtest entered this comparison. Official issuer identity,
same-source raw execution prices, actions/factors and frozen portfolio rules
remain open.
