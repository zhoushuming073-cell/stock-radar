> **Status: 🟢 ACTIVE**
>
> **Role:** Current canonical project status and active backlog. Start here for all current work.
> **Index:** `reports/README.md`
>
# Stock Radar — Canonical Project Status

> **Canonical status file.** Read this file first when deciding what is complete, what is still open, and what should be implemented next.
>
> Historical dated journey/backlog files under `reports/` are retained as audit evidence. They are not the current source of truth once their items are closed here.
>
> Current review baseline: `main @ 5cc2d5c4f93a709b0f4ce9b5fb7a5000d8371568`
>  
> Consolidated: 2026-09-30

---

## Status rules

- **DONE** — implementation is present in the current source and corresponding regression coverage or acceptance evidence exists.
- **PARTIAL** — useful functionality exists, but the original larger goal is not fully complete.
- **OPEN** — current implementation still has a correctness, reliability, product, or research gap.
- **ARCHIVED** — historical evidence only; do not treat it as an active backlog.

When this file conflicts with an older dated journey document, this file is authoritative for current status.

---

# 1. Current platform summary

Stock Radar is currently a local research platform with:

- causal daily feature research and strict As-Of replay checks;
- strategy plugins with exact version identity in the main browser workflow;
- historical daily Scanner research with per-session candidate snapshots;
- Backtest, Timeline and Experiment execution;
- immutable completed Run evidence in SQLite;
- Scanner forward-outcome evaluation and candidate-level diagnostics;
- Research Export Bundles with CSV, Parquet, JSON and SHA-256 evidence;
- Train / Validation / frozen historical Test splits;
- Fresh OOS support once enough post-freeze sessions exist;
- shared Backtest / Scanner worker scheduling;
- a single local Web UI.

The platform is suitable for exploratory Train / Validation research subject to the limitations below. It is **not** a claim of unbiased PIT historical research or live-trading readiness.

---

# 2. Completed work

## 2.1 Causal research and research-store integrity — DONE

The earlier research-correctness work recorded in `reports/journey-2026-09-30-0651-active.md` and the first 2026-09-29 bug backlog is closed.

Completed:

- strict As-Of daily causal replay;
- removal of sample-end liquidity selection from historical daily eligibility;
- removal of current `tradable` / `exchange` state from historical daily decisions;
- causal daily Elasticity percentile and market breadth construction;
- Future Mutation regression tests;
- strict replay vs fast-engine comparison tests;
- atomic research-store staging and promotion;
- frozen dated Train / Validation / Test boundaries;
- missing full Scanner session detection;
- current `security_name` removed from historical strategy decisions;
- causal event-study tradability;
- persisted `market_feature_version` and legacy provenance warnings;
- shared Scanner / Backtest worker budget;
- Scanner experiment summaries separated when evaluation definitions differ.

Primary acceptance evidence:

- `reports/journey-2026-09-29-1306-completed.md`
- `reports/journey-2026-09-29-0629-completed.md` — CLOSED

## 2.2 Follow-up operations backlog — DONE

All seven items from `reports/journey-2026-09-29-1351-completed.md` are implemented in the current source:

- Scanner queued/running cancellation;
- first-class Fresh OOS support in Scanner and Backtest when the split exists;
- bounded research backup retention;
- severe partial-session feature coverage detection;
- oldest-eligible-first shared worker scheduling;
- historical/legacy Phase 2 report labeling;
- README worker-cap documentation reconciliation.

Status of the source backlog file: **CLOSED / ARCHIVED**.

## 2.3 Bug-mining round 2 — DONE

All ten items from `reports/journey-2026-09-30-0124-completed.md` are implemented in the current source:

- atomic multi-Run creation;
- exact strategy version preserved by Clone;
- canonical execution/evaluation settings restored by Clone;
- real RunManager walk-forward path repaired;
- version-aware browser/API state for the main workflow;
- dynamic Research Bundle Top-K export;
- authoritative RunStore schema provenance;
- mutable presentation fields excluded from immutable exported Run evidence;
- exact-version uninstall semantics;
- selected universe mode displayed correctly.

Status of the source backlog file: **CLOSED / ARCHIVED**.

The implementation summary is retained at:

- `reports/journey-2026-09-30-0620-completed.md`

That file records a local result of **262 tests passed** and a browser smoke check. GitHub currently has no CI workflow/check result attached to commit `5cc2d5c...`, so the 262-test statement is retained as local verification evidence rather than independent hosted-CI evidence.

## 2.4 Historical daily Scanner research — DONE

The historical daily Scanner requested by the research workflow exists.

For every signal session in a selected research split, Scanner:

