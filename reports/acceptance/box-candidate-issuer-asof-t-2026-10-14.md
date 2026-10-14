# Box candidate as-of-T issuer observations — 2026-10-14

**Result: 20/242 near-lower candidates on two complete days have a known
as-of-T issuer risk; the other 222 have no known conflict in the frozen
construction source, but have no official identity certification.** This
extends the earlier 48-task identity audit to a different, actual daily
candidate population. It does not create a security master or clear LEAN.

The audit reverified each private candidate file set and the Research
Infrastructure v1 construction-database SHA-256. It obtained each candidate's
126-session T-only window from the RI provider, requiring the same source and
price basis as the candidate receipt. The existing `dated_evidence` join used
only ticker episodes spanning that window, CIK/name evidence available by T,
other security IDs active at T, and dispute annotations known by T. Current
CIK/ticker mappings and post-T evidence did not enter classification.

| Actual candidate day | Train 2024-07-01 | Validation 2025-06-02 |
| --- | ---: | ---: |
| Near-lower candidates | 96 | 146 |
| Observational, no known conflict | 84 | 138 |
| Another active security ID with same observed CIK | 9 | 6 |
| Known identity/name conflict | 3 | 2 |

The sealed private issuer and ten-session execution-metadata receipts were
also joined by exact private task IDs, split, date, candidate file-set hash
and RI semantic hash. Of the **29** candidates with complete, unflagged
same-source raw *metadata*, **25** have no known as-of-T issuer conflict and
**4** already have an alias/conflict risk. This intersection is reproducible
with `scripts/summarize_box_candidate_gates.py`; its code hash and both
private receipt hashes are in the [aggregate evidence](../evidence/box-candidate-issuer-asof-t-2026-10-14.json).

Those 25 are **not** LEAN-ready. “No known conflict” is observational, not
official historical issuer/class continuity. The raw rows are metadata
presence observations, not certified open prices, factor/actions, delisting
settlement or benchmark closure. The ten sessions are a coverage probe, not
a selected exit rule. Two dates cannot establish all-history identity or
execution coverage, detector accuracy or returns.

Private security IDs, CIKs, names, dates and window mappings remain only in
ignored local `data/box-range-stage-d/issuer-candidates-v1`. Their hashes were
independently re-read and matched. No human label, future outcome, Test/Fresh
row or box LEAN portfolio run was used.

## Regression

Focused issuer/overlap tests: **5 passed**. Full project pytest with
`STOCK_RADAR_TEST_LEAN=1`: **793 passed, 8 skipped, 1 existing
`websockets.legacy` deprecation warning** in 120.34 s. Native LEAN regression
was enabled; no box portfolio backtest was run.
