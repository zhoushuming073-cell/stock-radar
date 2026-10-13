# BOX-LQ1.0 — reproducible baseline gap audit

> 2026-10-13. Read-only audit of the local private v1 batch and PR #21 source at `2a283affeef6336116f5eb8456b914d64bc53f08`. No private identities, chart content or human responses are included here. P0 is an audit, not model or label-quality acceptance.

## Actual local state

The ignored `data/box-label-v1-2m-1y-4y/manifest.json` has 30 tasks and 30 unique `security_id`s: 21 Train / 9 Validation; positive 21 / boundary 6 / control 3. Years: 2022 8, 2023 8, 2024 7, 2025 7. Membership: confirmed 23, probable 7, unknown 0. Source/basis: legacy Alpaca SIP split 29, Dolt raw 1. **Later-disappeared security participation was not established from these manifest fields.** Issuer alias continuity is not independently proved merely by distinct security IDs.

Observed numeric/display bars:

| Scale | Observed length histogram | Full coverage |
| --- | --- | ---: |
| Daily | 42: 30 | 30/30 |
| Weekly | 31,33,34,35,37,38,49,50: one each; 52:22 | 22/30 |
| Monthly | 7:1, 8:3, 9:2, 12:3, 14:1, 17:2, 18:2, 19:1, 21:1, 23:2, 25:1, 32:2, 33:1, 38:2, 48:6 | 6/30 |

Read-only SQLite counts: formal human database **0 revisions / 0 unique tasks / 0 skips**; separate smoke database **4 revisions / 3 unique tasks / 1 skip**. No real intra-rater or inter-rater agreement is measurable. Existing v1 annotation rows are never rewritten by this audit.

## Discrepancy register

| Classification | Evidence | Consequence / action |
| --- | --- | --- |
| VERIFIED BUG, repaired in parent | The October 11 model zeroed valid short weekly/monthly embeddings. PR #21 head `2a283af` uses observed lengths and passed 9 targeted / 720 full-project tests. | Reuse repair; do not reimplement or claim the October 11 historical receipt was wrong. |
| DESIGN TRADEOFF | Candidate `loose_box_v1` sees 126 daily sessions; human close-up daily chart shows 42 while weekly gives longer context. | Define the human evidence interval; decide if an optional 126D context panel improves agreement before changing the user's 42D default. |
| DESIGN TRADEOFF | V1 selects 70/20/10. `candidates()` caps a deterministic 1,800-row ordered pool and stops once 30 quota slots fill; only 34 rows were evaluated in the dated build receipt. The `index % 13` control slot is deterministic, not a known-probability random draw from the full eligible universe. | Report selection mechanism exactly. A new versioned pool needs recorded denominator, inclusion probability or explicit unknown probability, and more unconditional controls. Never claim market-wide recall from v1. |
| DATA LIMIT | RI v1 begins September 2021; early Train cases cannot contain four prior calendar years. Some histories are only 7–38 monthly bars. | Keep true lengths and coverage masks. Do not pad missing historical sessions as observations. |
| DATA LIMIT | The 30-task receipt has 23 confirmed and 7 probable members, but no verified disappeared-security count or issuer alias mapping in the task manifest. | Audit identity/disappearance coverage in a new pool; no broad survivorship claim from these 30 cases. |
| NEEDS HUMAN DECISION | V1 has no independently defined box evidence interval, boundary-zone coordinates, subtype handbook or genuine human labels. | Version a v1.1 ontology and pilot; preserve v1 rows. Human judges ambiguity and boundary meaning. |
| VERIFIED GATE | Existing v1 tests assert future mutation isolation, partial as-of-T periods, plugin purity, split separation, hash verification and label revision conflict. Browser smoke was recorded in the October 11 acceptance. | Retain and extend exact causal/visible-payload gates for v1.1; tests do not establish human reliability. |

## P0 exit and P1 entry

P0 audit result: **READY_TO_DEFINE_V1_1**, with known data and label limitations above. P1 must use an additive label contract and separate human/smoke stores, protect blind payload, and provide a first honest human pilot. New sampling must live in a versioned directory; the 30 existing tasks and their untouched annotations remain available as v1 engineering evidence. No future returns, detector expansion or substantive training were read/run here.
