> **Status: ✅ COMPLETED**
>
> **Role:** Historical implementation/backlog evidence. The actionable work recorded here is closed. Do not use this file as the current task list.
> **Current status:** `reports/journey-2026-09-30-0651-active.md`
>
# Stock Radar Journey — Bug Backlog 2026-09-29

> Purpose: translate the latest bug-mining findings into implementation-oriented engineering language for Codex.
>
> Scope: this log only records newly identified defects and acceptance criteria. It does **not** duplicate the previously documented PIT/survivorship-bias backlog or the earlier As-Of causal-replay work.
>
> Audit baseline: `main @ dd7364d9d9736fb1ae264fca6f98e5ba01168c45`

---

## Priority order

### P0 — must fix before larger experiments

1. Atomic research-store rebuild / promotion
2. Immutable research split boundaries
3. Missing-session fail-fast validation

### P1 — fix before relying on large experiment comparisons

4. Remove current `security_name` from historical decision logic
5. Migrate `event_study.py` off current asset-status metadata
6. Persist and validate `market_feature_version` for Backtest Runs
7. Enforce one global worker-concurrency budget
8. Prevent aggregation across incompatible Scanner evaluation definitions

---

# 1. P0 — Research-store rebuild is not atomic

## Problem

The current research-table build path can delete or replace the active v3 feature version before a full rebuild has completed.

A partial build, process interruption, exception, test run with `--max-symbols`, or host shutdown can therefore leave the active research database containing an incomplete `FEATURE_VERSION` while Scanner/Backtest continue to treat that version as valid.

This creates a partial-publication failure mode.

## Required behavior

Research rebuilds must follow a staging-and-promote workflow:

```text
build into staging
→ validate completeness and invariants
→ atomically promote staging as active
→ retain previous complete version until promotion succeeds
```

The active feature version must never refer to a partially built dataset.

`--max-symbols` must never overwrite or truncate the production feature version.

## Acceptance criteria

- Interrupting a rebuild midway leaves the previously active feature store fully usable.
- A failed rebuild cannot change the active feature version.
- A partial/test build uses a distinct staging or temporary version/DB.
- Promotion occurs only after completeness validation passes.
- The previous active version remains recoverable after promotion.
- Add a regression test that simulates an interrupted/partial build and proves the active store remains unchanged.

---

# 2. P0 — Train / Validation / Test boundaries drift when new market data is appended

## Problem

Current split boundaries are derived from fractions of the current SPY session count.

As new daily bars are appended, the historical boundaries move.

This allows dates that were previously Test to later migrate into Validation or Train.

That invalidates the intended meaning of a sealed/previously viewed holdout and creates researcher-level contamination even if all feature calculations are causal.

## Required behavior

Research splits must become immutable dated boundaries once established.

Recommended semantics:

```text
Train: fixed historical date interval
Validation: fixed historical date interval
Viewed historical Test: fixed historical date interval
Fresh OOS: only newly arriving dates after the freeze date
```

Appending market data must not reclassify historical sessions across these sets.

## Acceptance criteria

- Adding new daily bars does not alter existing Train/Validation/Test membership.
- Split boundaries are persisted in config or a versioned split manifest.
- Historical Runs continue to resolve to the same dated split after later data updates.
- Fresh data is assigned only to a new OOS region or explicitly versioned future split.
- Add a regression test that appends later sessions and asserts all prior split memberships are unchanged.

---

# 3. P0 — Scanner silently skips missing feature sessions

## Problem

The Scanner currently tolerates a signal date with no feature rows by catching the lookup failure and continuing.

A missing full session can therefore disappear from the experiment without failing the Run.

This is especially dangerous when combined with an incomplete research-store rebuild because the Run may complete with fewer evaluated days than expected while still returning normal-looking metrics.

## Required behavior

Scanner must validate expected signal-session coverage before or during execution.

For formal research Runs, missing expected sessions must be explicit and non-silent.

Preferred behavior:

- fail the Run when an expected signal session has zero causal-feature coverage; or
- only allow continuation under an explicitly configured degraded-data mode, with prominent audit fields.

## Acceptance criteria

- A missing expected signal session cannot silently disappear.
- Run metadata/metrics record expected session count, observed session count, and missing dates.
- Default research mode fails on missing full sessions.
- A regression test removes one complete signal date and confirms the Run fails with a clear error.
- A separate test confirms a legitimate non-trading date is not treated as missing.

---

# 4. P1 — Current `security_name` leaks present-day metadata into historical strategy logic

## Problem

In current-snapshot mode, historical rows receive `security_name` from the current `assets` table.

`security_name` is then exposed as a base StrategyContext field and Strategy 2 uses it for the ETF/ETN name-based exclusion heuristic.

A future rename can therefore affect a historical decision.

This is a residual metadata look-ahead channel independent of PIT universe membership.

## Required behavior

Until historical security-name/type metadata is available, current `security_name` should be treated as display-only metadata.

It must not affect historical candidate eligibility or scoring.

For Strategy 2, the name-based ETF/ETN exclusion should be removed from the formal historical decision path or explicitly disabled in current-snapshot causal research.

Historical security classification should later come from dated/PIT security metadata, not current names.

## Acceptance criteria

- Mutating the current asset name cannot change a historical candidate set, score, or rank.
- Add a future-metadata mutation test for `security_name`.
- StrategyContext may continue to display the name, but historical strategy logic must not branch on current names.
- PIT mode may use dated security metadata when available.

