# Current research direction — three-path program · 2026-10-09

**Status: ACTIVE RESEARCH ORGANIZATION / METHODS STILL UNDER CONSTRUCTION.**

The project no longer treats v1/v2/v3, Vision-H, Vision-Y, Sequence and Fusion as separate top-level roadmaps.

There are now exactly **three primary research families**:

1. **Quant-only**
   - Q1: fuzzy-shape-v1 — implemented candidate/feature method, predictive value not validated.
   - Q2: parallel-channel-v1 — Draft PR #10, source-only experimental Quant method, not merged or fully accepted.
   - Q3: later Q1/Q2 ensemble or classical ML on Quant features.

2. **Quant + Vision**
   - classical machine-learning Fusion;
   - deep-learning Fusion.

3. **Vision-only**
   - classical machine-learning visual model;
   - deep-learning visual model.

Human blind labels (H_blind), retrospective review (H_review), objective future outcomes (Y_future), numeric sequence models, Train/Validation/Test/Fresh, LEAN/QC and GPT/news review are **shared supervision / control / validation layers**, not additional primary routes.

**Current project phase:** infrastructure + method definition. The repository contains old exploratory backtests, LEAN smoke executions and forward statistics, but **there is no formal current-strategy backtest or fresh OOS result proving Q1/Q2/Vision/Fusion alpha**. Vision v3 labeling engineering is accepted but the user has paused human trial. Model training remains not started as a formal program.

The authoritative taxonomy is [Research Master Guide](../../docs/RESEARCH_MASTER_GUIDE.md). Completion status remains in the [canonical ledger](../journey-2026-09-30-0651-📌当前总账.md).

Draft PR #10 remains separate until real-market validation and review. Historical v1/v2/v3 documents stay for methodology and provenance, not as competing master plans.
