# Active Codex task

**Status: BOX RANGE DETECTOR STAGE B ENGINEERING READY — HUMAN QUALITY GATE PENDING**

The owner authorized continuing the existing roadmap on 2026-10-13 without
repeated permission requests. [Stage B work order](2026-10-13-box-range-stage-b.md)
is active on a branch stacked on Stage A PR #25 → PR #24 → PR #21. Engineering
may proceed through the existing route, but human judgments and data-quality
gates cannot be waived or simulated. The independent blind 48-task set is frozen
and the local smoke path passed browser checks; formal human labels are still absent.
The [2026-10-14 identity follow-up](../../reports/acceptance/box-range-stage-b-identity-followup-2026-10-14.md)
separated one as-of-T name conflict from one post-T-only flag; identity remains
provisional and the human annotation store still has zero revisions.

The owner explicitly authorized Stage A on 2026-10-13 after the [revised box route in PR #23](https://github.com/zhoushuming073-cell/stock-radar/pull/23). The bounded [Stage A work order](2026-10-13-box-range-detector-stage-a.md) was executed on a branch based on unmerged [PR #24](https://github.com/zhoushuming073-cell/stock-radar/pull/24), which itself depends on [PR #21](https://github.com/zhoushuming073-cell/stock-radar/pull/21). Preserve all three review dependencies; do not treat this code as merged into main.

The [local acceptance](../../reports/acceptance/box-range-detector-stage-a-2026-10-13.md) records two causal, replaceable baselines, 22 focused tests, full regression **754 passed / 8 skipped**, and a real read-only 96-security-day Train/Validation diagnostic. Its 69 detector state disagreements are **not** a quality score. No independent human structure Ground Truth exists for that diagnostic.

The earlier numeric CNN/TCN and v1.1 labeling engineering are preserved as optional comparator/shared infrastructure, not the next mandatory detector.

Stage B does not generate human judgments. ML training, future-outcome research,
lower-band strategy signals, Historical Test/Fresh development, LEAN/QC
backtests, broker/paid activity, frozen database mutation and main merge remain
behind their actual prerequisite gates. S1 market-shock research is separate.
