# Box Stage D candidate-only scan — local acceptance, 2026-10-14

**Result: the separate near-lower candidate scanner works on one complete
Train day and one complete Validation day.** On the Train reference day its
96 private near-lower context rows match the sealed full-state scan **exactly**,
including detector-specific context content. This is an engineering result,
not a detector-quality score, formal signal, return study or LEAN run.

The scanner applies the versioned, T-only necessary gate to every supported,
research-ready 126-session security-day. It sends every possible or uncertain
row to the unchanged RI v1 history provider and both Stage A detectors, then
stores only the `NEAR_LOWER_STABILIZING` Stage C contexts. The existing
full-state scanner remains available for independent audit. Source/basis,
contiguous session numbers, final date and 20-bar length are checked before
exclusion. A read-only database audit found zero `shape_price` series IDs
shared by multiple security IDs. No post-T price, outcome, human label,
Historical Test or Fresh row enters candidate selection.

| Actual frozen day | Train 2024-07-01 | Validation 2025-06-02 |
| --- | ---: | ---: |
| Eligible security-days | 3,944 | 3,898 |
| Certainly cannot reach near-lower state | 2,723 (69.0%) | 2,059 (52.8%) |
| Evaluated by both full detectors | 1,221 | 1,839 |
| Unknown prefixes retained | 0 | 0 |
| Near-lower union contexts | 96 | 146 |
| Private chunks verified / missing | 5 / 0 | 8 / 0 |
| New detector compute time | 163.685 s | 258.862 s |

The original full-state Train day took 595.383 s of new detector computation;
the candidate path used 72.5% less detector compute on **that same day**. This
comparison excludes bulk gate-query, process startup and verification time.
Validation has no full-state reference, so its time is not a measured speedup.
The different daily rejection rates prohibit extrapolating a single constant
to the entire historical population. The full Train/Validation history has
**not** been scanned.

The 2024-07-01 comparator independently verified the original 16-chunk
full-state file set, recomputed eligible/candidate selection, then compared
private near-lower context maps in memory. Equality passed with 96/96 rows;
no identities were printed or committed. Both candidate days were independently
reopened in `--verify-only` mode, with zero missing chunks and matching file-set
hashes. Interruption and resume use immutable payload and selection hashes,
config/code/RI/runtime fingerprints and a private `.partial` guard. The
aggregate [evidence](../evidence/box-candidate-scan-stage-d-2026-10-14.json)
contains no security mapping or OHLCV.

Focused tests cover uncertain-prefix retention, necessary rejection,
missing/duplicate prefix identities, target-only persistence and receipt
count/provenance checks. Full project pytest result is recorded below after
the actual run. Remaining independent gates: observational issuer identity,
same-source raw execution prices/actions, full historical coverage, frozen
portfolio rules and any formal LEAN comparison. Human structure truth is
absent by owner choice; it is not replaced with a synthetic score.

## Regression

Focused gate/candidate tests: **7 passed**. Full project pytest with
`STOCK_RADAR_TEST_LEAN=1`: **788 passed, 8 skipped, 1 existing
`websockets.legacy` deprecation warning** in 106.82 s. Native LEAN regression
was enabled; no box portfolio backtest was run.
