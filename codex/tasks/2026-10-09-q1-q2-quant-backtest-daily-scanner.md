# Codex Work Order — Q1/Q2 Quant Infrastructure, Local LEAN → QC Cloud, Daily Watchlist

> Date: 2026-10-09  
> Status: **ACTIVE USER-AUTHORIZED WORK ORDER**  
> Research family: **A. Quant-only** under [Research Master Guide](../../docs/RESEARCH_MASTER_GUIDE.md)  
> Scope: finish Q1/Q2 Quant infrastructure, build a real latest-session watchlist, run reproducible local QuantConnect LEAN backtests, then—only after local gates pass—run compliant QuantConnect Cloud backtests/validation.  
> Out of scope: Vision training, Quant+Vision fusion, Q3 optimization, broker/live orders, paid services, or claiming alpha from exploratory evidence.

## 0. User intent

The user wants two concrete outcomes now:

1. **Complete Q1 and Q2 as usable Quant research methods**, then backtest them locally with QuantConnect LEAN, and only afterward test them in QuantConnect Cloud when the current account/platform rules permit.
2. **Restore the original Stock Radar product goal:** on the latest completed US trading session, use Q1/Q2 to screen the current market and produce a practical list of stocks worth watching today.

The project is still in research infrastructure / method-definition stage. This task must produce real engineering and reproducible research evidence, but must not overstate any result as a validated trading edge.

Current methods:
- **Q1 = fuzzy-shape-v1**: prior strength → pullback → downside exhaustion → OHLCV support/absorption proxies → early turn-up → extension/entry-position risk. It exists in current main, originally embedded in Quant-guided labeling infrastructure. Its predictive efficacy is unvalidated.
- **Q2 = parallel-channel-v1**: monthly/weekly parallel channel + repeated boundary tests/alternation + non-monotonic-decline gate + current daily lower-band / stabilization logic. It currently exists only in Draft PR #10 and has not passed real-market/full-project acceptance.

Current shared constraints:
- Research Infrastructure v1 is frozen/reusable.
- Historical PIT/identity/delisting coverage is incomplete and must remain explicit.
- The v3 Vision/Human/Y subsystem is accepted engineering but human labeling is paused.
- Historical Test has already been viewed in prior work and is never “fresh OOS”.
- Current QC Cloud tooling has a documented export-scope hold after an actual Terms 2.6 warning. Do not bypass it.

Read before coding:
- `AGENTS.md`
- `docs/RESEARCH_MASTER_GUIDE.md`
- `reports/journey-2026-09-30-0651-📌当前总账.md`
- `docs/RESEARCH_INFRASTRUCTURE_V1.md`
- `docs/LEAN_EXECUTION.md`
- `docs/QUANTCONNECT_FREE_VALIDATION.md`
- `reports/acceptance/qc-cloud-smoke-validation-2026-10-08.md`
- `reports/acceptance/qc-cloud-validation-readiness-2026-10-07.md`
- Q1 source/config/tests in current main
- Draft PR #10 source/docs/tests
- current Scanner/Strategy Lab/API/UI implementation and daily updater

Do not trust old README checklist items over the master guide / canonical ledger.

---

# 1. Repository and branch safety

1. Synchronize local working copy with latest GitHub `main`.
2. Inspect local uncommitted changes and private data before any checkout/rebase.
3. Inspect Draft PR #10 and compare it with latest main.
4. Do **not** force-merge or blindly rebase PR #10.
5. Prefer a new implementation branch from latest main and selectively port/reconcile Q2 source, tests, config and docs.
6. Preserve all current Research Infrastructure hashes, Strategy 2 frozen code, old labels, private market databases and acceptance evidence.
7. Never commit:
   - real market OHLCV extracts;
   - private daily watchlist history if it exposes detailed local market data beyond safe aggregate evidence;
   - credentials / sessions / QC login data;
   - private human labels;
   - local SQLite/DuckDB stores;
   - QC raw market data.

At the start, write a short local plan stating:
- current main SHA;
- PR #10 head SHA;
- local data availability;
- local LEAN availability/build;
- QC Cloud account/session availability if visible;
- any current Terms/export hold;
- intended new branch.

---

# 2. Q1 — promote fuzzy-shape-v1 into first-class Quant infrastructure

