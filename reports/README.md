# Reports Log Index

> **Purpose:** Navigation only. This file is not a journey log.

## Current source of truth

- **📌 当前总账:** [Canonical status / active backlog](journey-2026-09-30-0651-📌当前总账.md) — updated 2026-10-07 Asia/Shanghai.
- **PIT migration acceptance:** [2026-10-07 · Local reconstruction and limitations](pit-acceptance-2026-10-07.md) — pinned data, price gaps, production Scanner samples and correctness regression evidence.
- **PIT trust / retired-price acceptance:** [2026-10-07 · Reviewed identities, events and real OHLCV](pit-data-trust-acceptance-2026-10-07.md) — installed enrichment, six-dimension readiness, 342 tests and pre-task daily-update exception; first acceptance preserved.
- **PIT final execution acceptance:** [2026-10-07 · Frozen Run closure, native actions and formal blockers](pit-final-acceptance-2026-10-07.md) — Global and Run scorecards remain separate; no false portfolio completion.
- **Latest PIT data clearance:** [2026-10-07 · IREN continuity, full source probes and completion boundary](pit-clearance-acceptance-2026-10-07.md) — installed identity correction, 397 native-inclusive tests; formal Run still data-blocked, no PIT return comparison.
- **Current development-stage report:** [2026-10-06 · Research + local LEAN integration](development-status-2026-10-06.md) — detailed Chinese overview, acceptance scope, limitations and next milestones.

The canonical journey owns completed/open/partial backlog status. The dated
development report explains the verified release stage; it does not create a
second active backlog. Historical reports are preserved as evidence.

## Journey filename convention

`journey-YYYY-MM-DD-HHMM-<emoji><status>.md`

- Date/time uses the GitHub repository commit timestamp in UTC.
- Exactly one journey may be `📌当前总账`.
- `📌当前总账` = current canonical status/backlog.
- `✅已完成` = closed backlog, implementation or acceptance evidence.
- `🟡部分完成` = historical log with some unfinished work still relevant.
- `❌未完成` = standalone unresolved historical work; use sparingly because current work belongs in the canonical journey.
- `🗂️历史归档` = historical mixed planning/research record, no longer actionable.
- `🧭路线图` = optional/future direction, not implementation evidence.

When a new canonical status snapshot is created, rename the previous `📌当前总账` journey to `✅已完成` or `🗂️历史归档`, create the new timestamped `📌当前总账` journey, and update this index.

## Journey inventory

| File | Status | Purpose |
| --- | --- | --- |
| `journey-2026-09-30-0651-📌当前总账.md` | 📌 当前总账 | Current consolidated project status and backlog |
| `journey-2026-10-06-1750-🟡部分完成.md` | 🟡 部分完成 | Historical PIT engineering/data acceptance; remaining data trust belongs in the canonical ledger |
| `journey-2026-09-29-0426-🗂️历史归档.md` | 🗂️ 历史归档 | Mixed 2026-09-29 planning/history; surviving work migrated to current ledger |
| `journey-2026-09-29-0629-✅已完成.md` | ✅ 已完成 | First research-integrity bug backlog; closed |
| `journey-2026-09-29-1306-✅已完成.md` | ✅ 已完成 | Acceptance/readiness evidence for the first backlog |
| `journey-2026-09-29-1351-✅已完成.md` | ✅ 已完成 | Follow-up backlog; all seven items closed |
| `journey-2026-09-29-1421-🧭路线图.md` | 🧭 路线图 | Open-source reuse/adoption roadmap |
| `journey-2026-09-30-0124-✅已完成.md` | ✅ 已完成 | Bug-mining round 2; all ten items closed |
| `journey-2026-09-30-0620-✅已完成.md` | ✅ 已完成 | Fix-pass and local verification evidence |

## Non-journey reports

- [Development status · 2026-10-06](development-status-2026-10-06.md): current architecture, Phase A–F migration scope, local acceptance evidence, operational boundaries and planned work.
- [Initial PIT architecture audit · 2026-10-07](pit-initial-audit-2026-10-07.md) and [PIT acceptance](pit-acceptance-2026-10-07.md): before/after database architecture and honest data readiness.
- `phase2/` contains historical pre-v3 research artifacts and datasets. It is not an active project backlog.
- `personal-research/` contains owner-authored personal research reports and preserved research conclusions.
- Contracts and specifications belong under `docs/`, not in the journey status stream.
