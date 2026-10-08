# Reports Log Index

> **Purpose:** navigation and document governance only. This file is not a journey log and does not create a second backlog.

## Current source of truth

- **📌 当前总账:** [Canonical status / active backlog](journey-2026-09-30-0651-📌当前总账.md) — the only active project ledger.
- **Current research-direction snapshot:** [2026-10-08 · Quant + Vision Fusion](current/quant-vision-fusion-direction-2026-10-08.md).
- **Earlier development-stage snapshot:** [2026-10-06 · Research + local LEAN integration](current/development-status-2026-10-06.md) — retained for engineering history.
- When a dated report conflicts with the canonical ledger, the canonical ledger wins for current status. Dated reports remain audit evidence.

## Directory layout

| Path | Role |
| --- | --- |
| `acceptance/` | Dated acceptance reports and bounded engineering/research conclusions |
| `evidence/` | Machine-readable evidence, scorecards and supporting derived artifacts |
| `audit/` | Point-in-time architecture/audit records |
| `archive/journeys/` | Closed, partial or roadmap journey history; not an active backlog |
| `archive/reports/` | Superseded non-journey status/report snapshots kept for audit history |
| `archive/plans/` | Completed or superseded operational plans kept for audit history |
| `personal-research/` | Owner-authored research reports and preserved research conclusions |
| `phase2/` | Historical pre-v3 research artifacts and datasets |
| `current/` | Current stage snapshots that explain the active platform state |
| `docs/` (repository root) | Contracts and specifications; intentionally outside `reports/` |

The `reports/` root is intentionally kept small: this index plus the canonical ledger. Dated acceptance/readiness/finalization reports belong under `acceptance/`; superseded non-journey reports and completed operational plans belong under `archive/`.

## Quant + Vision Fusion research direction · 2026-10-08

[Active plan](../docs/QUANT_VISION_FUSION_RESEARCH_PLAN.md): the current research path is **Quant high-recall candidate generation → Human Observe/Entry labels → Vision M1 → Quant+Vision+Human transition → frozen Quant+Vision**. The random blind Single/Pair Pilot remains valid P0/P1 infrastructure evidence but is no longer the primary human-label dataset path; its formal human Ground Truth remains0. Do not force completion of the old50 Single +25 Pair task. [Direction record](current/quant-vision-fusion-direction-2026-10-08.md), [historical P0/P1 acceptance](acceptance/vision-p0-p1-pilot-acceptance-2026-10-08.md).

## Research Infrastructure v1 · 2026-10-08

[Frozen infrastructure / 47-answer finalization](acceptance/research-infrastructure-v1-finalization-2026-10-08.md): Shape READY, General PIT Tier 1 deep/audit, expansion CLOSED, maintenance ACTIVE, strategy research READY TO RESUME. 595 native-inclusive tests PASS. Combined ready 83.8733%; supported safe candles 5,407,961; Fresh supported windows 34,491 /33,745 /32,979 /30,462. Formal QC/Fresh strategy evaluation NOT_RUN. [API](../docs/RESEARCH_INFRASTRUCTURE_V1.md), [asset inventory](evidence/database-asset-inventory-2026-10-08.json), [cleanup receipt](evidence/database-cleanup-results-2026-10-08.json).

## Earlier Shape core acceptance · 2026-10-08 (historical snapshot)

[22-answer Shape readiness](acceptance/shape-research-data-readiness-2026-10-08.md): **SHAPE_RESEARCH_READY**, General PIT still Tier1.83.3562% technically safe observed candles; default confirmed/probable5,372,282 /77.5332%;126-session Train/Validation/Test2,107,260 /429,953 /517,162; Fresh OOS0.573 native-inclusive tests passed. [Machine evidence](evidence/shape-research-scorecard-2026-10-08.json), [API and source/cutoff contract](../docs/SHAPE_RESEARCH_DATA_LAYER.md). Stop active vendor-grade expansion, resume local shape/factor research and visual data preparation. Missingness of disappeared IDs and previously viewed Test remain explicit limits; strict production/formal gates and source tables untouched.

## Preserved General PIT database · 2026-10-08

[25-answer database acceptance](acceptance/pit-database-construction-acceptance-2026-10-08.md) supersedes the earlier P0-only/QC work order for this database branch. The target is a shared historical data foundation for future strategies.88,340 episodes,9,600,753 daily observation rows,906,514 accepted raw rows; old BBBY recovered419 bars/features. Overall **Tier1 Exploratory PIT / PARTIAL**, not Tier2 or maintenance.544 Native-inclusive tests passed; original root/frozen artifacts remain unchanged. [Scorecard](evidence/pit-database-scorecard-2026-10-08.json), [integration evidence](evidence/pit-database-integration-2026-10-08.json), [API contract](../docs/PIT_HISTORICAL_DATABASE.md). QC remains bounded smoke evidence only; no further reference/market export is planned.

## PIT acceptance chain · 2026-10-07

1. [Initial local PIT reconstruction](acceptance/pit-acceptance-2026-10-07.md) — architecture, pinned data and explicit limitations.
2. [Identity / retired-price trust continuation](acceptance/pit-data-trust-acceptance-2026-10-07.md) — reviewed identities, events and real OHLCV enrichment.
3. [Final execution-gate engineering](acceptance/pit-final-acceptance-2026-10-07.md) — frozen Run closure, native actions and formal blockers.
4. [Data clearance](acceptance/pit-clearance-acceptance-2026-10-07.md) — IREN continuity and full source probes; Formal PIT remains blocked.
5. [Bulk-source benchmark / trust ceiling](acceptance/pit-source-breakthrough-acceptance-2026-10-07.md) — large candidate coverage, no false formal admission.
6. [Research-Grade PIT](acceptance/pit-research-grade-acceptance-2026-10-07.md) — **PARTIAL** research-grade evidence; real Research-Grade Native LEAN remains blocked.
7. [Final research decision audit](acceptance/pit-research-final-acceptance-2026-10-07.md) — **PARTIAL / BLOCKED**; identity-safe Core competitors 29–72/day, actual-candidate gates, Top3 and missingness stress, 468 passing tests. [Derived evidence](evidence/pit-research-final-evidence-2026-10-07.json) and [focused P0 queue](evidence/pit-research-final-priority-2026-10-07.json).
8. [QuantConnect Free Cloud readiness](acceptance/qc-cloud-validation-readiness-2026-10-07.md) and [2026-10-08 actual Cloud smoke](acceptance/qc-cloud-smoke-validation-2026-10-08.md) — both complete Cloud smoke receipts imported and parser-verified PASS; first Layer1 pilot engine Completed but receipt unverified; further batches/reference exports HOLD due to actual Terms2.6 warning, Layer2–3 NOT_RUN and PIT BLOCKED. 470 date-project quota checks and507 native-inclusive tests passed. [Web instructions](../docs/QUANTCONNECT_FREE_VALIDATION.md).

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
- Closed or superseded journey records go to `archive/journeys/`; superseded non-journey reports go to `archive/reports/`; completed operational plans go to `archive/plans/`. Do not leave dated reports in the root.
- Historical evidence is preserved rather than rewritten to make later results look cleaner.
- Strategy logic, research parameters and trading assumptions are not changed as part of report housekeeping.