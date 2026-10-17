# Box candidate/full-state cross-period parity — 2026-10-14

**Result: the candidate-only path exactly reproduced every near-lower context
on three complete full-state reference days spanning two Train years and one
Validation year.** The comparison checked private security IDs and the full
detector-specific context objects in memory, not just aggregate counts.

Each side's independent verifier first recomputed the frozen eligible
population and confirmed all expected immutable chunks, configuration/code/
RI/runtime fingerprints and file hashes. Only then did the comparator strip
the full-state output to `NEAR_LOWER_STABILIZING` and compare it with the
candidate-only output. No private identity/date mapping or OHLCV entered Git.

| Reference day | Eligible | Gate evaluated | Certainly rejected | Exact near-lower matches |
| --- | ---: | ---: | ---: | ---: |
| Train 2022-03-15 | 3,106 | 1,642 | 1,464 | **228 / 228** |
| Train 2024-07-01 | 3,944 | 1,221 | 2,723 | **96 / 96** |
| Validation 2025-06-02 | 3,898 | 1,839 | 2,059 | **146 / 146** |

Thus **470/470** observed target contexts matched exactly across these three
dates. Gate rejection ranged from 47.1% to 69.0%, reinforcing that one day's
throughput must not be projected as a constant. The 2024 Train detector
compute was 163.685 s candidate-only versus 595.383 s full; the Validation
comparison was 258.862 s versus 751.374 s. These are detector computation
times from separate runs, excluding gate-query, startup and verification.
The 2022 candidate day was produced inside an ongoing multi-day backfill, so
its isolated compute time was not recorded and no speedup is claimed for it.

The exact file-set hashes and comparator source hash are in [aggregate
evidence](../evidence/box-candidate-cross-period-parity-2026-10-14.json).
This is strong observed consistency for the fixed Stage C target state under
the current RI data and configs, not a proof of detector structure truth,
future return value, all-date parity or preservation of other box states.
The full-state scanner remains intact. Historical Test/Fresh, outcomes,
human labels and box portfolio backtests were not used. Issuer identity,
raw execution price/actions and portfolio contracts remain open.

Focused scan/gate regression after this comparison: **12 passed**. Scanner,
gate and comparator source did not change after the previous full project
Native-inclusive run (**793 passed, 8 skipped**); that earlier result is not
represented as a new full-suite run for this read-only checkpoint.