Q1 currently works as part of the Quant-guided visual-label workflow. Refactor only as needed so Q1 can be reused independently by:

- historical research;
- local LEAN signal generation;
- latest-session daily scanner;
- later Quant+Vision work.

## 2.1 Stable Q1 contract

Create/confirm a versioned Quant research API under an appropriate `radar.research` namespace instead of making the daily product depend on a vision-labeling module.

The Q1 result should expose, at minimum:

- security/date identity privately;
- `method = q1_fuzzy_shape`;
- version;
- total score;
- A prior-strength score;
- B pullback score;
- C downside-exhaustion score;
- D OHLCV support/absorption **proxy** score;
- E early-turn score;
- F extension / price-position score;
- candidate/watch state;
- explicit reason codes / gate failures;
- input-window length;
- data/provenance hash.

Do not silently change the current Q1 semantics while extracting the module.

First create parity tests proving the refactored Q1 returns the same score/rank as the accepted `fuzzy-shape-v1` implementation on fixed fixtures and a bounded real local sample.

Any subsequent Q1 semantic change must:
- have a new version;
- be justified by structural/correctness logic, not by looking at returns;
- keep the original v1 reproducible.

## 2.2 Q1 adapters

Q1 must have two explicit data adapters:

**Historical research adapter**
- Research Infrastructure v1 / historical eligible universe;
- honors Train/Validation/Test/Fresh boundaries;
- keeps unknown membership/identity uncertainty explicit.

**Current/latest-session adapter**
- current local `market.duckdb` / latest eligible tradable market snapshot;
- intended for “today’s watchlist” only;
- must not be used to claim survivorship-bias-free historical performance.

No future data may enter either adapter.

---

# 3. Q2 — harden Parallel Channel before merging

Draft PR #10 is an experimental starting point, not an accepted strategy.

Port and review it against latest main, then address the following correctness/design issues before real-market acceptance.

## 3.1 Coordinate consistency

The channel is fit in log-price space. Use one consistent coordinate definition for:
- long-horizon channel position;
- current lower-band distance;
- daily entry-position calculations.

Do not calculate one stage in log space and another in linear price space while comparing the same “position” threshold.

Add tests where a wide channel makes log-space and linear-space positions materially different.

## 3.2 Lower-band breach handling

A price below the lower channel may be:
- small/temporary undercut;
- meaningful breakdown.

Do not reward negative channel position as a perfect lower-band-distance score.

Define a versioned policy with:
- near-lower inside-channel region;
- tolerable undercut region with explicit penalty;
- breakdown / invalid region.

The exact initial knots must be disclosed and must **not** be optimized from future returns in this task.

## 3.3 Real pivot / impulse-pullback structure

Do not define “low → rally → pullback” merely by finding any two indexes satisfying a percentage inequality.

Implement a robust but simple past-only pivot/prominence/local-extrema rule, or another clearly specified causal alternative.

Tests must cover:
- monotonic fall;
- noisy random walk;
- real low → rally → pullback;
- false micro-bounce;
- lower-band break;
- incomplete current bar.

## 3.4 Multi-window stability

Q2 currently searches several weekly/monthly windows and takes the best-looking result.

Add a stability/consensus diagnostic so one lucky window cannot alone create a high-confidence channel.

Possible implementation:
- best-window score remains;
- separately calculate agreement among neighboring candidate windows for slope, lower/upper band geometry and current position;
- expose `stability_score` / `window_agreement`;
- optionally require minimum stability only for “qualified”, while still retaining near-miss/watch candidates.

Do not tune the window set or consensus thresholds to maximize backtest results in this task.

## 3.5 Partial weekly/monthly bars

Using T-prefix daily data to form a partial current week/month is causal, but its bucket-end label can point to a later Friday/month-end.

Make the metadata unambiguous:
- `observed_through = T`;
- optional bucket end stored separately;
- no future-labeled date leaks into model/task/UI semantics.

## 3.6 Trading calendar

`--asof` must actually validate a completed US exchange session using the project’s exchange calendar utilities, not merely “last row equals asof”.

Latest-session mode must choose the latest **completed** session, accounting for weekends/holidays and data freshness.

## 3.7 Historical vs current universe

The current Draft defaults to active current assets.

That is acceptable for the **daily product**, but not for historical backtesting.

