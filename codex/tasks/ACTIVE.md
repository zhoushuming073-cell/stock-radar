# Active Codex task

**Current work order (2026-10-09):** [Quant + Vision Dual-Stage Review v3 — implement D1/D2/D3](2026-10-09-dual-stage-quant-vision-v3.md).

**Current authoritative plan:** [Quant + Vision Dual-Stage Research Plan v3](../../docs/QUANT_VISION_DUAL_STAGE_RESEARCH_PLAN.md).

Scope: reconcile the still-draft PR #7 implementation with latest main, build past-only SVG and server-gated future SVG, split H_blind/H_review, compute separate bounded Y_future, run actual local tests and browser acceptance, and stop before any model training or formal OOS/QC.

Codex should synchronize and inspect the repository, read \`AGENTS.md\` and the linked full work order, then execute it. This file is a task pointer, **not** proof that the implementation has run or succeeded.

User can start the next Codex chat with:

> Read \`AGENTS.md\` and \`codex/tasks/ACTIVE.md\` in my stock-radar repository. Follow the linked work order end to end, honoring all gates and stop conditions. Report actual code changes, tests and PR.

Do not replace the active task solely because a newer draft PR exists; change it only after a user decision.
