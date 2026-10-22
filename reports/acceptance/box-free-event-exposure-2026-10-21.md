# Box free-source event exposure follow-up — 2026-10-21

**Result: two cash-dividend review leads in the bounded Validation cohort; no complete corporate-action certification.** This [work order](../../codex/tasks/2026-10-21-box-free-event-exposure-followup.md) follows the [accepted raw-price parity check](box-free-raw-price-parity-2026-10-21.md). The [aggregate receipt](../evidence/box-free-event-exposure-2026-10-21.json) binds the private 142-candidate queue and price-parity receipt to the local pinned Dolt event scans. The split and dividend scans use source version `vt6qeesk27k07492k5jc5b7p04mf0s6o`, cover 2023-12-12–2025-09-22, and contain 1,207 and 54,810 source event rows respectively. The local file SHA-256 values are in the receipt. The script rejects missing coverage, failed HTTP receipts or a changed source version.

| Ten-session diagnostic exposure | Candidate-days with a source event | Candidate-event rows | Distinct private symbol/date events |
| --- | ---: | ---: | ---: |
| Split | 0 | 0 | 0 |
| Cash dividend | **7** | **7** | **2** |

The two dividend events are linked to issuer-issued dated declarations available before the exposed candidate decisions. The declarations corroborate common-share class, amount, record date and payment date. The source URLs, symbol/date/amount mappings and review notes are stored only in ignored `stock-radar/data/references/box-cta-symbol-v1/event-exposure-source-review-20251021.json`, SHA-256 `cfc073ba92f47701d2d6f6f071814ec5e7ed75a632523d43121f15a23df2e894`. That private review does **not** independently certify the scan's ex-dividend dates. It also does not prove that there were no other events. The public receipt contains only counts, source version and file hashes.

These are **event-review leads**, not dividend entitlements or return adjustments. Entitlement depends on the actual entry and holding interval, settled ownership and LEAN cash handling; no portfolio rule or trade was run. The vendor event scans are not a complete official event ledger, and zero matched split rows do not prove absence of splits, mergers or terminal events. Historical identity/class remains observational for most of the cohort, accepted execution factors and company-action coverage are incomplete, and `formal_lean_ready=false`. No outcome, Test/Fresh data or box return was used. Formal box LEAN remains **NOT_RUN** under the owner's free-data route.

The full local project regression with `STOCK_RADAR_TEST_LEAN=1` passed **828**, skipped **8**, with one existing `websockets.legacy` deprecation warning (110.92 seconds). The independent Native LEAN integration module had passed **5/5** in the preceding parity follow-up. Neither test run is a box portfolio backtest.