Provide:
- current-market scanner path;
- Research Infrastructure v1 historical path.

Never use current-active symbols to claim historical unbiased results.

## 3.8 Q2 acceptance

Before Q2 can merge:
- targeted Q2 unit/property tests pass;
- real local full-market/latest-session scan completes;
- sample distribution and candidate count are reported;
- manually inspect a small safe local set of top / borderline / rejected charts for structural sanity;
- full project pytest + Native LEAN regression pass;
- no frozen infrastructure hash unexpectedly changes.

Do not claim Q2 predicts returns merely because charts look sensible.

---

# 4. Common Q1/Q2 Quant candidate contract

Implement one shared result schema/interface so the rest of Stock Radar does not need separate bespoke logic.

At minimum:

```text
method
version
decision_date
security_id/private symbol mapping
score
rank
status
subscores
reason_codes
window metadata
quality/uncertainty flags
source/data/config/code hashes
```

Q1 and Q2 scores are **not assumed to be numerically comparable**.

For this task:
- do not invent a Q3 weighted score;
- do not optimize a combined Q1/Q2 rank.

You may derive:
- Q1-only list;
- Q2-only list;
- simple set overlap (`Q1 ∩ Q2`);
- union with source flags.

“Both methods selected it” may be displayed as an overlap fact, not as a proven superior signal.

---

# 5. Restore the original product function: latest-session watchlist

Build a real, maintainable **Latest-session Daily Scanner** using Q1 and Q2.

This is a product/research utility, not a broker signal.

## 5.1 Decision time

Default:
- use the latest completed US trading session for which required local bars are available;
- never use an in-progress daily candle as though it were complete;
- display `as_of` explicitly.

If local market data is stale:
- show the latest available completed session;
- show a visible stale-data warning;
- offer the existing safe sync/update action where available;
- do not silently fabricate “today”.

## 5.2 Outputs

Provide three views:

1. **Q1 Watchlist**
2. **Q2 Watchlist**
3. **Q1 ∩ Q2 Overlap**

Default display can be Top 20 per method, configurable within a bounded range.

Each row should show enough interpretable information, for example:
- ticker/company only in the live/current product;
- method;
- rank;
- score;
- key subscore/structure summary;
- Q1: pullback/exhaustion/turn/extension state;
- Q2: timeframe/window, channel slope/width, stability, lower-band position, daily state;
- warnings/data quality;
- why selected / why only watch;
- latest close date.

Do **not** output a stock just to fill Top N if it does not meet that method’s minimum research/watch criteria. “No qualified candidates today” is valid.

Do not label the list “buy recommendations”. Use wording such as:
- 今日关注;
- Watch;
- early reversal;
- near lower band / wait;
- qualified setup.

## 5.3 CLI / API / UI

Deliver all three:

**CLI**
- one command to scan latest completed session;
- `--asof` reproducibility option;
- `--method q1|q2|all`;
- safe JSON/CSV local output.

**API**
- read-only endpoint for current/latest Q1/Q2 watchlist;
- response includes as-of date, freshness and hashes;
- no broker action.

**Local Web UI**
- integrate into existing Scanner/Stock Radar interface rather than creating an unrelated app;
- show Q1 / Q2 / overlap tabs or sections;
- allow opening the existing price chart;
- clearly mark research-only and data timestamp;
- browser smoke test on real local results.

## 5.4 Daily persistence

Save an immutable/lightweight local daily snapshot sufficient for reproducibility:
- decision date;
- method/version;
- ranked candidates;
- hashes;
- reasons;
- data freshness.

Keep detailed private data under ignored local storage.

Daily updater may optionally generate the watchlist **after** a successful market update, but:
- do not make a failed scanner break the market-data update itself;
- record scanner status separately;
- manual one-click/CLI run must remain available.

---

# 6. Freeze the Quant research versions before looking at backtest returns

This task may fix:
- causal bugs;
- coordinate inconsistency;
- calendar bugs;
- API/refactor issues;
- clear semantic defects described above.

It must **not** iteratively tune thresholds after looking at portfolio returns.

Before the first research backtest that will be used for comparison, create a freeze receipt containing:
- Q1 version/config/hash;
- Q2 version/config/hash;
- universe/data contract;
- ranking criteria;
- execution contract;
- fee/slippage config;
- backtest dates;
- Top-K;
- cooldown/duplicate-position policy;
- code SHA.

