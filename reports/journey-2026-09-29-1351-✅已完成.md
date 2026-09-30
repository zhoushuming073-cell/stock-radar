> **Status: ✅ COMPLETED**
>
> **Role:** Historical implementation/backlog evidence. The actionable work recorded here is closed. Do not use this file as the current task list.
> **Current status:** `reports/journey-2026-09-30-0651-active.md`
>
# Stock Radar Journey — Follow-up Backlog 2026-09-29

> Purpose: record the next set of issues found after commit `edb428c055dfc715429f33d23380da314b069d1e`.
>
> Scope: this file only contains newly identified follow-up work. It does not repeat the previously completed P0/P1 backlog in `journey-2026-09-29-0629-completed.md`.
>
> Audit baseline: `main @ edb428c055dfc715429f33d23380da314b069d1e`

---

## Priority summary

### P1 — should fix before larger Scanner/Experiment workloads

1. Scanner Runs are not cancellable
2. Fresh OOS exists in split logic but is not exposed as a runnable split
3. Research-store backups have no retention policy
4. Scanner coverage checks detect fully missing sessions, but not severely incomplete sessions

### P2 — operational / maintenance follow-up

5. Global worker scheduling can starve Scanner work behind Backtests
6. Some legacy reports/documentation still describe old split dates or old ETF-name filtering semantics
7. README worker-cap text is out of sync with the current default

---

# 1. P1 — Scanner Runs cannot be cancelled

## Problem

Backtest Runs support:

```text
queued
running
cancel_requested
cancelled
```

and the worker checks cancellation during execution.

Scanner Runs currently only use:

```text
queued
running
completed
failed
```

There is no Scanner-side cancellation state, cancellation request method, or Scanner worker polling for cancellation.

The generic `/api/lab/cancel` route calls `RunManager.cancel()`, which currently reads from the Backtest Run store path and does not provide equivalent Scanner semantics.

For short Runs this is tolerable, but it becomes a practical platform defect once users queue long Scanner grids or multi-strategy experiments.

## Required behavior

Scanner Runs should have the same lifecycle-quality as Backtest Runs.

Recommended lifecycle:

```text
queued
→ running
→ cancel_requested
→ cancelled
```

A queued Scanner should cancel immediately.

A running Scanner should stop at a safe session boundary.

## Acceptance criteria

- A queued Scanner Run can be cancelled.
- A running Scanner Run can receive a cancellation request.
- Scanner execution checks the cancellation flag between signal sessions.
- Cancelled Scanner Runs preserve already written progress/audit information but do not publish a completed immutable candidate snapshot.
- UI can cancel Scanner and Backtest Runs through an unambiguous Run-type-aware path.
- Add tests for queued Scanner cancellation and running Scanner cancellation.

---

# 2. P1 — Fresh OOS is defined but not runnable from Strategy Lab

## Problem

`resolve_split_windows()` now creates a `fresh_oos` interval when enough sessions exist after the frozen historical Test.

However, normal Strategy Lab queueing currently accepts only:

```text
train
validation
test
```

for Scanner, and standard Backtest UI/API flows also do not expose `fresh_oos` as a first-class selectable split.

This means the project can correctly identify newly arriving untouched data, but cannot yet use the normal experiment workflow to run that region.

## Required behavior

Fresh OOS should become a first-class research split once it exists.

It must remain clearly distinct from the already viewed historical Test.

Recommended semantics:

```text
Train       = fixed
Validation  = fixed
Historical Test = fixed and exploratory
Fresh OOS   = post-freeze newly arriving sessions
```

Do not automatically mix Fresh OOS into Train, Validation, or historical Test.

## Acceptance criteria

- Scanner can queue `fresh_oos` when the split exists.
- Backtest can queue `fresh_oos` when the split exists.
- UI exposes Fresh OOS only when enough post-freeze sessions are available.
- Metadata explicitly identifies `split=fresh_oos`.
- Research exports distinguish historical Test from Fresh OOS.
- Grid/ablation parameter search should not use Fresh OOS unless explicitly allowed by a future research policy; default behavior should keep it protected.
- Add tests showing historical split membership remains frozen while Fresh OOS grows.

---

# 3. P1 — Research-store backups have no retention policy

## Problem

Atomic promotion now creates a complete backup of the previous research DuckDB before replacing the active store.

This is good for safety, but every successful rebuild creates another full database under:

```text
data/research-backups/
```

There is currently no bounded retention or cleanup policy.

On a multi-GB research store, repeated rebuilds can silently consume tens or hundreds of GB.

## Required behavior

Keep rollback safety while bounding disk growth.

Recommended default:

```text
retain the latest 3 successful research-store backups
```

Optionally also retain backups referenced by an explicit manual pin/manifest if that feature is added later.

Cleanup should occur only after a new promotion succeeds.

