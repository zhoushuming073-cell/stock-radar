# Active Codex task

**Status: ACTIVE — Box Structure Numeric Deep Learning labeling/data pipeline v1**

Current work order:
[2026-10-11 Box Structure Numeric Deep Learning — causal labeling and training-data pipeline v1](2026-10-11-box-structure-numeric-dl-labeling.md)

User-authorized objective:
- supersede the prior Q2 v1.3 implementation priority;
- build a causal historical box/range labeling workflow on Research Infrastructure v1;
- use a replaceable, permissive high-recall candidate prefilter to improve human-labeling throughput without letting the prefilter define Ground Truth;
- show the human simultaneous historical Daily / Weekly / Monthly candlestick views whose latest observation is the historical decision date T, never today and never post-T;
- persist a new versioned box-structure label contract;
- export training-ready **numeric OHLCV** multi-scale tensors;
- implement a lightweight multi-scale 1D CNN/TCN training scaffold for later supervised learning;
- stop before substantive real-label model training, future-return evaluation, strategy backtesting, or alpha claims.

Modality decision:
- candlestick charts are **human annotation visualizations only**;
- the deep-learning model consumes causal numerical OHLCV time series;
- do not implement an image-only CNN or use PNG/JPEG/SVG pixels as the default model feature representation.

This supersedes the Q2 v1.3 work order as the **active priority**. Preserve Q1/PR13, Q2 v1.1/v1.2/v1.3 work orders, Draft PRs, historical evidence, and frozen artifacts; do not delete or rewrite them.

Not authorized:
- substantive production-quality training on fabricated or insufficient labels;
- future-return-driven labeling or threshold tuning;
- Historical Test/Fresh consumption for development;
- portfolio/LEAN/QC backtests for this task;
- QC Cloud access/retry;
- database expansion/rebuild;
- paid services or broker/live actions;
- implementation merge to main without later explicit user approval.

Codex start instruction:

> Synchronize latest main, read AGENTS.md → canonical ledger → Research Master Guide → this ACTIVE file → the 2026-10-11 Box Structure Numeric Deep Learning work order. Implement only that work order. Reuse Research Infrastructure v1 and the existing local labeling security/audit patterns, enforce the T-close causal boundary, keep candidate generation replaceable and high-recall, treat charts as human-only views, export numeric multi-scale OHLCV tensors, validate the training scaffold, and stop before substantive model training or any profitability evaluation.
