# Box candidate recurrence audit — 2026-10-20

**Result:** Stage D candidates recur heavily for the same *observed* security ID inside each frozen split. The [aggregate evidence](../evidence/box-candidate-recurrence-2026-10-20.json) comes from a second read and SHA-256 recheck of every accepted candidate chunk. No ID/date map is published.

| Split | Candidate days | Observed IDs | Episodes, 20-session gap | Candidate days in multi-day episodes | Largest episode |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 78,607 | 3,901 | 14,845 | 75,238 (95.7%) | 50 candidate days |
| Validation | 33,226 | 3,397 | 6,479 | 31,749 (95.6%) | 58 candidate days |

An episode groups consecutive candidate appearances of one observed ID when the gap is at most 20 **sessions in that frozen split**. A gap of more than 20 starts another episode. At 60 sessions, episode counts are 9,841 Train and 4,610 Validation; at 126 sessions, 6,564 and 3,633. These are descriptive cooldown sensitivities, not optimized strategy settings. One episode can include intermittent candidate days; its largest count is the number of candidate days, not elapsed calendar/session duration.

The split folders supply the complete 753/235 observed session calendars. Episodes are intentionally never joined across Train and Validation, because the intervening month is absent from those folders. The scanner's causal input is up to 126 contiguous security-specific bars, so a 20/60/126-session episode is **not** proof that images or input windows are independent. The observed ID is not a certified issuer identity. These counts support a future grouped/cooldown sampling design, but do not select one or claim model performance.

The audit reads no raw prices, human labels, future outcomes, Test/Fresh or LEAN orders. Formal box execution gates remain unresolved under the free-data route. The [bounded work order](../../codex/tasks/2026-10-20-box-candidate-recurrence-audit.md) records scope. Focused tests: **2 passed**. Full-project pytest with `STOCK_RADAR_TEST_LEAN=1`: **824 passed, 8 skipped, one existing `websockets.legacy` deprecation warning**. The test flag includes eligible local LEAN tests; it is not a box LEAN backtest.
