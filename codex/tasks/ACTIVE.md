# Active Codex task

**Status: BOX ROADMAP ALIGNMENT — DEPENDENT ENGINEERING DRAFTS; FORMAL QUALITY/RETURN UNVERIFIED**

This draft [PR #26](https://github.com/zhoushuming073-cell/stock-radar/pull/26)
contains the [Stage B diagnostic acceptance](../../reports/acceptance/box-range-stage-b-2026-10-13.md)
and [as-of-T identity follow-up](../../reports/acceptance/box-range-stage-b-identity-followup-2026-10-14.md).
The separate 48-task blind set and isolated human store remain intact; the
[progress gate](../../reports/acceptance/box-range-stage-b-human-gate-followup-2026-10-14.md)
found 0/48 formal labels. On 2026-10-14 the owner cancelled mandatory
human blind review. No assistant-generated Ground Truth or detector-quality
score replaces it. Observed CIK/ticker episodes do not certify official
security-class identity. PR #21 is merged; PR #24–#26 remain drafts.

This draft [PR #25](https://github.com/zhoushuming073-cell/stock-radar/pull/25)
adds the bounded [Stage A detector work order](2026-10-13-box-range-detector-stage-a.md)
and [local acceptance](../../reports/acceptance/box-range-detector-stage-a-2026-10-13.md):
two causal, replaceable baselines, 22 focused tests, 754 passed / 8 skipped
at the dated full regression, and a real 96-security-day Train/Validation
diagnostic with 69 detector-state disagreements. These are engineering
measurements, not structure accuracy. PR #21 is merged; PR #24 and this PR
remain drafts. Mandatory human blind review was later cancelled.

PR #21's box-labeling foundation is now merged into main (`d95d12c`). This
branch adds the [BOX-LQ1 P0 audit](../../reports/acceptance/box-lq1-p0-gap-audit-2026-10-13.md)
and [P1 v1.1 acceptance](../../reports/acceptance/box-label-quality-v1-1-2026-10-13.md):
isolated store/UI, ten browser tasks, 722 passed / 18 skipped at the dated
receipt, zero formal human labels. The owner's later cancellation means a
human blind pilot is optional, not a release gate. This PR remains a draft;
no synthetic Ground Truth, model training or structure accuracy is claimed.

The owner authorized a research-direction and task-priority document update on 2026-10-13. This PR #23 branch points to the [consolidated box development path](../../docs/BOX_RESEARCH_DEVELOPMENT_PATH.md). Since that revision, causal detector baselines, bounded diagnostics, lower-band context and the full Train/Validation candidate scan were implemented on dependent draft [PR #25](https://github.com/zhoushuming073-cell/stock-radar/pull/25), [#26](https://github.com/zhoushuming073-cell/stock-radar/pull/26) and [#27](https://github.com/zhoushuming073-cell/stock-radar/pull/27). They are not merged into main. Candidate coverage is engineering evidence, not detector accuracy, a trading signal or a formal return result. The old numeric OHLCV CNN/TCN scaffold remains an optional later comparator.

The October 11 [numeric labeling/data pipeline order](2026-10-11-box-structure-numeric-dl-labeling.md) is historical, not a standing authorization for new CNN/TCN work. Preserve its artifacts and receipts. [PR #21](https://github.com/zhoushuming073-cell/stock-radar/pull/21) is merged; this dependent draft [PR #24](https://github.com/zhoushuming073-cell/stock-radar/pull/24) contains BOX-LQ1 P0/P1 engineering with pilot-ready v1.1 labels/UI. Formal human labels were zero at that acceptance. On 2026-10-14 the owner cancelled mandatory human blind review. Keep independent human judgments optional and never fabricate labels or claim an accuracy estimate from detector agreement.

**Permitted on this branch:** align and validate the PR #23 planning documents with the later user decision and dependent engineering receipts. This docs-only task does not itself authorize new dependency installation, detector changes, synthetic human labels, model training, outcome research, Historical Test/Fresh work, LEAN/QC backtests, frozen database changes, paid/broker actions or merging experimental implementation PRs.

The dependent engineering branch keeps its own bounded work orders and acceptance. Formal box LEAN still lacks trusted as-of-T security-class identity, corporate-action/factor coverage and accepted execution prices under the owner's free-data route. Do not promote Stage D candidates to executable signals or profitability evidence. Keep Research Infrastructure v1 and the three-family Research Master Guide unchanged in meaning. S1 remains independent.
