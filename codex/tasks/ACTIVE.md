# Active Codex task

**Status: ACTIVE — close Q1 execution dependencies, re-run frozen local LEAN, then QC Cloud**

## Actual execution checkpoint — 2026-10-09

**PARTIAL / BLOCKED_LOCAL_EXECUTION** on Draft PR[#13](https://github.com/zhoushuming073-cell/stock-radar/pull/13). Q1 parity, hardened Q2, actual Daily CLI/API/browser workflow, full756-test Native-inclusive regression and real Q2 Train/Validation Native runs completed. Q1 Train/Validation are blocked by three frozen execution dependencies (missing forward prices or unsafe price/identity); no substitutions or weaker gates. QC Cloud NOT_RUN; main not merged; Draft10 not closed. [Acceptance](../../reports/acceptance/q1-q2-quant-infrastructure-backtest-2026-10-09.md), [current ledger](../../reports/journey-2026-09-30-0651-📌当前总账.md).

Continue only within this work order to resolve those trustworthy execution inputs and repeat the unchanged local study. Do not infer permission for training, Q3/date/weight optimization, data-gate relaxation, frozen database mutation or Cloud jobs before mandatory local PASS.

Current work order:
[2026-10-09 Q1 execution closure + QC Cloud follow-up](2026-10-09-q1-execution-closure-qc-cloud.md)

Parent implementation:
- Draft PR [#13](https://github.com/zhoushuming073-cell/stock-radar/pull/13)
- branch `feature/q1-q2-daily-lean-20261009`
- checkpoint head `77424fc5afb69098ef8eabd1931a28e3bdf86f6e`

Current checkpoint:
- Q1 parity / Q2 v1.1 / Daily Scanner engineering completed on PR #13.
- 756 tests PASS with Native LEAN.
- Q2 local bounded Native results completed.
- Q1 remains NOT_RUN_DATA_BLOCKED on three trusted execution-data dependencies.
- QC Cloud remains BLOCKED/NOT_RUN until the full local gate passes.

Authorized scope:
1. identify and resolve the exact three Q1 historical execution dependencies with trusted evidence;
2. preserve frozen Q1/Q2 selector/config/date/cost contracts;
3. re-run the exact frozen Q1 Train/Validation local Native LEAN study;
4. regression-check frozen Q2 and Daily Scanner;
5. run full test/protection gates;
6. only after full local PASS, attempt compliant QC Cloud Mode A/B;
7. update and decide release of PR #13.

Not authorized:
- removing/substituting blocked candidates;
- weakening price/identity gates;
- return-driven parameter tuning;
- Q3;
- Vision/Fusion;
- Historical Test/Fresh efficacy;
- paid QC resources;
- raw QC data export/workarounds;
- broker/live trading.

Codex start instruction:

> Synchronize stock-radar main, read AGENTS.md, the Research Master Guide, canonical ledger and codex/tasks/ACTIVE.md. Then continue Draft PR #13 from its actual checkpoint. Resolve only the Q1 trusted execution dependencies under the unchanged frozen study, re-run local LEAN, and touch QC Cloud only after every mandatory local gate passes. Report actual evidence only.
