# Q1/Q2 QuantConnect Cloud validation boundary

**Actual 2026-10-09 status: BLOCKED / NOT_RUN.** Q1 Train and Validation fail frozen required-price/safety dependencies; Q2 Native Train/Validation passed execution. The complete mandatory local gate therefore has not passed. No new Cloud projects or strategy jobs were created. This is a local-data blocker, not an assertion that Cloud itself failed. Draft PR13 remains unmerged. See the [actual acceptance](../reports/acceptance/q1-q2-quant-infrastructure-backtest-2026-10-09.md).

Cloud is a separate LEAN runtime, not the local Native installation. Results may differ because of data normalization, subscription/universe coverage, corporate-action handling, fills and fees. A common engine name does not prove an identical research environment.

The active work order requires all mandatory local engineering, real candidate/data and Native execution gates before Cloud strategy jobs. Existing old platform data-export hold remains intact. No raw local OHLCV upload or QC-reference export/reconstruction, no paid resource purchase, no broker connection.

- **Mode A, preferred:** own selector source generated from the frozen accepted Q1/Q2 kernels, QC-hosted historical data, independent selection and LEAN execution. Validate current Terms, free-tier access and file/resource limits before staging. No manually rewritten strategy approximation.
- **Mode B, fallback only:** frozen local signals, QC-hosted execution prices, explicit execution-only interpretation. This does not validate the selection layer.
- **BLOCKED:** missing local execution gate, account/free-tier/platform/Terms limitation or insufficient safe input. Record the exact reason; do not label a generated bundle or compilation as completed Cloud backtest.

Use new strategy projects `SR-Q1-Fuzzy-Quant-v1` and `SR-Q2-Channel-Quant-v1` only after the gate. Existing mapping/split smoke projects and old data-export campaign are independent historical evidence. Their passes are not Q1/Q2 strategy validation. Project/backtest IDs, mode, actual completion and artifacts must appear in the dated acceptance report if execution occurs.

The dated acceptance report is authoritative for this task's actual Cloud status. This file specifies the boundary and does not claim that a Cloud project has run.

## Execution closure follow-up — 2026-10-09

Actual read-only preflight still blocks Q1 (Train2 / Validation1). New source downloads and official events have not established accepted homogeneous execution dependencies. 778 Native-inclusive tests pass, Q2 artifacts reconcile and Daily recomputes exactly; these do not replace missing Q1 strategy acceptance. Cloud remains **NOT_RUN_LOCAL_GATE_BLOCKED**, no Mode/project/backtest IDs. PR13 remains Draft.