If a later change is required after seeing results, version it as a new experiment and record that the prior result influenced the revision.

---

# 7. Historical signal generation and local QuantConnect LEAN backtest

The goal is to obtain the **first reproducible Quant-only Q1/Q2 strategy evidence**, not to optimize a pretty equity curve.

## 7.1 Methods tested separately

Run Q1 and Q2 as separate selectors.

Primary strategy runs:
- **Q1-only**
- **Q2-only**

Do not backtest a tuned Q1+Q2 combined strategy in this task.

Report overlap as diagnostics.

## 7.2 Historical universe

Use Research Infrastructure v1 / the strongest permitted historical research universe.

Report:
- PIT/identity coverage;
- excluded unknowns;
- missing prices;
- disappeared/delisted coverage;
- any current-survivor fallback.

If the strict formal PIT path is blocked, do **not** silently substitute current snapshot and call it PIT.

A bounded research-grade/Shape path may be used if explicitly labeled with its known bias limitations.

## 7.3 Pre-registered primary execution contract

Use one simple primary contract for both Q1 and Q2:

- signal decision: after T close;
- earliest entry: **T+1 tradable open**;
- select up to **Top 10** valid candidates for that method;
- equal-weight available capital across active positions;
- maximum **10 trading sessions** holding period;
- primary exit: close at the end of the 10th tradable session;
- prevent overlapping duplicate positions in the same security;
- after entry, the selector does not retroactively change the original signal;
- use the existing local LEAN fee/slippage configuration, but clearly label any fee model that has not been verified against the user’s actual broker.

Rationale: fixed-horizon primary exit avoids optimizing stop/target behavior before Q1/Q2 candidate quality is understood.

Secondary diagnostics may include:
- Top 5 / Top 20 ranking sensitivity;
- existing +5% / -3% Y-event statistics;
- MFE / MAE.

These are diagnostics only. Do not choose the “best” K/target after seeing results and call it the strategy.

If the existing LEAN adapter requires a slightly different execution mechanic, preserve the economic meaning and document the exact mapping before the first run.

## 7.4 Research splits

Run in this order:

1. **Train** — engineering/research sanity.
2. **Validation** — first comparative research evidence after method freeze.
3. **Historical Test** — optional one-time exploratory run only after the Q1/Q2 method/config and execution contract above are frozen.

Historical Test is already contaminated by prior project research and must be labeled:
- `historical_test_exploratory`;
- **not fresh OOS**.

Do not run the new Q1/Q2 strategy on Fresh as part of this task unless a genuinely valid post-freeze period and existing Fresh contract explicitly allow it. Default: **Fresh NOT_RUN**.

## 7.5 Local LEAN integration

Use the existing independent local QuantConnect LEAN execution pipeline.

Q1/Q2 should own stock selection; LEAN should own:
- cash;
- holdings;
- orders;
- fills;
- fees/slippage;
- portfolio accounting.

Before LEAN starts:
- freeze/hash daily Q1/Q2 signals;
- freeze execution prices/inputs under existing contract;
- save manifest.

The generic LEAN algorithm must not contain hidden Q1/Q2 selection logic if the architecture uses frozen signals. If a native strategy adapter is added, preserve one source of truth and parity-test it.

## 7.6 Required local metrics

For Q1 and Q2 separately report:
- dates / eligible security-days;
- signal days;
- candidate count distribution;
- top-10 selections;
- trade count;
- average holding period;
- turnover;
- gross/net total return;
- CAGR where meaningful;
- max drawdown;
- volatility / Sharpe only with clear assumptions;
- win/loss distribution;
- median/mean trade return;
- worst trades;
- year/regime breakdown;
- benchmark comparison;
- fees/slippage total;
- MFE/MAE;
- Q1/Q2 daily selection overlap;
- coverage/data-quality warnings.

Do not reduce the comparison to total return alone.

Also report candidate-domain Precision/Lift / target statistics using the existing Scanner research machinery where compatible.

---

# 8. Local acceptance gate before any QC Cloud run

Do **not** go to QC Cloud until all mandatory local gates pass:

