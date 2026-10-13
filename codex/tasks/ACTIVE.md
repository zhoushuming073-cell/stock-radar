# Active Codex task

**Status: BOX ROADMAP REVISION — DOCS ONLY; detector implementation NOT ACTIVE**

The owner authorized a research-direction and task-priority **document update** on 2026-10-13. This reviewed PR #23 branch now points to the [consolidated box development path](../../docs/BOX_RESEARCH_DEVELOPMENT_PATH.md). The next proposed engineering priority is a causal, replaceable, open-source-assisted `RangeDetector` (Stage A), followed by six-stock and independent blind quality review (Stage B). The old numeric OHLCV CNN/TCN scaffold is retained as an optional later comparator, not the mandatory box-recognition path.

The October 11 [numeric labeling/data pipeline order](2026-10-11-box-structure-numeric-dl-labeling.md) is historical, not a standing authorization for new CNN/TCN work. Preserve its artifacts and receipts. [PR #21](https://github.com/zhoushuming073-cell/stock-radar/pull/21) contains the unmerged box labeling/mask work; dependent draft [PR #24](https://github.com/zhoushuming073-cell/stock-radar/pull/24) completed BOX-LQ1 P0/P1 engineering with pilot-ready v1.1 labels/UI. Formal human labels were zero at that acceptance. Neither PR is treated as merged here.

**Permitted by this status:** review and revise the roadmap, technical selection, and the Stage B acceptance protocol; validate and submit these documentation changes to PR #23. **Not authorized:** installing new dependencies, writing/running a detector, collecting new real labels, training a model, outcome research, Historical Test/Fresh work, LEAN/QC backtests, frozen database changes, paid/broker actions or merging any PR.

To begin Stage A, obtain an explicit owner instruction and replace this file with a bounded implementation work order on a reviewable branch. Stage B, lower-band strategy rules and LEAN each require their own gates. Keep Research Infrastructure v1 and the three-family Research Master Guide unchanged in meaning. S1 remains an independent later feasibility track.
