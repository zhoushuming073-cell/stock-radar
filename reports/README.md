# Reports Log Index

> **Purpose:** navigation and document governance only. This file is not a journey log and does not create a second backlog.

## Current source of truth

- **📌 当前总账:** [Canonical status / active backlog](journey-2026-09-30-0651-📌当前总账.md) — the only active project ledger.
- **Current development-stage snapshot:** [2026-10-06 · Research + local LEAN integration](current/development-status-2026-10-06.md).
- When a dated report conflicts with the canonical ledger, the canonical ledger wins for current status. Dated reports remain audit evidence.

## Directory layout

| Path | Role |
| --- | --- |
| `acceptance/` | Dated acceptance reports and bounded engineering/research conclusions |
| `evidence/` | Machine-readable evidence, scorecards and supporting derived artifacts |
| `audit/` | Point-in-time architecture/audit records |
| `archive/journeys/` | Closed, partial or roadmap journey history; not an active backlog |
| `personal-research/` | Owner-authored research reports and preserved research conclusions |
| `phase2/` | Historical pre-v3 research artifacts and datasets |
| `current/` | Current stage snapshots that explain the active platform state |
| `docs/` (repository root) | Contracts and specifications; intentionally outside `reports/` |

The `reports/` root is intentionally kept small: this index plus the canonical ledger.
The final research report below retains its explicit user-requested root path;
its derived evidence and P0 queue follow the `evidence/` layout.

## PIT acceptance chain · 2026-10-07

1. [Initial local PIT reconstruction](acceptance/pit-acceptance-2026-10-07.md) — architecture, pinned data and explicit limitations.
2. [Identity / retired-price trust continuation](acceptance/pit-data-trust-acceptance-2026-10-07.md) — reviewed identities, events and real OHLCV enrichment.
3. [Final execution-gate engineering](acceptance/pit-final-acceptance-2026-10-07.md) — frozen Run closure, native actions and formal blockers.
4. [Data clearance](acceptance/pit-clearance-acceptance-2026-10-07.md) — IREN continuity and full source probes; Formal PIT remains blocked.
5. [Bulk-source benchmark / trust ceiling](acceptance/pit-source-breakthrough-acceptance-2026-10-07.md) — large candidate coverage, no false formal admission.
6. [Research-Grade PIT](acceptance/pit-research-grade-acceptance-2026-10-07.md) — **PARTIAL** research-grade evidence; real Research-Grade Native LEAN remains blocked.
7. [Final research decision audit](pit-research-final-acceptance-2026-10-07.md) — **PARTIAL / BLOCKED**; identity-safe Core competitors 29–72/day, actual-candidate gates, Top3 and missingness stress, 468 passing tests. [Derived evidence](evidence/pit-research-final-evidence-2026-10-07.json) and [focused P0 queue](evidence/pit-research-final-priority-2026-10-07.json).
8. [QuantConnect Free Cloud readiness](qc-cloud-validation-readiness-2026-10-07.md) and [2026-10-08 actual Cloud smoke](qc-cloud-smoke-validation-2026-10-08.md) — both complete Cloud smoke receipts imported and parser-verified PASS; first Layer1 pilot engine Completed but receipt unverified; further batches/reference exports HOLD due to actual Terms2.6 warning, Layer2–3 NOT_RUN and PIT BLOCKED. 470 date-project quota checks and507 native-inclusive tests passed. [Web instructions](../docs/QUANTCONNECT_FREE_VALIDATION.md).

Supporting material:
- [Initial PIT architecture audit](audit/pit-initial-audit-2026-10-07.md)
- [LEAN / PIT blocker localization](audit/pit-lean-blocker-localization-2026-10-07.md) — read-only source audit at `412c5e4`: historical request guard, current execution gates and Clone draft behavior; no new tests or Native Run.
- [Source-breakthrough human scorecard](evidence/source-breakthrough-scorecard-2026-10-07.md)
- Machine-readable evidence and JSON scorecards live under `evidence/`.

## Historical journey inventory

| File | Status | Purpose |
| --- | --- | --- |
| [2026-09-29 04:26](archive/journeys/journey-2026-09-29-0426-🗂️历史归档.md) | 🗂️ 历史归档 | Mixed planning/history; surviving work migrated to the current ledger |
| [2026-09-29 06:29](archive/journeys/journey-2026-09-29-0629-✅已完成.md) | ✅ 已完成 | First research-integrity bug backlog; closed |
| [2026-09-29 13:06](archive/journeys/journey-2026-09-29-1306-✅已完成.md) | ✅ 已完成 | Acceptance/readiness evidence for the first backlog |
| [2026-09-29 13:51](archive/journeys/journey-2026-09-29-1351-✅已完成.md) | ✅ 已完成 | Follow-up backlog; all seven items closed |
| [2026-09-29 14:21](archive/journeys/journey-2026-09-29-1421-🧭路线图.md) | 🧭 路线图 | Optional open-source reuse/adoption roadmap |
| [2026-09-30 01:24](archive/journeys/journey-2026-09-30-0124-✅已完成.md) | ✅ 已完成 | Bug-mining round 2; all ten items closed |
| [2026-09-30 06:20](archive/journeys/journey-2026-09-30-0620-✅已完成.md) | ✅ 已完成 | Fix-pass and local verification evidence |
| [2026-10-06 17:50](archive/journeys/journey-2026-10-06-1750-🟡部分完成.md) | 🟡 部分完成 | Historical PIT engineering/data acceptance; remaining work belongs in the canonical ledger |

## Maintenance rules

- Exactly one active canonical ledger is allowed.
- New acceptance reports go to `acceptance/`; machine evidence goes to `evidence/`; architecture audits go to `audit/`.
- Closed or superseded journey records go to `archive/journeys/`; do not leave them in the root.
- Historical evidence is preserved rather than rewritten to make later results look cleaner.
- Strategy logic, research parameters and trading assumptions are not changed as part of report housekeeping.
