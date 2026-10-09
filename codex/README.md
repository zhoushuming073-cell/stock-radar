# Codex work orders

This is the canonical repository location for Codex work instructions.

## How to use

1. In Codex, open the **stock-radar** repository and synchronize with the latest `main` (do not overwrite local uncommitted or private data).
2. Tell Codex: **“Read `AGENTS.md` and `codex/tasks/ACTIVE.md`, then execute the linked work order following its gates.”**
3. The active pointer is `codex/tasks/ACTIVE.md`. It either identifies one active approved task **or explicitly records that implementation is paused**.
4. Historical work orders remain under `codex/tasks/` for reproducibility; do not edit an accepted task in place to erase its original scope. Update the active pointer only when the user authorizes a new task.
5. Every work order must state current authoritative research plan, scope, acceptance evidence, protected files/credentials, stop conditions, and how to report results.
6. An instruction file is **not** an automatic job. Codex must actually read the correct GitHub revision, confirm local state and request any required approval; a GitHub commit alone does not perform local work.

Current research authority: [Research Master Guide](../docs/RESEARCH_MASTER_GUIDE.md). The dual-stage v3 document is now a shared Vision/Human/Y subsystem specification, not the sole project roadmap.

Do not commit real market candles/images, private label data, the Label Studio database, local sessions or credentials. Historical acceptance reports are immutable audit evidence; current status belongs to the single canonical ledger.