# Stock Radar

<p align="center"><strong>English</strong> · <a href="./README.zh-CN.md">简体中文</a></p>
<p align="center"><img src="./docs/repo-banner.png" alt="Stock Radar repository banner" width="100%"></p>

A broad US-equity research and screening project using Alpaca market data. Phase 1
builds the data foundation: asset master, daily OHLCV bars in DuckDB, incremental
updates, validation, and universe export.

It is research software only. **Nothing in this repository places orders** — no
trading or order endpoint is called anywhere in the package. The Phase 2
features, historical backtest engine, a simplified baseline, and an initial
seven-stage Strategy 2 candidate are implemented. Neither backtest establishes
a deployable trading edge.

## Setup

Requires Python 3.11 or newer. From the project root:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Then edit the untracked `.env` and fill in your Alpaca credentials:

```
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
```

Credentials are read from the environment first, then from `.env` in the project
root (via `python-dotenv`). Both keys are required for `sync` and `validate`;
`init-db` needs neither. `.env` is gitignored — never commit keys.

## Configuration

`config/base.yaml` drives every run:

```yaml
provider: alpaca
database_path: data/market.duckdb
daily_bars:
  feed: sip
  adjustment: split
  lookback_sessions: 400
```

- `feed: sip` — historical daily research uses Alpaca SIP. The feed is passed
  explicitly to every request; there is no automatic fallback to another feed.
- `adjustment: split` — split-adjusted daily bars.
- `lookback_sessions: 400` — number of market sessions (from the Alpaca calendar,
  not calendar days) covered by a default `sync` or `validate` run.
- `database_path` can be overridden by `RADAR_DB_PATH` (environment or `.env`).

## Commands

Run all commands from the project root; settings and `.env` resolve against the
current directory (`--project-root` overrides it).

```powershell
python -m radar init-db
python -m radar sync
python -m radar validate
```

- `init-db` — creates `data/market.duckdb` and applies schema version 1. Safe to
  re-run; existing rows are preserved.
- `sync` — refreshes the asset master and universe export, then downloads only the
  daily-bar sessions that are missing from the database and upserts them.
- `validate` — opens the database read-only, re-checks stored bars for the latest
  observed asset snapshot in the session window, and writes a JSON summary.

`sync` and `validate` both accept these bounded options for smoke runs:

| Option | Meaning |
| --- | --- |
| `--end YYYY-MM-DD` | Last session date to cover. Default: previous US/Eastern day. |
| `--lookback N` | Number of sessions, overriding `lookback_sessions`. |
| `--max-symbols N` | Limit to the first N eligible symbols (sorted by symbol). |

```powershell
python -m radar sync --end 2026-09-24 --lookback 5 --max-symbols 20
python -m radar validate --end 2026-09-24 --lookback 5 --max-symbols 20
```

Each command prints a one-line JSON result to stdout.

## Local data dashboard

Install the optional visualization packages, then start the read-only local site:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[viz]"
& .\.venv\Scripts\python.exe -m streamlit run src/radar/dashboard.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501` in your browser. The dashboard reads the existing
DuckDB database, universe CSV and validation report. It shows coverage, validation
warnings and searchable single-symbol OHLCV charts. It does not call Alpaca,
modify data, provide real-time quotes or place orders. Run `sync` and `validate`
first if the output files are missing; use **刷新数据** after those files change.
The interface uses the open-source [Streamlit](https://github.com/streamlit/streamlit)
and [Plotly.py](https://github.com/plotly/plotly.py) components.

Preview: [overview](docs/dashboard-preview.png) · [warning details](docs/dashboard-warnings.png).

## Local Research Scanner and Strategy Lab

On Windows, double-click `启动本地看板.cmd` in the project root to open both
the Streamlit Strategy Lab on port 8502 and the local web dashboard on port 4174.
It starts or reuses the loopback API on port 8765. Both Lab views show the
three-stage trading-day timeline. The Data navigation link opens the market dashboard.
Local changes to `site/dist/` appear without a Sites
deployment; deploy Sites only when a release is ready.

Scanner Research is the primary workflow: it saves daily candidate rankings,
generic diagnostic scores, 10-session host-generated forward labels, Precision/Lift
at 5/10/20, MFE/MAE and market-regime breakdowns without opening simulated
positions. Strategy Backtest remains available for portfolio diagnostics, with
per-strategy exits (including `null` to turn each automatic exit off).
The plugin interface stays at version 1; see
[the v1.5 scanner specification](docs/STRATEGY_PLUGIN_SPEC.md) for exact label
formulas, eligibility and reproducibility rules.

The Scanner and Strategy Lab are available inside the existing private Sites dashboard at
[`/lab.html`](https://stock-radar-local.zhoushuming.chatgpt.site/lab.html).
The same research interface also has a separate local Streamlit page. It
imports trusted strategy ZIPs, queues several backtests, shows each Run's live
equity/drawdown in its own tab, and compares completed Runs. Market data and
Run results remain on this computer. Nothing in the Lab places broker orders.

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e ".[viz,dev]"
& .\.venv\Scripts\python.exe -m streamlit run src/radar/strategy_lab_ui.py --server.address 127.0.0.1 --server.port 8502
```

