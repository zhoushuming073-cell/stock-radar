# Active Codex task

**Status: BOX RANGE DETECTOR STAGE A ENGINEERING COMPLETE — STAGE B NOT ACTIVE**

The owner explicitly authorized Stage A on 2026-10-13 after the [revised box route in PR #23](https://github.com/zhoushuming073-cell/stock-radar/pull/23). The bounded [Stage A work order](2026-10-13-box-range-detector-stage-a.md) was executed on a branch based on unmerged [PR #24](https://github.com/zhoushuming073-cell/stock-radar/pull/24), which itself depends on [PR #21](https://github.com/zhoushuming073-cell/stock-radar/pull/21). Preserve all three review dependencies; do not treat this code as merged into main.

The [local acceptance](../../reports/acceptance/box-range-detector-stage-a-2026-10-13.md) records two causal, replaceable baselines, 22 focused tests, full regression **754 passed / 8 skipped**, and a real read-only 96-security-day Train/Validation diagnostic. Its 69 detector state disagreements are **not** a quality score. No independent human structure Ground Truth exists for that diagnostic.

Next proposed task: Stage B six-stock and independent blind structure-quality assessment under PR #23's protocol. It requires a separate owner instruction and a new bounded ACTIVE order. The earlier numeric CNN/TCN and v1.1 labeling engineering are preserved as optional comparator/shared infrastructure, not the next mandatory detector.

Not authorized by this completed Stage A: new formal human labels, Stage B judgments, ML training, future-outcome research, lower-band strategy signals, Historical Test/Fresh development, LEAN/QC backtests, broker/paid activity, frozen database mutation or main merge. S1 market-shock research remains a separate later track.
