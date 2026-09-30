# Reports Log Index

> **Purpose:** Navigation only. This file is not a journey log.

## Current source of truth

- **ACTIVE:** `journey-2026-09-30-0651-active.md`

All current completed/open/partial project status belongs in the active journey.

## Journey filename convention

`journey-YYYY-MM-DD-HHMM-status.md`

- Date/time uses the GitHub repository commit timestamp in UTC.
- Exactly one journey may be `active`.
- `active` = current canonical status/backlog.
- `completed` = closed backlog, implementation or acceptance evidence.
- `archived` = historical mixed planning/research record, no longer actionable.
- `roadmap` = optional/future direction, not implementation evidence.

When a new canonical status snapshot is created, rename the previous `active` journey to `archived` or `completed`, create the new timestamped `active` journey, and update this index.

## Journey inventory

| File | Status | Purpose |
| --- | --- | --- |
| `journey-2026-09-30-0651-active.md` | 🟢 ACTIVE | Current consolidated project status and backlog |
| `journey-2026-09-29-0426-archived.md` | 🗂️ ARCHIVED | Mixed 2026-09-29 planning/history; surviving work migrated to ACTIVE |
| `journey-2026-09-29-0629-completed.md` | ✅ COMPLETED | First research-integrity bug backlog; closed |
| `journey-2026-09-29-1306-completed.md` | ✅ COMPLETED | Acceptance/readiness evidence for the first backlog |
| `journey-2026-09-29-1351-completed.md` | ✅ COMPLETED | Follow-up backlog; all seven items closed |
| `journey-2026-09-29-1421-roadmap.md` | 🧭 ROADMAP | Open-source reuse/adoption roadmap |
| `journey-2026-09-30-0124-completed.md` | ✅ COMPLETED | Bug-mining round 2; all ten items closed |
| `journey-2026-09-30-0620-completed.md` | ✅ COMPLETED | Fix-pass and local verification evidence |

## Non-journey reports

- `phase2/` contains historical pre-v3 research artifacts and datasets. It is not an active project backlog.
- Contracts and specifications belong under `docs/`, not in the journey status stream.
