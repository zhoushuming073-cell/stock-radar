# Box candidate cross-era issuer and raw-metadata gates — 2026-10-14

**Result: two additional complete reference days expose materially different
raw-price coverage, while official historical identity remains unresolved.**
These are read-only dependency audits of candidate context, not a signal,
outcome, executable-price certificate or box portfolio backtest.

The existing candidate verifier reopened each day's sealed chunks. The issuer
audit reused the frozen construction source, candidate-matched 126-session
T-only history and evidence known by T. The execution audit inspected only
session, source, basis and readiness/action/identity metadata for the next ten
sessions within the frozen split. The ten sessions are a coverage probe, not a
holding rule. [Aggregate evidence](../evidence/box-candidate-cross-era-gates-2026-10-14.json)
records all four private receipt hashes and candidate file-set hashes; private
security IDs, CIKs, windows and session rows remain in ignored local `data`.

| Actual complete day | Train 2022-03-15 | Validation 2024-09-30 |
| --- | ---: | ---: |
| Near-lower contexts audited | 228 | 144 |
| Observational, no known as-of-T conflict | 210 | 131 |
| Contemporaneous same-CIK alias | 13 | 13 |
| Ambiguous own identity | 5 | 0 |
| Ten-session research-basis metadata complete | 228 | 143 |
| Same-source raw metadata session rows / expected | 0 / 2,280 | 243 / 1,440 |
| Ten-session same-source raw metadata complete | 0 | 24 |
| Both observational and raw-metadata complete | 0 | 23 |

The 2022 zero is specific to these 228 candidates; a separate read-only
database count for 2022-03-16 through 2022-03-29 found **10 raw** and
**38,499 split-basis** `shape_price` rows overall. For 2024-10-01 through
2024-10-14, the corresponding counts were **51,323 raw** and **43,446 split**.
This establishes a severe era-dependent raw coverage gap, not a claim that no
raw row exists anywhere in 2022. The 2024 audit also found seven missing or
duplicated matching-basis session rows. Alternative-source raw rows were not
silently substituted for same-source candidate input.

The issuer/raw intersection reused `summarize_box_candidate_gates.py` and
required matching split, date, candidate file-set hash, RI semantic hash and
identical private task-ID sets. The 23 Validation rows are only observationally
free of **known** as-of-T conflict and metadata-complete. None has official
historical issuer certification, verified raw OHLCV/action/factor continuity,
delisting treatment or frozen portfolio execution rules. Thus none is promoted
to formal LEAN readiness. Neither day implies full-history coverage or
detector accuracy.

Separately, the live background candidate scans advanced and `--verify-only`
independently checked continuous Train through 2022-07-22 (**224/753 frozen
sessions, 668/668 chunks, 14,358 near-lower contexts**) and Validation
through 2024-10-09 (**8/235 sessions, 62/62 chunks, 1,140 contexts**).
Both splits remain incomplete. The prior dated dual-prefix report retains
its original smaller verified interval.

Focused issuer, horizon and gate-overlap regression after these data audits:
**10 passed**. Scanner/auditor source did not change. The last full project
Native-inclusive run remains the earlier **793 passed / 8 skipped** receipt;
this is not a new full-suite claim. No human labels, future OHLCV values,
outcomes, Test/Fresh decisions or box LEAN portfolio run were used.