- evaluates that day's causal cross-section;
- filters, scores, ranks and selects candidates;
- stores the signal date and candidate snapshot;
- stores diagnostics, probabilities and causal input features;
- computes forward labels only in the evaluation layer;
- allows the browser to select a date and inspect that day's candidates.

This is **historical daily Scanner research**.

It is not the same product as a one-click latest-session / "today's candidates" Scanner. That separate product item remains open below.

## 2.5 Research Export Bundle — DONE

The planned experiment evidence bundle is implemented.

Current bundle support includes:

- selected Backtest and Scanner Runs;
- per-Run metadata and metrics;
- full Scanner candidates in CSV and Parquet;
- Backtest equity, trades and events;
- Top-K comparison metrics;
- candidate overlap for compatible Scanner definitions;
- regime and risk summaries;
- provenance hashes;
- immutable evidence independent of Run rename/archive presentation state.

Documentation:

- `docs/research-export.md`

## 2.6 Strategy plugin infrastructure — DONE for current v1 scope

The current plugin architecture is operational for daily cross-sectional candidate strategies.

Implemented:

- Pluggy-backed strategy registry;
- manifest/config validation;
- required causal feature declarations;
- strategy ZIP import;
- versioned registrations;
- filter / score / select workflow;
- diagnostics/probabilities;
- exact-version identity in the main browser workflow.

This remains a candidate-strategy plugin model, not a general trading-engine plugin system.

---

# 3. Partially complete larger goals

## 3.1 Experiment Platform — PARTIAL

A useful Experiment layer exists:

- grid, ablation and walk-forward creation;
- multiple variants;
- queued execution;
- shared worker limits;
- persisted Run-level experiment metadata;
- browser experiment cards;
- variant status and summary metrics;
- Research Bundle export.

The larger "Experiment as a first-class entity" goal from `journey-2026-09-29-0426-archived.md` is not fully complete.

Still missing or incomplete:

- independent Experiment table/entity rather than primarily grouping Runs by metadata;
- experiment name and research question as durable first-class fields;
- explicit whole-experiment progress;
- whole-experiment cancellation/restart semantics;
- experiment-level notes;
- experiment-level immutable hash/manifest at creation time;
- richer variant matrix;
- direct Train vs Validation presentation;
- automatic report generation.

## 3.2 Point-in-Time historical research — PARTIAL / NOT FORMALLY READY

The repository has PIT-oriented contracts, security-master support, terminal-event handling and readiness checks.

However, repository code support is not the same as having a complete trustworthy PIT historical dataset.

Current research must continue to distinguish:

- **Current Snapshot** — operational, with explicit survivorship-bias risk;
- **Point-in-Time framework** — implemented;
- **formal unbiased PIT historical validation** — not established by the repository alone.

Do not mark PIT research "complete" only because the code path exists.

## 3.3 Fresh OOS — IMPLEMENTED, DATA-AVAILABILITY PENDING

Fresh OOS is a real Scanner/Backtest split in the current software.

The 2026-09-30 fix pass records that the then-current local research store still did not contain enough post-2026-09-28 sessions to expose a valid Fresh OOS signal/evaluation window.

Therefore:

- software support: **DONE**;
- currently available research interval at that recorded data snapshot: **NOT YET AVAILABLE**.

---

# 4. Current correctness / reliability backlog

These are the active bugs found after the 2026-09-30 fix pass. They supersede the old closed backlogs.

## CURRENT-P1-01 — Scanner outcome horizon can exceed the frozen split evaluation boundary — OPEN

Scanner evaluation currently permits `horizon_sessions` up to 60, while the frozen research contract reserves 10 forward sessions.

A custom Validation Scanner horizon above the reserved window can request labels beyond the stored Validation evaluation boundary and enter the frozen Test interval.

Required outcome:

- queue-time validation against the research contract;
- worker-time defensive validation;
- no Scanner label may consume sessions beyond its stored evaluation boundary;
- regression coverage for the maximum allowed horizon and rejection above it.

## CURRENT-P1-02 — Source Scanner provenance does not fully bind strategy implementation — OPEN

A Backtest created from a completed Scanner checks strategy ID/version, configuration, dataset, split and universe, but does not fully bind the Scanner's strategy implementation hash to the Backtest's recorded strategy implementation.

If a strategy file changes without a version bump after the Scanner completed, the Backtest can consume immutable old Scanner candidates while recording the newer strategy implementation as the current Run implementation.

Required outcome:

- preserve and validate the signal-producing Scanner implementation provenance;
- reject incompatible source Scanner / Backtest provenance or record signal-source provenance separately and explicitly;
- add a regression test for same ID/version with changed strategy code.