## Acceptance criteria

- Successful promotion creates the new backup first.
- After promotion, retention removes only backups older than the configured limit.
- Never delete the active DB or the just-created backup.
- Failed builds do not trigger backup cleanup.
- Retention count is configurable.
- Add tests with multiple promotions and verify only the newest N backups remain.

---

# 4. P1 — Scanner coverage validation does not detect severely incomplete sessions

## Problem

The new Scanner coverage guard correctly fails when an expected signal date has zero feature rows.

However, it considers a session “observed” as soon as at least one feature row exists.

A corrupted or partial daily feature build could therefore contain, for example:

```text
normal day: 3,000+ eligible feature rows
damaged day: 100 rows
```

and still pass the current full-session presence check.

The atomic feature-store promotion substantially reduces this risk, but a direct data corruption, partial external update, or later incremental-update defect could still create a materially incomplete date.

## Required behavior

Add a per-session completeness sanity check in addition to binary session presence.

This should avoid hard-coding one absolute symbol count because the current-snapshot cohort and historical eligibility vary over time.

Possible robust approaches:

- compare each date's raw feature-row count to nearby sessions;
- require a minimum ratio versus a rolling recent median;
- compare observed symbol coverage to a build-manifest/session-count table created during feature publication.

The preferred design is a published per-session coverage manifest generated by the research build and validated by Scanner.

## Acceptance criteria

- A full missing session still fails.
- A severely truncated session also fails or is prominently marked invalid.
- Legitimate historical variation in active/eligible symbols does not create false failures.
- Coverage diagnostics report date and observed/expected counts.
- Add a regression test where one date retains only a small fraction of its rows.

---

# 5. P2 — Global worker scheduling may starve Scanner work

## Problem

Scanner and Backtest now share a global worker budget, which fixes oversubscription.

However, the dispatcher calls:

```text
launch_queued()
launch_queued_scanners()
```

in that order.

With a single-worker default and a continuous Backtest queue, Backtests can repeatedly claim the available slot before Scanner queueing is considered.

This can create starvation or unexpectedly long Scanner delays.

## Required behavior

Use a fair global scheduler instead of two independently invoked launch loops.

Possible policy:

```text
oldest queued Run first across both Run types
```

or a simple alternating/fair-share scheduler.

The exact policy should be deterministic and auditable.

## Acceptance criteria

- A queued Scanner cannot wait indefinitely behind a continuously replenished Backtest queue.
- Scanner and Backtest share one ordering/scheduling policy.
- Manager restart preserves fair scheduling semantics.
- Add a mixed-queue test with `max_workers=1`.

---

# 6. P2 — Legacy research reports still describe outdated semantics

## Problem

Some older files under `reports/phase2/` still document:

- old Train/Validation/Test date boundaries;
- older current-name ETF/ETN exclusion behavior;
- earlier cohort definitions.

These files are historically valid artifacts, but their wording can be mistaken for current v3 research semantics by humans or coding agents.

This is a documentation provenance problem rather than a calculation bug.

## Required behavior

Do not rewrite historical evidence as if it had been produced under v3.

Instead add an explicit legacy banner to stale reports, for example:

```text
Historical artifact — generated under pre-v3 research semantics.
Do not use these dates/filters as the current Strategy Lab contract.
See current research split/config documentation.
```

Where appropriate, link to the current split/version documentation.

## Acceptance criteria

- Clearly stale reports are marked as historical/pre-v3.
- Current docs remain the canonical source of split and filtering semantics.
- Do not silently alter old numeric results or imply they were regenerated.

---

# 7. P2 — README worker-cap description is stale

## Problem

The implementation default is currently:

```text
RunManager(..., max_workers=1)
```

after a real concurrent workload exhausted memory.

README text still refers to a two-process local worker cap.

## Required behavior

Update documentation to match the current runtime default while retaining the fact that the code supports an explicitly configured higher cap.

## Acceptance criteria

- README states the current default correctly.
- Documentation distinguishes default from allowed maximum.
- No claim that two workers are always active by default.

---

# Suggested implementation order

```text
1. Scanner cancellation lifecycle
2. Fresh OOS as a first-class runnable split
3. Research backup retention
4. Per-session completeness validation
5. Fair global worker scheduling
6. Mark legacy reports as pre-v3 historical artifacts
7. Update worker-cap documentation
```

# Definition of done

This follow-up backlog is complete when:

- new targeted regression tests pass;
- the full test suite passes;
- a real queued Scanner can be cancelled safely;
- Fresh OOS can be queued without changing frozen historical splits;
- repeated feature-store promotions do not grow backups without bound;
- Scanner rejects a deliberately truncated feature session;
- mixed Scanner/Backtest queues show deterministic fair progress;
- documentation clearly separates current v3 semantics from legacy research artifacts.
