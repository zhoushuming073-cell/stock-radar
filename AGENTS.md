# Stock Radar — Repository agent entrypoint

Before performing tasks, read:
1. `reports/journey-2026-09-30-0651-📌当前总账.md` (canonical current status).
2. `docs/QUANT_VISION_DUAL_STAGE_RESEARCH_PLAN.md` (current active Quant/Vision research direction).
3. `codex/tasks/ACTIVE.md` (current user-approved Codex task and detailed work order).

Follow the detailed task's explicit scope and stop conditions. **Do not infer that repository docs alone authorize model training, cloud evaluation, data mutation, paid services or merge of another draft PR.**

`Research Infrastructure v1` and Strategy 2 frozen semantics are protected. Keep market data, secret values, human annotations and detailed historical mapping in ignored local storage. Do not rewrite historical acceptance to match a changed plan. Confirm the current GitHub `main` and branch divergence before edits; never overwrite local working files.

If the active task conflicts with current `main` or another open PR, reconcile by an explicit reviewed change, not a forced checkout/reset or quiet rollback.