Open `http://127.0.0.1:8502`. The current `full_strategy2_v1` plugin is
installed under `strategies/`. A standalone authoring guide and ZIP-ready
example are in [the Strategy Plugin specification](docs/STRATEGY_PLUGIN_SPEC.md)
and `templates/strategy_plugin_template/`. Only import Python strategy code
from authors you trust: structural, AST and test checks are useful validation,
but they are not an operating-system sandbox.

Each run stores its configuration and reproducibility metadata in local SQLite
WAL at `data/strategy-lab/runs.sqlite3`, while workers read the market DuckDB
read-only. Completed Runs are immutable. The two-process local worker cap keeps
the UI responsive and lets a browser refresh recover progress. Cancelling a Run
stops it between sessions. A source/data hash mismatch fails the queued Run
instead of silently executing changed inputs.

The complete Phase 2 Strategy 2 migration was checked against the saved
Train, Validation and previously viewed Test artifacts: 1,231 signal dates and
all equity, order and trade CSV rows matched exactly. Recheck locally with:

```powershell
& .\.venv\Scripts\python.exe scripts/verify_phase3_plugin_parity.py
```

The Test slice was already viewed before Phase 3 and is exploratory. Do not
treat reruns or parameter comparisons on it as fresh out-of-sample evidence.
The open-source selection and license notes are in
[the Phase 3 audit](docs/phase3-open-source-audit.md).

The experiment panel can queue bounded parameter grids (at most 64 variants),
full Strategy 2 stage ablations (baseline plus eight omissions), and rolling
walk-forward folds. Experiments use Train/Validation history only and save each
variant as an independent Run. Walk-forward currently holds parameters fixed
across folds; it reports OOS distribution rather than fitting parameters in
each fold. This avoids a misleading optimization claim.

## Private Sites dashboard and unattended updates

