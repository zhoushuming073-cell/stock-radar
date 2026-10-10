# Active Codex task

**Status: ACTIVE — final Q2 v1.3 relaxed plugin + Research Infrastructure v1 Strategy Lab adapter**

Current work order:
[2026-10-10 Q2 v1.3 relaxed plugin backtest](2026-10-10-q2-v1.3-relaxed-plugin-backtest.md)

User-authorized objective:
- make the smallest backward-compatible Strategy Lab/plugin change needed for causal past-only historical windows;
- use the finalized Research Infrastructure v1 / `shape_research_universe_v1` as the default data backend for this and future new local historical strategy/plugin research;
- implement the final relaxed Q2 v1.3 without return-driven tuning;
- verify a non-degenerate candidate-only funnel;
- generate `q2_v13_relaxed_channel_plugin.zip`;
- stop before the user's final local portfolio backtest so the user can import the ZIP in the web UI and run it once.

This supersedes the old Q1/QC work order as the **active priority**. Preserve Q1/PR13, Q2 v1.1/v1.2 and all historical evidence; do not delete or rewrite them.

Not authorized:
- QC Cloud access/retry;
- Q1 blocker work;
- Vision/Fusion/Q3 training;
- database expansion/rebuild;
- Historical Test/Fresh return tuning;
- paid services or broker/live actions;
- implementation merge to main without later user approval.

Codex start instruction:

> Synchronize latest main, read AGENTS.md → canonical ledger → Research Master Guide → this ACTIVE file → the Q2 v1.3 work order. Implement only that work order. Use Research Infrastructure v1 for new historical plugin research, keep old plugins backward compatible, deliver the tested Q2 v1.3 ZIP, and stop before the user's final portfolio backtest.