## CURRENT-P1-03 — Batch persistence is atomic, but batch research context capture is not — OPEN

The current fix validates all variants before one SQLite transaction, which prevents partial Run insertion.

However, variant preparation still resolves data snapshot, source watermark and other research context during per-variant preparation. A research database replacement during a large batch preparation can theoretically produce one Experiment containing Runs prepared against different research snapshots.

Required outcome:

- capture one immutable batch preparation context;
- all variants in the request must share it;
- revalidate the active research source before commit;
- source change during preparation must fail the complete batch with zero queued Runs.

## CURRENT-P2-01 — Exact strategy version is not yet a mandatory server contract on every route — OPEN

The browser now uses exact `strategy_id@version` identity in the main workflow.

Some server/legacy paths still accept a bare strategy ID and resolve a version implicitly.

Required outcome:

- new API paths should require exact version identity;
- any remaining bare-ID support must be explicitly isolated as legacy compatibility and tested;
- no automation/CLI path should silently upgrade to another installed version.

## CURRENT-P2-02 — Unified scheduler is invoked redundantly and repeatedly scans OS processes — OPEN

Backtest and Scanner launch wrappers both call the same unified dispatcher, while some callers invoke both wrappers consecutively.

Worker recovery also performs repeated process enumeration per queued Run.

Required outcome:

- one canonical dispatcher invocation per polling cycle;
- build one worker-process map per cycle instead of rescanning per Run;
- preserve oldest-eligible-first scheduling and restart recovery behavior.

## CURRENT-P2-03 — Some result surfaces still hide strategy version from the user — OPEN

The underlying Run identity is version-aware, but several human-facing lists still emphasize strategy name/ID without always showing the exact version.

Affected presentation includes parts of:

- Run History;
- Compare selection;
- Experiment cards;
- Research Export selection;
- Scanner Run selection.

Required outcome:

- every Run-selection surface should visibly show strategy version;
- users should be able to distinguish v1/v2 without opening the audit panel.

## CURRENT-P3-01 — Background refresh can clear important user notices — OPEN

The browser refresh loop clears the shared notice area after a successful refresh.

This can remove important Clone/provenance/warning messages shortly after they are shown.

Required outcome:

- connection state must be separate from user notices;
- background polling must not clear warnings/errors;
- transient success messages may expire independently.

## CURRENT-P3-02 — Fresh OOS availability is only loaded at initial page startup — OPEN

The split list is fetched when the page initializes.

If a research rebuild makes Fresh OOS available while the page remains open, normal background refresh does not add the new split option.

Required outcome:

- refresh split availability after relevant data/research updates or as part of a lightweight periodic refresh;
- no full browser reload should be required.

---

# 5. Product / UI backlog

These items are not research-integrity failures. They are product improvements and should remain separate from correctness bugs.

## PRODUCT-01 — Latest-session Daily Scanner — OPEN

The current Scanner is a historical research Scanner that processes each session inside Train / Validation / Test / Fresh OOS.

A separate daily-use workflow does not yet exist.

Desired product:

- run only the latest fully available signal session;
- show today's/latest candidates immediately;
- no forward labels are required at run time;
- retain exact strategy/version/data provenance;
- reuse the same causal filter/score/rank pipeline;
- clearly separate "Daily Scanner" from "Scanner Research".

## PRODUCT-02 — Small UI information-architecture cleanup — OPEN

The current Web UI is functional, but the next UI pass should remain small and low-risk.

Recommended scope already reviewed:

- reduce card-wall density;
- make Scanner/Backtest results the primary visual focus;
- collapse configuration after a Run;
- use tabs for secondary Trades/Activity/Audit detail;
- add a persistent research-context bar;
- make Run history more compact;
- consolidate duplicate CSS/design tokens;
- improve strategy-version visibility;
- improve notice/toast behavior.

Do not combine this with a frontend-framework rewrite.

## PRODUCT-03 — Scanner-centric Compare improvements — PARTIAL

Experiment summaries already expose Scanner metrics and Research Export can compare compatible evidence.

The dedicated Compare experience is still mainly Backtest-oriented.

Future Scanner comparison may include:

- Precision/Lift;
- Event Precision/Event Lift;
- MFE/MAE;
- falling-knife rate;
- censoring;
- regime stability;
- candidate overlap.

## PRODUCT-04 — Automatic research report generation — OPEN

Research Export creates a durable evidence package, but there is no finished first-class "generate research report" workflow from an Experiment/Bundle.

---

# 6. Research / data roadmap

These are future research capabilities, not current bugs.

## RESEARCH-01 — Historical daily premarket NASDAQ context — OPEN

Still a research/data-source task.

