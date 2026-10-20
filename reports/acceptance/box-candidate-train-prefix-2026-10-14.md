# Box candidate Train prefix — live backfill checkpoint, 2026-10-14

**Result: a continuous 207-session Train prefix has been independently
verified; the full 753-session Train split is not complete.** The hidden,
low-priority historical candidate process remains active. This report is a
dated progress receipt, not a final all-history acceptance or signal stream.

The scanner's `--verify-only` mode reopened every expected private chunk from
2021-09-01 through 2022-06-28. It recomputed the frozen eligible population,
causal necessary-gate selection, config/source/RI/runtime fingerprints and
payload hashes. The expected 560 chunks existed; zero were missing. Only
aggregate counts appear in the [public evidence](../evidence/box-candidate-train-prefix-2026-10-14.json).

| Verified Train prefix | Actual |
| --- | ---: |
| Frozen trading sessions | 207 / 753 Train sessions |
| Eligible security-days | 260,414 |
| Still requiring both full detectors | 100,023 |
| Necessarily outside near-lower state | 160,391 |
| Near-lower union contexts | 11,093 |
| Provider exclusions / unknown prefixes | 0 / 0 |
| Verified / missing private chunks | 560 / 0 |

The gate excluded 61.6% of this prefix's eligible rows; that is an observed
rate for this interval, not a constant for later Train or Validation days.
Early sessions in the frozen split can have zero eligible 126-session windows;
the 207 session denominator must not be confused with 207 full-population days.
No future price, outcome, human label, Test/Fresh row or portfolio result was
read. Known issuer and raw execution-data limits remain open.

An independent [cross-period full-state comparison](box-candidate-cross-period-parity-2026-10-14.md)
subsequently matched all 228 target contexts on 2022-03-15, as well as the
previous 2024 Train and 2025 Validation reference days. That comparison is
separate evidence; this prefix receipt still covers only the stated 207
sessions and is not full-history acceptance.