- Q1 refactor parity PASS;
- Q2 targeted tests PASS;
- Q2 real latest-session/full-current-market scan PASS;
- Daily Scanner CLI/API/UI PASS;
- deterministic/historical signal generation PASS;
- local Q1 LEAN run PASS;
- local Q2 LEAN run PASS;
- full project pytest PASS;
- Native LEAN regression actually executed;
- protected/frozen hashes unchanged except explicitly approved new files;
- no hidden future leakage;
- method/config freeze receipt written.

If a local strategy backtest fails because historical PIT/identity/price gates block it, report the blocker. Do not weaken data gates merely to reach Cloud.

---

# 9. QuantConnect Cloud — only after local freeze and local PASS

The user wants QC Cloud after local LEAN.

This task authorizes a **bounded Cloud validation/backtest**, subject to actual account capabilities and current platform rules.

## 9.1 Re-read current platform constraints

Before staging:
- inspect current repository QC docs/reports;
- inspect any current UI warning shown by QC;
- do not assume the old 2026-10-08 behavior still applies.

Existing documented state:
- two actual Cloud smoke runs were previously imported and parser-verified;
- prior campaign had an actual Terms 2.6/export-scope warning;
- raw/reference market-data export campaign was placed on HOLD.

**Do not bypass that hold by changing file format, encoding, logs, Object Store, API, screenshots, or another workaround.**

Do not purchase a plan or use paid API/CLI without a separate user request.

## 9.2 Preferred Cloud validation modes

Use the strongest compliant mode available.

### Mode A — QC-native Q1/Q2 selection (preferred if feasible)

Implement the frozen Q1/Q2 logic inside a bounded QC Cloud algorithm using QC’s own historical data/universe, with the same:
- T decision semantics;
- method config;
- Top 10;
- T+1 entry;
- 10-session hold;
- portfolio sizing.

This provides stronger data/execution independence.

Do not export QC raw bars or reconstruct the QC dataset locally.

Only use standard permitted backtest outputs / aggregate statistics / trades/logs within the platform’s normal workflow.

### Mode B — frozen-signal Cloud execution validation

If native Q1/Q2 selection is blocked by free-tier universe/history/API constraints, stage the locally frozen Q1/Q2 signals into QC Cloud and let QC execute them.

This validates **execution/accounting only**, not independent stock selection.

The final report must say exactly that.

### Mode C — BLOCKED

If Terms warnings, project limits, login/session constraints or free-tier restrictions prevent a compliant run:
- stop;
- record the exact blocker;
- do not manufacture a Cloud PASS from local output.

## 9.3 Cloud projects

Use separate clearly named projects/runs for Q1 and Q2, e.g.:
- `SR-Q1-Fuzzy-Quant-v1`
- `SR-Q2-Channel-Quant-v1`

Do not overwrite historical smoke projects.

Record:
- project/backtest IDs;
- code/config hashes;
- cloud mode A/B;
- actual dates;
- actual completion status;
- standard returned performance statistics;
- warnings/errors.

Do not tune Q1/Q2 after seeing Cloud results.

## 9.4 Local vs Cloud comparison

Compare only what is legitimately available:
- trade dates/symbols if standard results allow;
- order/fill counts;
- total return;
- drawdown;
- fees;
- benchmark;
- holdings/trade summaries;
- execution differences.

Do not require or attempt raw QC OHLCV export.

If Mode A uses QC’s own universe/data, differences from local selections are a research result, not automatically a bug. Attribute differences to:
- universe;
- price basis;
- corporate actions;
- identity;
- history availability;
- algorithm semantics;
before changing parameters.

---

# 10. Tests and leakage / robustness gates

Add tests for at least:

## Q1
- parity with original fuzzy-shape-v1;
- future mutation after T does not change score;
- current vs historical adapter boundaries;
- no Vision/H/Y dependency.

## Q2
- log-coordinate position consistency;
- lower-band undercut vs breakdown;
- pivot/prominence behavior;
- multi-window stability;
- partial week/month observation timestamp;
- exchange-calendar as-of;
- future mutation invariance;
- monotonic decline rejection;
- noisy false-channel cases.

## Daily scanner
- weekend/holiday latest-session resolution;
- stale-data warning;
- empty valid result;
- Q1/Q2/overlap output;
- deterministic rerun;
- no future fields;
- no broker/order path.

