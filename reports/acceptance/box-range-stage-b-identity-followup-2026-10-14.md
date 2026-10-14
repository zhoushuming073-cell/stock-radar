# Stage B issuer identity follow-up — 2026-10-14

This is a follow-up to the [2026-10-13 Stage B checkpoint](box-range-stage-b-2026-10-13.md); it does not replace or rewrite that historical report. The frozen 48-task selection, RI v1 database and human annotations were not changed.

The previous aggregate reported 46/48 `names_compatible` rows. That field summarizes evidence across all dates, so it is too broad to treat both flagged names as conflicts known at the frozen decision date T. The revised read-only audit counts issuer evidence available by each task's T separately from later evidence. It uses RI v1's recorded construction database and verifies its SHA-256 before querying.

| Identity check | Actual result |
| --- | ---: |
| Distinct selected security IDs | 48 |
| One CIK with evidence available by T | 48/48 |
| One ticker episode throughout the causal 126-session window | 48/48 |
| One CIK available by T for that episode | 48/48 |
| Distinct CIKs in selected batch | 48 |
| CIK overlap with old pilot / Stage A / six references | 0 / 0 / 0 |
| All-time name-compatible rows | 46/48 |
| Incompatible name evidence available by T | 1/48 |
| Incompatible name evidence only after T | 1/48 |
| `official_identity` rows | 0/48 |
| Reviewed identity discontinuities known and covering T | 0/48 |
| Retrospective full-window identity levels A / B / C | 33 / 3 / 12 |

The one pre-T conflict has a plausible documented issuer-renaming explanation, but the research database still marks the identity observational. External corroboration does not silently promote `OBS` to `official_identity`, and the remaining provenance review is not complete. No symbol, date, security ID or private name mapping is published here. The executable query and aggregate [receipt](../evidence/box-range-stage-b-identity-followup-2026-10-14.json) allow rechecking the time boundary.

All 48 dated CIK links come from the construction source marked `cik`, the historical SEC CIK-mapper mirror. The A/B/C identity level is explicitly a **full-window retrospective audit** in that database. The 12 C rows signal material provenance risks to review, but their level can include post-T evidence and cannot be substituted for a causal T-day eligibility rule. Conversely, zero reviewed discontinuities known by T does not prove the absence of an unobserved identity break. The primary detector-quality denominator must not be asserted until those provenance risks are resolved; the frozen sample itself remains intact.

The 126-session check reread each frozen RI v1 history through T, then joined the recorded ticker intervals and their dated CIK observations. Every sampled window overlaps exactly one ticker interval and one symbol, with one CIK already available by T for that interval. This rules out an observed ticker-episode splice *inside these windows*; it does not convert observational IDs into official class-level identities.

The revised read-only audit completed on the frozen local files; Stage A/B focused regression is **30 passed**. The earlier full-project regression remains the 2026-10-13 run of **760 passed / 8 skipped / 1 warning**; a second full-project run was not claimed for this audit-only follow-up.

**Gate: PROVISIONAL.** This refinement removes one false historical concern caused by post-T information. It does not establish the independent issuer-level quality gate or detector accuracy. The separate human annotation store still has zero genuine revisions; no assistant labels, future outcomes or Stage C work were produced. The owner can continue blind structure labeling in the existing local page. Stage B exit still requires genuine human labels and the remaining issuer provenance review.