---

# 5. P1 — `event_study.py` still uses current `tradable` and `exchange` metadata

## Problem

The v3 Scanner/Backtest path removed current `tradable/exchange` from historical eligibility, but the factor event-study path still joins current asset metadata and applies it to historical rows.

This means factor-study outputs are not on the same causal eligibility definition as the v3 research store.

## Required behavior

Event-study eligibility should use the historical causal feature-store gate, especially `tradability_pass`.

Current mutable asset fields must not be used as historical date-level filters.

If exchange/security-type constraints cannot be made historical, document them as unavailable rather than projecting current values backward.

## Acceptance criteria

- Historical factor-study sample membership is invariant to mutations of current `assets.tradable` and `assets.exchange`.
- Train/Validation event-study rows use the same causal tradability definition as the v3 feature store.
- Add regression tests covering current asset-status mutation.
- Existing limitation text is updated so event-study provenance matches actual behavior.

---

# 6. P1 — Backtest Compare compatibility check lacks persisted `market_feature_version`

## Problem

The Compare UI checks `metadata.market_feature_version`, but Backtest Run metadata does not currently persist that field through the same provenance chain used by Scanner.

As a result, two Backtest Runs may both expose `undefined` and appear compatible even if their market-context feature semantics differ.

## Required behavior

`market_feature_version` must be part of Backtest Run provenance.

It should flow through:

```text
dataset definition
→ resolved config
→ Run metadata
→ worker source/version validation
→ Compare compatibility signature
```

## Acceptance criteria

- Every new Backtest Run records `market_feature_version`.
- Worker execution rejects a queued Run if the expected market feature version changed before execution.
- Compare warns when selected Runs use different market feature versions.
- Add tests for equal and unequal market feature versions.

---

# 7. P1 — Scanner and Backtest concurrency limits are independent

## Problem

The manager applies the worker cap separately to Backtest and Scanner launch paths.

With a configured cap of 2, the system can therefore run approximately:

```text
2 Backtest workers + 2 Scanner workers
```

at the same time.

This violates the documented global worker limit and can cause avoidable CPU, memory, DuckDB read, and SQLite WAL pressure during large experiments.

## Required behavior

Use one global concurrency budget across all local research worker types.

Conceptually:

```text
active_backtest
+ active_scanner
<= max_workers
```

Queued work from both classes should share the same scheduler budget.

## Acceptance criteria

- With `max_workers=2`, no more than two total Scanner+Backtest worker processes run concurrently.
- Browser refresh / manager restart still reconstructs the correct active count.
- Add a regression test with mixed queued Scanner and Backtest Runs.
- Documentation and implementation must agree on whether the cap is global.

---

# 8. P1 — Experiment summaries can aggregate incompatible Scanner outcomes

## Problem

Scanner experiment summaries aggregate Event Precision/Lift primarily by a common Top-K.

However, grid experiments may vary evaluation semantics such as:

- `horizon_sessions`
- `primary_target`
- `primary_adverse_target`
- `success_rule`
- `label_version`

Precision values from different outcome definitions are not directly comparable and must not be averaged into one headline mean/median.

## Required behavior

Define an explicit evaluation signature, for example:

```text
(
  label_version,
  horizon_sessions,
  success_rule,
  primary_target,
  primary_adverse_target,
  top_k,
  event_cooldown_sessions
)
```

Only Runs with compatible evaluation signatures may be aggregated into one summary statistic.

If signatures differ, the experiment UI/API must separate them into distinct groups or refuse to compute a single aggregate.

## Acceptance criteria

- Incompatible outcome definitions never produce one combined mean/median Precision.
- Experiment summary exposes the evaluation signature used for each group.
- A grid over `horizon_sessions` or `success_rule` produces separate comparison groups.
- Add regression tests for mixed-compatible and incompatible Scanner variants.

---

# Secondary validation note — v3 threshold semantics

The fixed Strategy 2 thresholds such as the historical Elasticity cutoff were originally described using older Train-distribution semantics.

After v3 changed universe coverage and same-date cross-sectional normalization, those old percentile descriptions may no longer be numerically true.

This is not necessarily a code defect if the strategy intentionally freezes those constants.

However, reports and comments should distinguish:

```text
frozen historical threshold
```

from:

```text
current v3 Train percentile
```

Do not silently relabel an old constant as a v3 percentile without recalculating the v3 Train distribution.

---

# Suggested implementation order

```text
1. Atomic staging / promotion for research rebuilds
2. Freeze dated Train / Validation / historical-Test boundaries
3. Add expected-session coverage validation
4. Remove current security_name from historical strategy decisions
5. Update event_study.py to causal tradability
6. Add Backtest market_feature_version provenance
7. Unify Scanner + Backtest worker scheduling
8. Group Experiment summaries by evaluation signature
9. Re-run full test suite and targeted causal-mutation tests
10. Re-run one real Train and one real Validation smoke/acceptance experiment
```

# Definition of done

This backlog is complete only when:

- all new targeted regression tests pass;
- the full test suite passes;
- real local Scanner and Backtest smoke Runs complete on the active v3 research store;
- no fix reintroduces future-conditioned historical eligibility;
- existing completed Runs remain immutable;
- new provenance fields do not reinterpret old Runs silently.
