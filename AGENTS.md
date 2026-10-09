# Stock Radar — Repository agent entrypoint

Before performing any task, read in this order:
1. `reports/journey-2026-09-30-0651-📌当前总账.md` — canonical completion status / blockers.
2. `docs/RESEARCH_MASTER_GUIDE.md` — current authoritative research taxonomy and comparison rules.
3. `codex/tasks/ACTIVE.md` — whether any implementation task is currently authorized.
4. Only then read subsystem / historical plans linked by the master guide if relevant.

The project currently recognizes exactly three top-level research families: **Quant-only**, **Quant + Vision**, and **Vision-only**. Human labels, future outcomes, sequence controls, LEAN/QC and GPT/news review are shared supervision / control / validation layers, not extra top-level roadmaps.

Do not infer that a research document authorizes implementation. In particular, do not start model training, full backtests, Historical Test/Fresh evaluation, QC jobs, paid services, data mutation or merging an experimental PR unless `codex/tasks/ACTIVE.md` explicitly authorizes it.

`Research Infrastructure v1` and frozen Strategy 2 semantics are protected. Keep market data, credentials, real human annotations and detailed historical mappings in ignored local storage. Do not rewrite historical acceptance reports to match later decisions.

If an old v1/v2/v3 document conflicts with `docs/RESEARCH_MASTER_GUIDE.md`, the master guide controls research classification; the canonical ledger controls actual completion status.
