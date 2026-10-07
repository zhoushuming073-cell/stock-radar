# Local LEAN execution

Stock Radar is the sole strategy and selection implementation. The local website
launches **LEAN only**. The previous UI is archived at the GitHub tag
[`legacy-backtest-ui-2026-10-06`](https://github.com/zhoushuming073-cell/stock-radar/tree/legacy-backtest-ui-2026-10-06).
The old Python execution engine remains a compatibility/golden-case validator;
it is not a web launch option. Saved legacy results remain readable and labeled.

## Boundary and workflow

1. Select an exact strategy version and Train, Validation, historical Test, or
   Fresh OOS when available. Historical Test remains exploratory.
2. Stock Radar either verifies an existing matching historical Scanner snapshot,
   or generates all historical daily selections through its shared causal
   strategy adapter. Portfolio holdings never change these frozen selections.
3. Signals and execution prices are frozen, hashed, and stored locally under
   `data/strategy-lab/lean/<run_id>/` before LEAN starts.
4. An isolated worker invokes the compiled, independent LEAN source launcher.
   LEAN manages the actual simulated portfolio, cash, orders, fills, fees and
   slippage. The generic algorithm contains no Strategy 2 or other plugin logic.
5. Native portfolio observations stream into the existing daily timeline. A
   result adapter reconciles them to LEAN's raw final equity, orders and fees,
   then writes `normalized-result.json` and publishes the result to RunStore.
6. Existing curves, drawdown, positions, trades, activity, Compare, history,
   rename/delete/restore and research export continue to use the local API.
   Compare and export distinguish engines/builds and execution assumptions.

One-stage runs, three-stage timelines, and Backtest experiments all use LEAN.
The three stages execute sequentially and reset capital and positions at each
stage. Each day's actual portfolio snapshot is displayed in chronological order.
Pause changes display only. No legacy fallback occurs if LEAN fails.

## Independent installation

The installation remains outside this repository. `config/lean.yaml` currently
selects `D:\QuantConnect-LEAN`; `STOCK_RADAR_LEAN_ROOT` overrides the path.
The configured installation must contain:

```text
engine/Launcher/bin/Release/QuantConnect.Lean.Launcher.dll
engine/Launcher/bin/Release/QuantConnect.Lean.Engine.dll
runtime/dotnet/dotnet.exe
runtime/python-package/tools/python311.dll
config/demo-python.json
engine/Data/market-hours/market-hours-database.json
engine/Data/symbol-properties/symbol-properties-database.csv
```

This bridge uses the free compiled source launcher, without the paid CLI, Docker,
cloud backtests, broker orders or broker credentials. Both worker and launcher
start without console windows on Windows. Cancellation and timeout terminate the
native child process. Reuse the existing one-click local website launcher.

`config/lean.yaml` also sets a run timeout and maximum simultaneous positions
(default 30). Runs record the effective limit. Legacy launch remains available
only for explicit programmatic compatibility checks (`engine="legacy"`).

## Signal contract: `stock-radar-signals-v1`

Each record has `signal_date`, `symbol`, `rank`, `strategy_score`, `strategy_id`,
`strategy_version`, timezone-aware session-close `available_at`, and the following
causal execution context: `reference_close`, `avg_dollar_volume_20`, and a
Stock Radar-computed `allocation_weight`.

Only these fields are accepted. Forward labels and undeclared fields are
rejected. Duplicate symbol/date records, invalid dates, non-finite values and
strategy identity mismatches are rejected. The manifest preserves empty signal
days, the requested sessions, source Scanner ID, strategy/config/code identity,
research database hash, execution price export hash and exchange-reference hashes.
The worker binds the sealed manifest hash once. The runtime verifies the manifest,
configuration, algorithm, signals, price export, data index and consumed files
before and after native execution; the algorithm verifies its manifest and signal
hashes before initialization. It cannot consume a same-day/future signal as an entry.
Stock Radar precomputes any market guard;
LEAN does not calculate selection factors.

## Execution assumptions of this first bridge

- Inputs are **daily bars**, not actual minute data. Two flat native Equity
  minute-format observations reveal only Open at 09:31 ET and Close at the
  exchange close (including early closes). The Open proxy is the source daily
  Open, not a claim about the actual 09:31 quote. No future daily Close is
  available to the opening event.
- Signals at close enter next session. Close-based TP/SL/holding conditions
  schedule exits at the next Open. Opening gaps can trigger exits before new
  entries. TP/SL use acquisition cost including entry fees, matching the
  existing policy. Positions are not forcibly closed at the evaluation end.
- Native LEAN ImmediateFillModel, ConstantSlippageModel and configurable fee
  model are used. Sizing is cash-funded with leverage 1, position/ADV caps and
  the configured position limit. Settlement is immediate, preserving the
  previous research convention; real settlement availability is not simulated.
- The input price basis is preserved with Raw normalization and identity map /
  factor files. No additional splits, dividends, delisting payouts or intraday
  path are invented. Price serialization precision is USD 0.0001. Quotes,
  order-book depth and partial fills are not simulated. Existing unconfirmed
  illustrative fee schedules retain that status.
- Current Snapshot retains its documented survivorship/data risks. Point-in-Time
  PIT execution requires a frozen full-population Run dependency closure and all
  six preflight gates PASS. The installed representative Validation Run remains
  BLOCKED. Native rename/split/cash-entitlement cases are validated separately;
  unsupported terminal economics remain blocked. It never silently downgrades
  to Current Snapshot or legacy. See [PIT execution](PIT_LEAN_DATA_DESIGN.md).

## Result contract: `stock-radar-backtest-v1`

`run_metadata`: engine, strategy/version, signal source/snapshot, data snapshot,
dates, initial capital through the resolved execution configuration, LEAN commit,
launcher/engine/Python SHA-256 and installation patch hash.

`equity`: timestamp/date, equity, cash, holdings value, benchmark and drawdown.
The existing field name is retained for UI compatibility.

`trades`: entry/exit times, reference and execution prices, quantity, fees,
net P&L/return, holding sessions and exit reason. Concise native exit tags omit
the legacy `_signal_next_open` suffix; their recorded execution timing is equal.

`orders`: order ID/time, fill time, symbol, direction, quantity, reference price,
fill price, native fee and status. Filled orders are reconciled with LEAN orders.

`statistics`: return, applicable CAGR, drawdown, Sharpe/Sortino, trade count,
win rate, average win/loss, profit factor, turnover, fees and benchmark return.
`statistic_sources` identifies presentation analytics versus native LEAN fields;
native statistics are preserved separately. Undefined estimates are null,
including CAGR for fewer than 252 sessions. Drawdown includes initial capital.

The front end reads `/api/lab/equity`, `/trades`, `/events`, `/days`, `/orders`
and `/result`. `/api/lab/engine` reports local availability and build identity.
No front-end code interprets native QuantConnect JSON.

## Verification

Latest recorded native-inclusive acceptance on **2026-10-06: 272 passed,
1 existing websockets deprecation warning**. After final preparation-cancellation
changes, targeted worker/store tests also passed (15 tests). See the
[development-stage report](../reports/current/development-status-2026-10-06.md) for the
scope and remaining gaps. These are local results, not hosted-CI evidence.

Native golden cases compare the same frozen candidates, dates, initial capital,
sizing, fees, slippage and exit conditions against the compatibility engine.
Assertions cover each trade's dates/prices/quantity/fees/P&L, every day's cash
and equity, TP/SL, max hold, re-entry, empty signals and child cancellation.
The adapter also rejects deliberately corrupted native final equity.

```powershell
$env:STOCK_RADAR_TEST_LEAN = '1'
.venv\Scripts\python.exe -m pytest -q
```

Without this opt-in, portable tests run and native-installation tests are skipped.
Golden evidence and generated results stay in ignored local `data/`.

A real smoke test reused historical Scanner `1eed6775-9d24-47c9-a5ef-d00d1641c7ec`
for Bottom Base Green Candle v1 validation, 2024-09-30 through 2025-09-22:
245 sessions and 96 closed trades. Detailed results and balances remain local.
This is integration evidence, not fresh OOS
or proof of a tradable edge. The local browser displayed the native-derived
portfolio, benchmark, drawdown, positions, trades and engine audit.

LEAN is [QuantConnect/Lean](https://github.com/QuantConnect/Lean), Apache-2.0.
Its source and runtimes are not copied into Stock Radar's Git repository.

The 2026-10-07 final PIT pass has 377 local tests passing with native LEAN enabled.
See [final PIT acceptance](../reports/acceptance/pit-final-acceptance-2026-10-07.md) for
the complete frozen Validation comparison, supported action accounting,
remaining Run dependency failures and the difference between event goldens
and formal strategy execution.
