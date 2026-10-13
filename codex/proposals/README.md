# Stock Radar — Proposed Codex Research Briefs

> Updated: 2026-10-13  
> Status: **Research proposals, NOT active work orders**. This index neither authorizes execution nor supersedes `codex/tasks/ACTIVE.md`.

This directory preserves two **independent, testable research directions** formulated from peer-reviewed finance and weak-supervision literature. They are Codex-oriented briefs, not proof of profitability and not a commitment to implement both simultaneously.

| ID | Research track | Immediate engineering hypothesis | Dependencies | Proposed first gate |
| --- | --- | --- | --- | --- |
| BOX-LQ1 | [Box Structure Ontology, Label Reliability & Multi-scale Numeric Representation v1.1](2026-10-13-box-structure-label-quality-v1-1.md) | Establish reliable human definitions, sampling controls, and causally masked numeric OHLCV representations **before** training a real model | Box Labeling v1 code in **unmerged PR #21**; 30 prepared tasks, 0 genuine human labels | Verify PR #21 code, fix proven masking/coverage problems and run a human-label reliability pilot |
| S1 | [Market Shock Transmission, Relative Dislocation & Resilience](2026-10-13-shock-transmission-resilience-s1.md) | Test whether abnormal stock-vs-peers shocks and risk/liquidity regime interactions contain incremental short-horizon information | Frozen RI v1; independent of Box / Vision; no historically trustworthy news event layer yet | **S1.0 data feasibility audit**, then separate authorization for event outcome analysis |

## Mandatory Codex entry sequence

1. Open the repository, synchronize without overwriting private local data, and read `AGENTS.md`.
2. Read the canonical ledger `reports/journey-2026-09-30-0651-📌当前总账.md`.
3. Read `docs/RESEARCH_MASTER_GUIDE.md` and `codex/tasks/ACTIVE.md`.
4. Only when the owner explicitly authorizes a proposal and updates the active work-order pointer, follow **that single activated brief**; do not infer implementation permission from a document title, GitHub branch, PR or commit.
5. For BOX-LQ1: check the latest unmerged PR #21 head and its acceptance, and preserve all v1 annotations. Do not recreate unmerged code in main blindly.
6. For S1: use main's read-only Research Infrastructure v1, run feasibility before looking at future outcomes, and enforce price-basis / PIT / OOS boundaries.

Both briefs fit the project's existing research taxonomy as **Quant-only** research or shared measurement layers; they do not create a fourth top-level family. Box pattern recognition does **not** establish trading profitability. Statistical shock residuals do **not** establish economic causation or forced-selling events.

## Governance and privacy

- The current `ACTIVE.md` task is unchanged. Both proposals are **NOT_RUN**.
- No human labels or observed Alpha have been created by adding these files.
- No historical database or private OHLCV, SVGs, identities, raw study outcomes, personal annotation DB or credentials are committed.
- No QuantConnect Cloud, live broker execution, external paid data or result-driven threshold tuning is authorized.
- Future implementation should use its own versioned branch/PR, test results and explicit owner-approved work order. Audit failures and negative scientific findings are valid results.

## Research deliverables vs implementation

This PR supplies only **proposal documents and navigation**. Running the research is a separate future action. No progress in either scientific project should be inferred from a passing Markdown review or merged documentation.