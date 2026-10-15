# Box candidate continuous-prefix verification and runtime checkpoint — 2026-10-15

**Result: both immutable background candidate scans have longer,
independently verified continuous prefixes.** Train is complete through
2022-12-27 and Validation through 2025-02-05. Both workers remain live;
neither full split has finished. This is Stage D engineering coverage, not
detector accuracy, formal signals or returns.

The unchanged `box-candidate-source-basis-audit-v2` ran each scanner's
read-only `--verify-only` path over the full selected prefix, then checked
the ordered private chunk-file SHA-256 and every source/basis count. Both
intervals have zero missing chunks. Aggregate counts and hashes are in
[the evidence](../evidence/box-candidate-continuous-prefix-333-88-2026-10-15.json).
Identities, price rows and daily task mappings remain in ignored local data.

| Verified continuous prefix | Train | Validation |
| --- | ---: | ---: |
| Dates | 2021-09-01–2022-12-27 | 2024-09-30–2025-02-05 |
| Frozen sessions covered | 333/753 | 88/235 |
| Eligible security-days | 670,732 | 349,260 |
| Verified/missing chunks | 1,301/0 | 664/0 |
| Near-lower contexts | 29,363 | 12,530 |
| Legacy Alpaca SIP / split | 29,358 | 10,768 |
| Legacy public EOD / split | 5 | 0 |
| Dolt / raw | 0 | 1,762 |

Since the prior sealed 316/77 checkpoint, this verifies 17 more Train and
11 more Validation sessions. Train still has 125 zero-candidate warmup
sessions; the five public-EOD contexts remain a separate source stratum.
No alternative source was substituted for a raw execution price.

## Runtime measurement

The final JSON chunk's modification time was read for each of the last 31
sealed sessions per split, yielding 30 consecutive completion intervals.
Train's observed interval averaged **5.46 minutes/session** over 2.73
wall-clock hours (individual intervals 2.16–8.15 minutes). Validation
averaged **7.39 minutes/session** over 3.70 hours (2.95–11.75 minutes).
At those *recent* means, the remaining 420 Train sessions would occupy
about **38 hours**, and 147 Validation sessions about **18 hours**, if
both workers continue uninterrupted and future dates have similar work.
They run concurrently, so these figures must not be added. This is a
conditional scheduling estimate, **not a reliable ETA or completion
guarantee**: eligible populations, chunk counts, machine load and shutdowns
can change. Partially written current-day directories were excluded.

No code changed for this data-only checkpoint. The last full
Native-inclusive project regression remains **814 passed, 8 skipped,
1 existing warning**; it was not rerun for unchanged code. The auditors
read no future OHLCV values or outcomes and ran no LEAN portfolio backtest.
Official issuer, raw execution-price/action/factor, complete signal and
portfolio-rule gates remain open.
