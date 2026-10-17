# Box candidate Train and Validation prefix verification — 2026-10-14

**Result: two continuous historical prefixes passed independent private-chunk
verification. Neither frozen split is complete.** This dated checkpoint extends
the earlier Train-prefix and Validation-start receipts without replacing them.

The existing `--verify-only` path reopened every expected candidate chunk and
recomputed eligible populations, causal gate selections, configuration/source/
RI/runtime fingerprints and payload hashes. It did not run the detectors again,
read future outcomes or examine portfolio returns. Aggregate-only evidence is
in [the companion JSON](../evidence/box-candidate-dual-prefix-2026-10-14.json).

| Independently verified prefix | Train | Validation |
| --- | ---: | ---: |
| Inclusive dates | 2021-09-01 to 2022-07-20 | 2024-09-30 to 2024-10-07 |
| Frozen trading sessions covered | 222 / 753 | 6 / 235 |
| Eligible security-days | 308,971 | 23,888 |
| Sent to both full detectors | 122,220 | 10,412 |
| Certainly outside near-lower state | 186,751 | 13,476 |
| Near-lower union contexts | 14,101 | 777 |
| Verified / missing candidate chunks | 655 / 0 | 44 / 0 |
| Provider exclusions / unknown prefixes | 0 / 0 | 0 / 0 |

The Train interval includes early sessions with no eligible 126-session
windows; its session denominator is not a full-population day count. Background
low-priority processes may write later dates before this report is read. Dates
beyond these prefixes are unverified here. Existing four-day full-state
comparison evidence remains 614/614 exact observed target contexts, not a
proof of all-date or non-target-state parity.

The owner cancelled mandatory human blind review as a progress gate. Existing
human and smoke stores remain separate and untouched. No human structure truth
or detector accuracy is inferred from these candidate counts. Official
historical issuer identity, same-source raw execution prices, corporate
actions/factors and frozen portfolio rules remain open; no box LEAN backtest
or formal profitability claim follows from this verification.
