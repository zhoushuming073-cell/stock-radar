# Box daily context scan Stage D — local acceptance, 2026-10-14

**Result: resumable Train/Validation scan engineering passed on one real
historical trading day. The full historical scan is not complete.** No
issuer certification, human structure truth, formal signal, future outcome or
LEAN portfolio result follows from this receipt.

The scanner consumes Research Infrastructure v1's 126-session as-of-T prefix.
It enumerates all supported, ready rows on the requested date, evaluates the
quantile and confirmed-pivot detectors separately, and applies the frozen
lower-band context. It saves private immutable date/chunk files with a payload
hash, selection hash, RI semantic hash and detector/context/config code
hashes, including the history reader and canonical OHLCV hasher, plus runtime
dependency versions. A verifier recomputes the expected denominator and selection, checks
every file and reconciles both detectors' state totals. Existing chunks are
verified before resuming. Test/Fresh and cross-split requests fail closed.

| Real Train date 2024-07-01 | Result |
| --- | ---: |
| Indexed 126-session rows | 4,452 |
| Supported and ready security-days | 3,944 |
| Processed / provider exclusions | 3,944 / 0 |
| Verified / missing immutable chunks | 16 / 0 |
| Rows with at least one active detector context | 1,457 |
| Quantile `NEAR_LOWER_STABILIZING` | 87 |
| Confirmed-pivot `NEAR_LOWER_STABILIZING` | 19 |
| Near-lower union / both detectors | 96 / 10 |

These counts describe **one date**, not market-wide frequency or detector
accuracy. Stage A already showed substantial detector disagreement; neither
variant was chosen using this date. The near-lower context is not a buy order.
The detailed security/date mappings stay in ignored local
`data/box-range-stage-d/daily-scan-v4`. Only the [aggregate verifier
receipt](../evidence/box-daily-scan-stage-d-2026-10-14.json) enters Git. Its
verified file-set SHA-256 is
`18fd02c3e61b32876453942fe9442e4c67051929d83d7246226ed301fb3fc8a2`.
The scanner source digest is
`57c3bad73172782c2bf2b5cfd2929cf956322075d954c7fd19c92e00b8f81481`;
RI semantic hash is
`74b765911a8a4f18b2074cd8d9e529b25b54afade15309a148b0ca43340b80be`.

A prior v2 pilot inadvertently included runtime in immutable payloads. It is
preserved privately as a diagnostic; v3 removed timing and v4 additionally
bound the history/hasher code and Python/library versions. An independent v4
run of the first 256-row chunk produced the **identical file SHA-256**
`8d81bd968063a34a11a3f594ec384ef5db5bbf586c3bb71124ca7889ea4d1e9e`.
All 16 v2/v3 and v3/v4 chunks had identical processed, excluded, context,
state and status values after ignoring version/code/timing metadata. A second v4 run
verified 16 existing chunks and wrote 0 new chunks.

The full v4 day took **595.383 seconds of new-chunk computation** in this
machine's run. The Stage A documented 2022–2025 eligible population alone
contains about 3.03 million security-days. At this single day's throughput,
a naive serial full scan is on the order of **127 hours**, before variation,
I/O and verification. This is a scaling warning, not an ETA or justification
to quietly sample the history. The next engineering task is to profile and
prove a lossless candidate prefilter or other throughput improvement before
launching the full Train/Validation scan. Keep explicit population and
exclusion denominators; preserve both detector variants separately.

Focused Stage D tests: **5 passed**. Full project pytest with
`STOCK_RADAR_TEST_LEAN=1`: **781 passed, 8 skipped, 1 existing
`websockets.legacy` warning** in 101.12 seconds. Native LEAN regression was
enabled, but no box portfolio run occurred. The previously found issuer and
same-source raw execution-price gates remain open.
