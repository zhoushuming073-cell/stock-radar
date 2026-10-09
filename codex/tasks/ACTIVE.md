# Active Codex task

**Status: ACTIVE — Q1/Q2 Quant infrastructure, local LEAN → QC Cloud, latest-session watchlist**

Current work order:
[2026-10-09 Q1/Q2 Quant infrastructure + backtest + Daily Scanner](2026-10-09-q1-q2-quant-backtest-daily-scanner.md)

Current research authority:
- [Research Master Guide](../../docs/RESEARCH_MASTER_GUIDE.md)
- [Canonical project ledger](../../reports/journey-2026-09-30-0651-📌当前总账.md)

Authorized scope:
1. productionize and validate Q1 fuzzy-shape-v1;
2. harden/reconcile Q2 parallel-channel-v1 from Draft PR #10;
3. implement latest-session Q1/Q2/overlap Daily Scanner;
4. freeze Q1/Q2 research versions;
5. run local QuantConnect LEAN Q1-only and Q2-only research backtests;
6. only after local PASS, run bounded compliant QuantConnect Cloud validation/backtests, respecting the documented Terms/export hold.

Not authorized:
- Vision / Fusion training;
- Q3 optimization;
- return-driven Q1/Q2 threshold tuning;
- Fresh-OOS claims;
- paid QC resources;
- broker/live orders.

Codex start instruction:

> Synchronize stock-radar to latest main. Read AGENTS.md, docs/RESEARCH_MASTER_GUIDE.md, the canonical ledger, and codex/tasks/ACTIVE.md. Execute the linked Q1/Q2 work order end to end, using real local data/LEAN where available, respecting all freeze/Cloud/export gates, and report actual evidence only.