The private [Sites dashboard](https://stock-radar-local.zhoushuming.chatgpt.site)
hosts only HTML, CSS and JavaScript. It reads market data and controls local
research Runs through the loopback `127.0.0.1:8765` API on **this computer**.
The dashboard's market endpoints remain read-only; Strategy Lab endpoints can
queue Runs and import a user-selected plugin ZIP only for the configured Site
origin. DuckDB, Run results, plugin files and Alpaca credentials stay local.
After signing in to the Site, allow its browser
prompt to access the local computer if one appears. Other computers cannot read
this computer's loopback API.

Two Windows tasks are installed for the current user:

| Task | When | Purpose |
| --- | --- | --- |
| `StockRadar-DailyUpdate` | Tuesday–Saturday at 08:30 China time, and at next logon | Update the most recent completed US trading day, backfill missing sessions, then validate. An already successful target date is skipped. |
| `StockRadar-LocalApi` | At logon | Serve the local dashboard and Strategy Lab API on `127.0.0.1:8765`. |

Both use `pythonw.exe` and run without a console window. A missed update while
the computer is off runs after the next logon; the computer must be online to
reach Alpaca. The database remains in `data/market.duckdb`; the latest job
result is in `data/daily-update-status.json`. No market data is uploaded to
Sites by this setup.

To inspect or run the update manually:

```powershell
Get-ScheduledTaskInfo -TaskName StockRadar-DailyUpdate
Get-Content data/daily-update-status.json
Start-ScheduledTask -TaskName StockRadar-DailyUpdate
```

The scheduled run reads Alpaca keys from `.env` when present, otherwise from
`../alpacakey.txt` on this machine. Reinstall the tasks after moving the project
or changing the Site address:

```powershell
& ./scripts/install-automation.ps1 -SiteOrigin 'https://stock-radar-local.zhoushuming.chatgpt.site'
```

## Phase 2 simplified-baseline historical backtest

Phase 2 research uses local SIP, split-adjusted daily bars in
`data/phase2-research.duckdb`. The research database and detailed trade files
stay on this computer and are gitignored. The rules and split definitions are
in `config/research.yaml`, `config/backtest.yaml`, and the final one-time Test
freeze in `config/frozen_backtest_v1.yaml`.

The frozen combined-rank baseline returned **-81.14% Train**, **+4.49%
Validation**, and **-55.10% final Test** after modeled fees and slippage. The
Test portfolio fell from $1,000,000 to $448,957.69. See
[`reports/phase2/backtest_final.md`](reports/phase2/backtest_final.md) for the
full accounting, benchmark, verification, and limitations. The local interactive
chart is `data/research/final-test-v1/回测报告.html` after the run.

With the local research database already prepared, the reproducible commands are:

```powershell
& .\.venv\Scripts\python.exe scripts/run_backtest_research.py
& .\.venv\Scripts\python.exe scripts/run_frozen_backtest.py
& .\.venv\Scripts\python.exe scripts/verify_final_backtest.py
& .\.venv\Scripts\python.exe scripts/render_backtest_report.py
```

The tested candidate ranks high Elasticity and deep 20-session drawdowns. It
does not yet require prior strength, downside exhaustion, support/absorption,
absence of new lows, and early bullish confirmation together. Its result must
not be presented as the full Strategy 2 return.

The baseline's final Test runner records a one-time evaluation marker and
returns the stored result on a repeat invocation.

## Full Strategy 2 exploratory research

The first seven-stage candidate includes prior strength, pullback, downside
exhaustion, support/absorption, stopped new lows, early reversal, and an
extension limit. The exact feature mapping and provisional thresholds are in
[`reports/phase2/full_strategy2_feature_map.md`](reports/phase2/full_strategy2_feature_map.md).
At 10 bps slippage per side plus illustrative fees, it returned **-36.83%
Train**, **+29.11% Validation**, and **+10.75% on the previously viewed
historical Test**. Results and cost sensitivity are in
[`reports/phase2/full_strategy2_backtest.md`](reports/phase2/full_strategy2_backtest.md).
That Test result is exploratory because its dates were already viewed for the
baseline; it is not fresh out-of-sample evidence.

```powershell
& .\.venv\Scripts\python.exe scripts/run_full_strategy2_backtest.py --splits train validation
& .\.venv\Scripts\python.exe scripts/run_full_strategy2_backtest.py --splits test
& .\.venv\Scripts\python.exe scripts/verify_full_strategy2_backtest.py
& .\.venv\Scripts\python.exe scripts/print_full_strategy2_summary.py
& .\.venv\Scripts\python.exe scripts/render_full_strategy2_report.py
```

Detailed ledgers, scenario summaries, and verification stay in the gitignored
`data/research/full-strategy2-v1/` directory. The self-contained local chart is
`data/research/full-strategy2-v1/策略2完整条件回测.html`. A new untouched period is needed
to validate any claimed improvement. This remains research, not an order signal.

## Outputs

| Path | Contents |
| --- | --- |
| `data/market.duckdb` | DuckDB database: `assets` (asset master) and `daily_bars` (OHLCV + provider/feed/adjustment provenance), plus `schema_migrations`. |
| `data/universe.csv` | Eligible universe, sorted by symbol, columns: `symbol, name, exchange, asset_class, tradable, fractionable, shortable`. |
| `data/validation-summary.json` | Latest `validate` report: checked/accepted/rejected rows and structured issues. |
| `data/ingestion-issues.json` | Latest `sync` report: failed symbols and detailed data issues. |

Generated files under `data/` are gitignored.

## Conventions and limitations

- **Asset master comes from current snapshots.** Only active US-equity assets are
  requested from Alpaca, so tickers that were delisted or renamed before the first
  `sync` never enter the database. Historical research over 400 sessions therefore
  carries **survivor bias**; it is not a point-in-time universe.
  Previously observed assets remain in the master with an older `last_seen`;
  `validate` uses only the newest observed snapshot.
- **The eligible filter is coarse, not common-stock-only.** It keeps US-equity
  assets that are `active` and `tradable` and listed on NASDAQ, NYSE, AMEX, ARCA
  or BATS. ETFs, ADRs, preferred shares and similar listed equity-like classes pass
  the filter. OTC and non-major venues are excluded.
- **No feed fallback.** If SIP is rejected (e.g. HTTP 401/403), the run fails with
  a provider error instead of silently switching to another feed.
- **Provenance is strict.** Bars carry `provider`, `feed` and `adjustment`, and a
  row may be replaced only by a newer download with the same triple. Writing into
  the same database with a conflicting provider/feed/adjustment raises an error
  rather than mixing series.
- **Zero-volume bars keep nullable VWAP.** Alpaca can report `vwap = 0` with zero
  trades; that is mathematically undefined, so `NULL` is stored instead of
  rejecting an otherwise valid bar.
- **Missing sessions are retried, not skipped.** Ingestion re-requests any session
  window with no stored bars on every run, so a halted or newly listed ticker whose
  bars do not exist yet is requested again on the next `sync`.
- **Large price jumps warn, they do not reject.** A close-to-close move beyond the
  jump threshold is recorded as a `warning` (code `abnormal_price_jump`) because
  splits and other corporate actions can legitimately cause it. Review these
  manually.
- **No corporate-action reconciliation.** There is no automated handling of
  splits, mergers, or ticker changes beyond the provider's split adjustment.
- **Validation is non-destructive.** It reads stored bars and flags gaps, missing
  sessions, stale tickers and malformed rows; it does not delete or repair data.

## Tests

The test suite is fully offline: it uses in-memory/temporary DuckDB databases and
fake provider objects, and it never contacts Alpaca or reads real credentials.

```powershell
& .\.venv\Scripts\python.exe -m pytest
```

`pyproject.toml` sets `testpaths = ["tests"]` and `pythonpath = ["src"]`, so a bare
`pytest` from the project root works too.