Goal: reconstruct historically available premarket market context without using information released after the intended decision timestamp.

## RESEARCH-02 — ES / NQ / YM causal market context — OPEN

Not integrated into the current strategy context.

Any future implementation must be host-owned and timestamp-causal, including roll logic and continuous-contract handling.

## RESEARCH-03 — Trusted PIT security-master / historical-universe data — OPEN

PIT software support exists, but high-confidence historical membership/delisting/corporate-action source coverage remains a separate data problem.

## RESEARCH-04 — Rolling ML / label maturity framework — OPEN

Future rolling models must train only on labels that were already mature at the training as-of timestamp.

Any scaler, imputer, feature selection, calibration and hyperparameter search must obey the same cutoff.

## RESEARCH-05 — Researcher-degrees-of-freedom controls — PARTIAL

The platform retains experiment variants and prevents experiment search directly on historical Test, which is useful.

Still desirable:

- durable pre-registered research question;
- saved search space before execution;
- stronger experiment-level audit trail;
- explicit Freeze → Fresh OOS workflow.

---

# 7. Open-source reuse roadmap status

`reports/journey-2026-09-29-1421-roadmap.md` remains a roadmap, not an implementation checklist that can be assumed complete.

Clearly adopted in the current repository:

- Pluggy strategy registry;
- psutil-assisted worker/process recovery.

Not evidenced as integrated into the current core Strategy Lab workflow:

- Huey;
- Label Studio;
- Optuna;
- exchange_calendars;
- Pandera;
- Hypothesis;
- mplfinance;
- QuantStats;
- Aim / MLflow;
- DVC.

Do not treat roadmap mentions as installed features.

---

# 8. Historical log map

Use the following classification when reading old files.

| File | Current meaning |
| --- | --- |
| `reports/journey-2026-09-30-0651-active.md` | **CURRENT CANONICAL STATUS** |
| `reports/journey-2026-09-29-0629-completed.md` | ARCHIVED — all 8 items closed |
| `reports/journey-2026-09-29-1306-completed.md` | ARCHIVED acceptance evidence for the first bug backlog |
| `reports/journey-2026-09-29-1351-completed.md` | ARCHIVED — all 7 items closed |
| `reports/journey-2026-09-30-0124-completed.md` | ARCHIVED — all 10 items closed |
| `reports/journey-2026-09-30-0620-completed.md` | ARCHIVED implementation/verification summary for the 17-item fix pass |
| `reports/journey-2026-09-29-0426-archived.md` | ARCHIVED mixed planning/history; surviving open goals are copied into this canonical file |
| `reports/journey-2026-09-29-1421-roadmap.md` | ROADMAP — optional adoption plan, mostly not integrated |
| `reports/phase2/*` | HISTORICAL pre-v3 research artifacts, not current Strategy Lab semantics |

---

# 9. Logging convention from now on

To prevent status from fragmenting again:

1. Every journey log uses `journey-YYYY-MM-DD-HHMM-status.md`.
2. `HHMM` uses the GitHub repository commit timestamp in UTC so historical filenames are deterministic.
3. Exactly one journey file may have status `active`. `reports/README.md` points to it.
4. When a new canonical status snapshot is published, create a new timestamped `active` journey and downgrade the previous active file to `archived` or `completed`, according to its role.
5. Closed bug backlogs and fix-pass records remain preserved as `completed`; they are not reused as task lists.
6. Mixed historical planning notes become `archived`; optional future adoption plans use `roadmap`.
7. New bug-mining findings, product work and research/data work are consolidated into the current active journey before a new standalone log is created.
8. `reports/phase2/` remains historical research evidence rather than journey status logs.
9. `docs/` contains contracts/specifications, not current task status.
10. Every journey file must carry a visible status banner at the top.

---

# 10. Current recommended order

For the next engineering pass:

1. `CURRENT-P1-01` — enforce Scanner horizon inside the frozen evaluation boundary.
2. `CURRENT-P1-02` — bind Source Scanner signal provenance to exact implementation evidence.
3. `CURRENT-P1-03` — make batch research-context preparation snapshot-consistent.
4. `CURRENT-P2-01` — finish server-side exact-version enforcement.
5. `CURRENT-P2-02` — simplify unified dispatcher/process discovery.
6. `CURRENT-P2-03` — expose exact strategy versions on all result selectors.
7. `CURRENT-P3-01` / `CURRENT-P3-02` — UI refresh/message cleanup.
8. Then implement `PRODUCT-01` Latest-session Daily Scanner.
9. Then perform the small UI information-architecture cleanup.
10. Continue the longer research/data roadmap separately.

This ordering keeps research correctness ahead of convenience features while avoiding another broad rewrite.