## Backtest
- T signal cannot enter before T+1;
- fixed 10-session hold;
- duplicate-position rule;
- Top 10 determinism;
- split boundary / embargo;
- signal/config hash binding;
- same frozen signals yield same local LEAN bundle;
- no Historical Test result changes method config.

## Cloud staging
- project bundle contains only approved code/config/frozen signal artifacts;
- no raw local OHLCV upload;
- no credentials;
- no QC raw market export path;
- project quotas / file sizes respected;
- results cannot be accepted without actual Cloud completion evidence.

Run:
- targeted tests;
- full pytest;
- Native LEAN opt-in regression;
- browser smoke for Daily Scanner;
- real local Q1/Q2 backtests.

Report exact pass/fail/skip counts. Historical “728 passed” is not a substitute for a new run.

---

# 11. Documentation / evidence deliverables

Add/update:

- Q1 research/scanner documentation;
- Q2 accepted specification replacing/superseding the Draft PR #10 doc where appropriate;
- a common Q1/Q2 Quant scanner contract;
- latest-session Daily Scanner user guide;
- local LEAN Q1/Q2 backtest methodology;
- QC Cloud Q1/Q2 validation notes;
- canonical ledger;
- README / README.zh-CN only where current product/status actually changed.

Create a real acceptance report, suggested:

`reports/acceptance/q1-q2-quant-infrastructure-backtest-2026-10-09.md`

and machine-readable evidence, suggested:

`reports/evidence/q1-q2-quant-infrastructure-backtest-2026-10-09.json`

The report must clearly separate:

1. **Engineering PASS/FAIL**
2. **Candidate-quality observations**
3. **Local LEAN research results**
4. **QC Cloud Mode A/B/BLOCKED results**
5. **Daily Scanner product readiness**
6. **Known data/PIT limitations**
7. **What is not proven**

Do not write “strategy validated” unless a genuinely new OOS protocol later supports that claim.

---

# 12. GitHub / PR handling

- Base implementation on latest main.
- Reuse PR #10 code selectively.
- Do not merge PR #10 simply because this task exists.
- If the new accepted implementation supersedes PR #10, leave a clear provenance note and close #10 only after the new PR is merged and evidence exists.
- Open one main implementation PR when the work is coherent.
- Keep large/private/generated research artifacts out of Git.
- Merge only if mandatory engineering gates pass.
- If Cloud is blocked but all local engineering passes, it is acceptable to merge local Q1/Q2 + Daily Scanner with Cloud status explicitly `BLOCKED/PENDING`; do not hold a useful local product hostage to an external platform limitation.

---

# 13. Explicit non-goals

Do not in this task:
- train Vision / CNN / ViT;
- build Quant+Vision Fusion;
- optimize Q3;
- use H_blind/H_review to tune Q1/Q2;
- use future Y to choose Q1/Q2 thresholds;
- grid-search returns until a profitable backtest appears;
- rename old Historical Test as Fresh;
- use current active stock list as a supposedly unbiased historical universe;
- bypass QC Terms/export warnings;
- purchase QC resources;
- send broker orders or add live trading;
- claim that “both Q1 and Q2 agree” is proven superior before testing it.

---

# 14. Stop condition and final user handoff

This work order is complete when the project has:

1. **Q1 productionized** as a first-class independent Quant method with parity evidence.
2. **Q2 hardened and real-market accepted** or an explicit blocker report.
3. **Latest-session Daily Scanner** usable locally for Q1/Q2/overlap.
4. **Reproducible local LEAN backtests** for Q1-only and Q2-only under the frozen common execution contract.
5. **QC Cloud** run completed in compliant Mode A/B, or truthfully marked BLOCKED with reason.
6. Full tests / Native LEAN / browser acceptance recorded.
7. No Vision training or return-driven parameter optimization performed.

Final response to the user must provide:

- merged PR / commit or Draft blocker;
- exact local Daily Scanner URL and CLI;
- current `as_of` date and whether data is fresh;
- Q1 top candidates count, Q2 top candidates count, overlap count **without treating them as buy advice**;
- local LEAN Q1/Q2 headline metrics with explicit exploratory label;
- QC Cloud mode, project/backtest IDs and result status;
- exact test counts;
- major data/PIT limitations;
- whether Q1/Q2 are now technically ready for routine daily watchlist use;
- the single next research decision to make.

Then stop. Do not automatically start Vision/Fusion work.
