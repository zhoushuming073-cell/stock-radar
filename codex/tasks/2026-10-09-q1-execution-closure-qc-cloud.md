# Codex Work Order — Close Q1 Execution Dependencies, Re-run Frozen Local LEAN, Then QC Cloud

> Date: 2026-10-09  
> Status: **ACTIVE USER-AUTHORIZED FOLLOW-UP**  
> Parent implementation: Draft PR [#13](https://github.com/zhoushuming073-cell/stock-radar/pull/13), branch `feature/q1-q2-daily-lean-20261009`  
> Research family: **A. Quant-only**  
> Scope: resolve the three Q1 historical execution-data dependencies under the unchanged frozen study, re-run the exact local Q1 LEAN experiments, re-verify Q2 and Daily Scanner, then proceed to bounded compliant QuantConnect Cloud validation only if all mandatory local gates pass.

## 0. Current checkpoint — do not redo completed work

Read first:
- `AGENTS.md`
- `docs/RESEARCH_MASTER_GUIDE.md`
- `reports/journey-2026-09-30-0651-📌当前总账.md`
- `codex/tasks/ACTIVE.md`
- `reports/acceptance/q1-q2-quant-infrastructure-backtest-2026-10-09.md` on PR #13
- `reports/evidence/q1-q2-quant-infrastructure-backtest-2026-10-09.json` on PR #13
- `docs/Q1_Q2_LEAN_METHODOLOGY.md`
- `docs/Q1_Q2_QC_CLOUD.md`
- `docs/DAILY_QUANT_SCANNER.md`

Verified checkpoint from Draft PR #13:
- head: `77424fc5afb69098ef8eabd1931a28e3bdf86f6e`;
- Q1 exact parity completed;
- Q2 v1.1 hardened;
- Daily Q1/Q2/overlap Scanner implemented and browser-tested;
- 756 tests passed, 0 failed/skipped, Native LEAN executed;
- 5,207 protected files unchanged;
- Q2 local Native LEAN:
  - Train +1.3394%, maxDD -5.5185%, 14 trades;
  - Validation -2.5963%, maxDD -7.7590%, 27 trades;
- Q1 Train/Validation are **NOT_RUN_DATA_BLOCKED**, not zero-return runs;
- QC Cloud is BLOCKED/NOT_RUN because the mandatory local Q1 gate failed;
- PR #13 remains Draft and unmerged;
- PR #10 remains historical Draft provenance.

Do **not** rebuild Q1/Q2 from scratch. Do **not** change selector logic, thresholds, dates, Top-K, fees, slippage or holding rule to improve results.

## 1. Continue from PR #13 safely

1. Synchronize latest GitHub main.
2. Inspect PR #13 head and local branch.
3. If PR #13 has not changed since the checkpoint, continue on `feature/q1-q2-daily-lean-20261009`.
4. If it has changed, inspect every delta first and preserve the accepted freeze.
5. Do not force-reset local private artifacts.
6. Confirm the frozen study receipt and selector kernel before doing any data work:
   - final pre-strategy receipt: `7a175ee6fe9b5815207e5d1a964213cf005a11b4cbd4b16e27856f3f46a96efd`;
   - selector kernel: `4e5d9f15e7002977a74d67d1637c24a2da28c0cf11414696dece2090485962a8`.
7. If either selector/config/date/cost contract has drifted, stop and report instead of silently creating a new experiment.

## 2. Identify the exact three Q1 execution blockers locally

The public report intentionally omits detailed security IDs. Recover the exact private blocker records from the local gate diagnostics / ignored artifacts.

Expected blocker classes:

### Train
- one candidate with `missing_10session_fill_prices`, total 10 required bars missing;
- one candidate with `unsafe_identity_or_fill_prices`.

### Validation
- one candidate with `missing_10session_fill_prices`, total 6 required bars missing.

For each blocker, create a **private local dependency worksheet** containing:
- internal security ID;
- ticker history / alias if known;
- decision date;
- intended T+1 entry session;
- all required holding/exit sessions;
- which exact bar(s) are missing or unsafe;
- source currently used;
- adjustment basis;
- identity / corporate-action risk;
- why the existing gate refused execution.

Do not commit private IDs, raw bars or mappings to GitHub. Public evidence may contain only aggregate counts and source categories.

## 3. Resolve blockers with trusted evidence only

The objective is **not “make Q1 run at any cost.”** The objective is to determine whether the exact frozen signals can be executed with defensible historical evidence.

Follow the repository’s existing trust/provenance policy. Prefer already accepted authoritative/independent sources and existing ingestion/review mechanisms.

For every missing/unsafe dependency, require all of:

1. **Identity continuity**
   - establish that the historical symbol/security corresponds to the intended issuer/security for the exact interval;
   - handle rename/acquisition/delisting/split boundaries explicitly;
   - do not join by ticker string alone.

2. **Price basis**
   - establish raw vs split-adjusted basis;
   - identify corporate-action transformations;
   - ensure entry/holding/exit bars are on one internally consistent basis;
   - do not mix adjusted and raw units silently.

3. **Required sessions**
   - supply the exact T+1 entry and all possible holding/exit daily bars needed by the frozen 10-session execution contract;
   - no fill-forward substitution for a missing tradable session;
   - a halt/no-trade day must remain a halt/no-trade fact, not a fabricated bar.

4. **Provenance**
   - source, retrieval date, immutable/local hash, transformation logic and acceptance reason;
   - preserve original evidence bytes locally where policy permits;
   - add accepted supplemental data through the existing versioned evidence layer rather than mutating frozen Research Infrastructure v1 in place.

5. **Corporate actions / terminal events**
   - if a security disappears, merges, liquidates or changes entitlement during a possible holding window, resolve the event sufficiently for the frozen execution contract;
   - if actual exit economics cannot be established, keep the method BLOCKED.

### Forbidden shortcuts

Do not:
- delete the blocked candidate;
- replace it with rank #11;
- use a current-universe historical fallback;
- substitute a nearby ticker;
- invent a close/open;
- use future knowledge to exclude the position;
- weaken the identity/price gate;
- alter Q1 score or rank;
- switch the experiment date range;
- use Q2 results to modify Q1;
- mutate the frozen database merely to satisfy the test.

If one blocker cannot be resolved with trusted evidence, document it and stop Q1 execution as BLOCKED.

## 4. Data acceptance tests before re-running Q1

For each resolved dependency add targeted tests / audit checks:

- exact security/date mapping;
- expected adjustment basis;
- no split-basis discontinuity across required window;
- all required tradable sessions present;
- no future sessions influence T selection;
- source provenance hash binds to the accepted supplemental evidence;
- existing frozen infrastructure hashes remain unchanged;
- private supplemental layer is read-only during execution;
- Q1 signal/rank hashes are identical to the prior frozen study.

Re-run the Q1 preflight. It must go from:
- `NOT_RUN_DATA_BLOCKED`
to
- `READY_FOR_NATIVE`

without any change in selected signals.

Record before/after blocker counts.

## 5. Re-run the exact frozen Q1 local Native LEAN study

Only after Q1 preflight passes, execute the same registered contract:

- selector: Q1 frozen `fuzzy-shape-v1`;
- same bounded Train interval;
- same bounded Validation interval;
- same eligible universe contract;
- Qualified Top10;
- decision after T close;
- entry T+1 tradable open proxy;
- max 10 positions;
- equal available cash allocation across remaining slots;
- no same-security overlap;
- no lower-rank refill;
- tenth holding-session close exit;
- no TP/SL;
- same 10 bps slippage;
- same existing illustrative/unconfirmed fee model.

Run order:
1. Q1 Train;
2. reproducibility repeat of Q1 Train;
3. Q1 Validation.

The second Train invocation must reproduce:
- signal hash;
- execution-data hash;
- daily journal;
- fills;
- trades;
- completed holdings;
- headline metrics.

Do not publish the repeat as an additional strategy result.

## 6. Q1 local acceptance metrics

Report for Train and Validation:
- Native run ID;
- selected signals;
- fills;
- closed trades;
- max simultaneous positions;
- net/gross return;
- max drawdown;
- fees;
- turnover;
- mean/median trade return;
- win rate;
- worst trade;
- average holding;
- SPY benchmark;
- MFE/MAE diagnostics;
- Precision/Lift diagnostics already defined by the frozen study;
- cash/fill reconciliation error;
- all-holds-ten-sessions status;
- data-source/proxy limitations.

Do not claim alpha from these bounded short intervals.

If Q1 performs poorly, **do not tune it**. A poor result is an accepted research result.

## 7. Re-verify Q2 without changing Q2

Q2 is frozen for this follow-up.

Do not rerun parameter search.

At minimum:
- verify Q2 selector/config hash unchanged;
- verify prior Q2 Train/Validation Native artifacts remain reproducible / intact;
- if the execution supplement touches any Q2 dependency, re-run only the necessary parity/reconciliation checks;
- otherwise do not create fresh Q2 optimization runs.

Existing exploratory Q2 results remain:
- Train +1.3394%, maxDD -5.5185%, 14 trades;
- Validation -2.5963%, maxDD -7.7590%, 27 trades.

## 8. Re-verify Daily Scanner product

The Daily Scanner is already implemented.

Do a regression-only check:
- current latest completed session resolves correctly;
- Q1/Q2/all tabs work;
- Q1/Q2/overlap counts load;
- browser shows freshness/as-of;
- no broker action;
- deterministic same-input snapshot hash;
- daily market updater still does not fail merely because scanner fails.

Do not redesign the UI in this task unless a blocker prevents use.

## 9. Full local release gate

Before any QC Cloud work, all must pass:

- three Q1 execution dependencies resolved with trusted evidence;
- Q1 preflight READY;
- Q1 Train Native PASS;
- Q1 Train reproducibility PASS;
- Q1 Validation Native PASS;
- Q2 frozen integrity PASS;
- Daily Scanner regression PASS;
- targeted dependency tests PASS;
- full pytest PASS;
- Native LEAN opt-in actually executed;
- protected-file audit PASS;
- no selector/config/date/cost drift;
- no future leakage;
- updated acceptance/evidence written.

If any mandatory local gate fails, QC Cloud remains NOT_RUN.

## 10. QuantConnect Cloud — only after full local PASS

Before touching Cloud:
- re-read `docs/Q1_Q2_QC_CLOUD.md`;
- inspect the current QC UI/account warnings and current platform constraints;
- retain the existing Terms/export hold;
- do not use paid resources without separate authorization.

### Preferred Mode A

Run frozen Q1 and Q2 selector logic on QC-hosted data and QC LEAN.

Use separate projects:
- `SR-Q1-Fuzzy-Quant-v1`
- `SR-Q2-Channel-Quant-v1`

Preserve:
- same causal decision semantics;
- same ranking/gates;
- Top10;
- T+1 execution;
- max10 positions;
- equal cash allocation;
- 10-session hold;
- same stated fee/slippage assumptions where QC supports them.

Do not manually approximate selectors.

### Mode B fallback

If free-tier/universe/history constraints prevent QC-native selection, use the frozen local signals only for Cloud execution validation.

If Mode B is used, state clearly:

> QC validated execution/accounting only; selection remained local.

### Cloud forbidden actions

Do not:
- export QC raw OHLCV;
- reconstruct QC raw data through logs/results;
- use Object Store as an export workaround;
- bypass Terms warnings with encoding/chunking/screenshots;
- purchase API/compute;
- retune Q1/Q2 after seeing Cloud results.

### Cloud evidence

For each completed Q1/Q2 Cloud run record:
- Mode A/B;
- project ID;
- backtest ID;
- source/config hashes;
- dates;
- completion status;
- standard performance metrics;
- standard permitted order/trade summaries;
- warnings;
- comparison to local result where legitimately comparable.

Differences between local and Cloud are research evidence. Diagnose universe/data/identity/corporate-action/fill differences before changing code.

## 11. PR #13 release decision

After the follow-up:

### If all local gates pass and Cloud completes
- update PR #13 acceptance/evidence/docs;
- remove Draft status only after final review;
- merge PR #13 if tests/evidence/protection checks remain PASS;
- after PR #13 merges, close Draft PR #10 as superseded with provenance link;
- synchronize local main;
- update canonical ledger and `codex/tasks/ACTIVE.md` to completed/paused state.

### If all local gates pass but Cloud is externally BLOCKED
It is acceptable to:
- merge PR #13 if local Q1/Q2 + Daily Scanner engineering is complete and trustworthy;
- mark Cloud explicitly BLOCKED/PENDING;
- keep the platform restriction as a separate external-validation item.

### If Q1 cannot be resolved
- keep PR #13 Draft;
- do not merge;
- leave QC Cloud NOT_RUN;
- publish a truthful blocker report;
- do not weaken the experiment.

## 12. Required documentation update

Update, without rewriting historical evidence:
- `reports/acceptance/q1-q2-quant-infrastructure-backtest-2026-10-09.md`;
- `reports/evidence/q1-q2-quant-infrastructure-backtest-2026-10-09.json`;
- `docs/Q1_Q2_LEAN_METHODOLOGY.md` if source-evidence semantics change;
- `docs/Q1_Q2_QC_CLOUD.md` with actual Cloud status;
- canonical ledger;
- PR #13 body;
- `codex/tasks/ACTIVE.md` after completion.

Public evidence must remain aggregate/safe. Detailed blocker security IDs, raw bars, mappings, local evidence files and credentials remain private.

## 13. Stop condition

Stop after one of these states:

### SUCCESS
- Q1 blockers closed;
- Q1 Train/Validation local Native complete and reproducible;
- Q2 integrity retained;
- Daily Scanner regression passes;
- full test/protection gates pass;
- QC Cloud Mode A/B completed or externally blocked with precise reason;
- PR #13 release decision completed.

### BLOCKED
- at least one Q1 execution dependency cannot be established with trusted evidence.

Do not continue into:
- Q3;
- Vision;
- Quant+Vision;
- threshold optimization;
- Historical Test/Fresh efficacy runs;
- broker execution.

Final user handoff must state:
1. exact blocker resolution outcome;
2. Q1 Train/Validation Native metrics or NOT_RUN reason;
3. whether prior Q2 results remain unchanged;
4. Daily Scanner current as-of and readiness;
5. full test/protected-file counts;
6. QC Cloud Mode/status/project/backtest IDs if any;
7. PR #13 merged or still Draft;
8. the single next research decision.
