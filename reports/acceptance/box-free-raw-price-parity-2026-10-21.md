# Box free-source raw-price parity follow-up — 2026-10-21

**Result: a bounded Validation cohort has exact same-source raw-price copy parity. Formal box LEAN remains deferred.** This follow-up implements the [work order](../../codex/tasks/2026-10-21-box-free-raw-price-parity-followup.md) after the [CTA + SEC pilot](box-free-cta-sec-pilot-2026-10-21.md). The [intersection receipt](../evidence/box-free-cta-raw-intersection-2026-10-21.json) reuses the full-window audit, which rehashes 684 sealed candidate chunks and 87 CTA files for 2025-05-05–2025-09-08. The candidate file-set hash is `48189aae1a54e3607a991df0c84e9d6939b49d7a714369988e561ffdaefbbb09`. All 356 Dolt/raw candidate-days with an exact-case CTA symbol match were assessed.

| Existing evidence state | Candidate-days |
| --- | ---: |
| No known issuer conflict, raw horizon complete, accepted T-day missing | 164 |
| No known issuer conflict, raw horizon incomplete, accepted T-day missing | 19 |
| No known issuer conflict, raw horizon incomplete, accepted T-day exact, accepted horizon metadata incomplete | 12 |
| Contemporary issuer alias, raw horizon complete, accepted T-day missing | 18 |
| Known identity conflict, raw horizon incomplete, accepted T-day missing | 1 |
| No known issuer conflict, raw horizon complete, accepted T-day exact, accepted horizon metadata complete | **142** |
| **Total** | **356** |

The 142 follow-up candidate-days involve 28 **observed** security IDs. “No known conflict” is an observational classification, not official issuer or share-class certification. The private queue contains the security/date/CIK mapping and is stored only under ignored `stock-radar/data/references/box-cta-symbol-v1/` in the original research root. Its SHA-256 is `fb026fce19455dcd2d7b02fec75cc98200675270a21028c0d86642fb1a51a60c`; the queue and source price rows are not committed.

The [accepted raw-price parity receipt](../evidence/box-free-accepted-raw-parity-2026-10-21.json) compares the following ten in-Validation sessions for each of those 142 candidate-days. Each comparison requires exactly one Shape `raw` row and one accepted `raw` row, the same symbol, exact open/high/low/close/volume values, and the frozen accepted provenance. **1,420/1,420 candidate-session comparisons matched**; overlapping candidate horizons represent **667 distinct observed security/date pairs**. The accepted raw-price database SHA-256 is `1fd1996e88cc91ab25baf9a4f7615478d99506672ed47c028eaecfefd0240545`. The ten sessions are a data-coverage diagnostic, **not** a proposed maximum holding period.

This check did read post-T OHLCV values, **solely to verify equality of two stored copies of the same source**. It did not compute future outcomes, returns, P&L, trades, or strategy rankings. It did not use Test/Fresh. CTA is a post-close retrospective symbol snapshot and was not used as a T-close signal input. The two databases' equality does not provide an independent price source or establish LEAN executable prices.

The company-action and factor chain, split/dividend cash handling, security lifecycle and exact historical class/issuer identity remain uncertified. The accepted database contains `daily_bars` but no action ledger. Only five observed issuer/class cases have the earlier bounded pre-T SEC cover-page review; this follow-up did **not** extend that review to all 28 IDs. No candidate was promoted to formal status; `formal_lean_ready=false` in both receipts. The complete free historical population and portfolio-rule gates also remain open. Under the owner's free-data decision, formal box LEAN is **NOT_RUN**.

## Reproduction and testing

The scripts are `scripts/audit_box_cta_raw_gate_intersection.py` and `scripts/audit_box_accepted_price_parity.py`. Both read frozen local data; the former writes only an ignored private queue when requested, and the latter emits aggregate counts only. The existing CTA full-window receipt and frozen database manifests are required. The single-row and exact-provenance comparator has fail-closed regression coverage in `tests/test_box_accepted_price_parity.py`.

The full project regression with `STOCK_RADAR_TEST_LEAN=1` passed **827**, skipped **8**, with one existing `websockets.legacy` deprecation warning (112.45 seconds). The independent local Native LEAN integration module passed **5/5** when run separately. This is software regression coverage; **no box strategy LEAN backtest** was run.
