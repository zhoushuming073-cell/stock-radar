# Stock Radar Strategy Plugin Specification (interface version 1)

This document describes Research Scanner Interface v1.5. The public plugin interface remains version 1. A plugin proposes **which symbols are interesting** from information available after signal day `t` closes. Scanner Research evaluates candidate quality without a portfolio. Strategy Backtest optionally converts selected candidates into simulated orders; the host controls fills, accounting, exits, costs, and result storage.

Start from `templates/strategy_plugin_template/` and deliver the completed directory as a ZIP. The ZIP must contain exactly one strategy directory with the files shown below. Use Python 3.11+, pandas, and the packages already installed by Stock Radar. Do not add runtime dependencies to a plugin.

## Directory and identity

```text
my_strategy/
├── manifest.yaml
├── strategy.yaml
├── strategy.py
├── README.md
└── tests/
    └── test_strategy.py
```

`manifest.yaml` is metadata and is validated by the host with Pydantic:

```yaml
name: My Pullback Strategy
id: my_pullback_strategy
version: 1.0.0
interface_version: 1
author:
  type: ai
  name: Codex
description: Finds liquid prior winners after a measured pullback.
required_features:
  - tradability_pass
  - ret_60
  - drawdown_20
tags:
  - pullback
  - research
```

`id` is a stable, unique, lowercase `snake_case` identifier. `version` identifies the plugin's logic and follows `MAJOR.MINOR.PATCH`. `interface_version` must be the integer `1`. `author.type` is provenance metadata (`human`, `ai`, or `other`); it grants no permissions. The manifest's `required_features` must match the features returned by the Python method of that name. Duplicate strategy IDs or unsupported interface versions are rejected.

`strategy.yaml` contains strategy thresholds and selection settings, for example:

```yaml
prior_strength:
  min_return_60: 0.15
pullback:
  min_depth: 0.08
  max_depth: 0.30
selection:
  max_candidates: 20  # null means all filtered candidates
evaluation:
  entry_reference: next_session_open
  horizon_sessions: 10
  upside_targets: [0.03, 0.05, 0.08, 0.10]
  downside_targets: [-0.03, -0.05, -0.08, -0.10]
  primary_target: 0.05
  primary_adverse_target: -0.05
  success_rule: target_touch
  top_k_values: [5, 10, 20]
  event_cooldown_sessions: 5
  false_falling_knife:
    enabled: true
    max_drawdown_threshold: -0.08
exit:
  take_profit: 0.05
  stop_loss: -0.10
  max_holding_sessions: 10
```

Change numerical thresholds by creating a new configuration and a **new Run**. Do not fork Python merely to change a threshold. A structural change to filtering, scoring, or selection requires a new plugin version. Past Run results are immutable.

## Exact Python interface

`strategy.py` must export one module-level object named `PLUGIN`. The host imports and validates it. The public types are `radar.strategy.base.StrategyPlugin` and `radar.strategy.context.StrategyContext`. Configuration is a read-only `Mapping[str, Any]` passed to every method.

```python
from typing import Any, Mapping
import pandas as pd
from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext

class MyStrategy(StrategyPlugin):
    def required_features(self) -> set[str]:
        ...

    def hard_filter(
        self, context: StrategyContext, config: Mapping[str, Any]
    ) -> pd.Series:
        ...

    def score(
        self, context: StrategyContext, config: Mapping[str, Any]
    ) -> pd.Series:
        ...

    def select(
        self, candidates: pd.DataFrame, config: Mapping[str, Any]
    ) -> pd.DataFrame:
        ...

PLUGIN = MyStrategy()
```

Contract:

1. `required_features()` returns the set of causal feature names read by the plugin. It must agree with `manifest.yaml`. `symbol`, `security_name`, and `close` are base columns and need not be declared as features.
2. `hard_filter()` returns a **boolean pandas Series** with exactly the same index and length as `context.frame`. `True` means a candidate remains eligible. Treat missing input values as ineligible; do not silently backfill them from future dates.
3. `score()` returns a **numeric pandas Series** with exactly the same index and length as `context.frame`. Larger values rank higher. Return finite scores for eligible rows. Score calculation may use only data in the context and config.
4. The host calls `select()` with a DataFrame containing eligible rows and a numeric `strategy_score` column. Return a DataFrame with a subset of those rows, in desired rank order, with at most `selection.max_candidates` rows when that value is an integer. `null` means no selection cap. Break score ties deterministically, normally by ascending `symbol`. Do not fabricate rows or mutate the input. Zero rows are valid. Scanner persists every filtered/scored row and marks the subset returned by `select()` with `selected`.
5. All four methods must be deterministic for the same inputs. They must not place orders, read the database, perform network requests, access files, or alter backtest state.

An optional `diagnostic_scores(context, config)` method may return an index-aligned DataFrame of finite numeric sub-scores, plus optional `p_*` probabilities bounded to `[0,1]`. Diagnostic names are generic snake_case and cannot be future-label names. They are persisted with candidate snapshots. The host calculates Brier score, log loss, and five probability calibration bins when a probability column exactly matches a configured target, e.g. `p_hit_5pct_10d`.

The host validates output shape, indices, booleans, numeric scores, selected symbols, and candidate limits. Invalid output prevents registration or a Run and produces a readable error. Stock Radar also excludes already-held symbols and applies its execution constraints outside the plugin.

## StrategyContext and allowed data

### Additive Research Infrastructure v1 history capability (Q2 v1.3)

An interface-v1 plugin may declare `data_backend: research_infrastructure_v1`
in `strategy.yaml`. Legacy configurations without this field retain their exact
previous data path and behavior. This declaration binds a new Backtest Run to
the frozen dated `shape_research_universe_v1` membership index, its semantic
hash and core database SHA-256. The host records these in Run metadata; it does
not use the current listing universe as a substitute. This adapter currently
supports the local LEAN Backtest path, not Scanner Research or Fresh OOS.

The opted-in plugin receives a `security_id` in `context.frame` and can ask the
host for a bounded, defensive OHLCV copy:

```python
bars = context.history(security_id, sessions=430)
```

The host checks the frozen 126-session dated membership window, selects only
that security's homogeneous historical series, and returns at most 430 exchange
sessions ending no later than `context.signal_date` (T). Missing, unsafe or
mixed-basis history is an explicit exclusion. The plugin never receives a
database connection or a filesystem path. `context.history()` is unavailable
to legacy plugins and does not change their context columns. The host also has
T-clipped, provenance-tagged SPY/QQQ benchmark access; Q2 v1.3's causal paired
SPY beta is supplied as `beta_spy_126`. Its `avg_dollar_volume_20` uses
split-adjusted SIP close times volume from the same historical source. The
`market_input_safe` flag is false when this evidence is incomplete.

The ZIP static inspection still rejects file, database, network and private
host imports. Static inspection is not an operating-system sandbox; import only
trusted plugin ZIPs. Execution, fees, slippage, maximum positions and the next
session Open remain host owned. Historical membership reconstruction reduces
survivorship bias but does not remove unknown identities or all coverage gaps.

For plugins without the research backend declaration, `StrategyContext` exposes only:

```python
context.signal_date  # pandas.Timestamp: date t, after the close
context.frame        # pandas.DataFrame: one row per symbol at date t
```

`context.frame` is supplied as a copy. Its base columns are `symbol`, `security_name`, and `close`, plus selected, causal feature columns that were computable from observations through `t` Close. It does **not** expose daily Open, DuckDB connections, the Alpaca client, `forward_labels`, later bars, future equity, or final Test metrics. Only a declared research backend can request the separate T-clipped raw history capability above. Some features are null while rolling windows warm up; use explicit null handling.

Examples of existing causal feature names (the available list is checked against the installed feature version):

| Group | Example features |
| --- | --- |
| Tradability and strength | `tradability_pass`, `elasticity_score`, `ret_20`, `ret_60`, `relative_strength_spy_20`, `relative_strength_qqq_20` |
| Trend and pullback | `drawdown_20`, `drawdown_60`, `pullback_days_20`, `dist_ma_5`, `dist_ma_20`, `rebound_from_low_5` |
| Exhaustion | `decline_speed_prev_3`, `decline_acceleration`, `red_body_avg_3`, `red_body_avg_5`, `range_contraction`, `volume_contraction` |
| Support and reversal | `failed_breakdown`, `support_reclaim`, `lower_wick_ratio`, `close_location`, `higher_low_proxy`, `reclaim_ma_5`, `new_low_frequency_5` |
| Volatility and liquidity | `atr_pct_20`, `realized_vol_20`, `avg_dollar_volume_20`, `body_pct` |
| Causal market context | `spy_trend`, `qqq_trend`, `spy_drawdown`, `qqq_drawdown`, `market_realized_volatility`, `market_breadth` |

Market context version `causal-market-v2-asof` is host-computed through signal day `t`: `spy_trend` and `qqq_trend` are close / trailing 20-session mean close − 1; drawdowns are close / trailing 60-session maximum close − 1; realized volatility is the trailing 20 SPY close-to-close return standard deviation × √252; breadth is the fraction of same-day tradable, non-null-feature symbols with `dist_ma_20 > 0`. Rolling windows have no future rows. Plugins receive only market fields declared in `required_features()`.

Declare every feature used in code in both places. If a feature such as `support_reclaim` is unavailable, the loader rejects the plugin with a missing-feature message. Do not compute a substitute from future data or bypass the context. To request a genuinely new causal feature, add it to the host feature pipeline as a separate, reviewed change.

**Prohibited future data:** `forward_labels`, `entry_open`, `return_close_1d`, `return_close_3d`, `return_close_5d`, `return_close_10d`, `mfe_high_5d`, `mae_low_5d`, any `t+1` bar, and any metric calculated from later trades or equity. Names in this list are examples, not the complete set. Future data must not influence signal day `t`.

## Scanner Research mode and labels

Scanner Research runs a plugin once per signal session over the host's tradable, feature-complete eligible market. It stores a structured candidate snapshot with `(signal_date, symbol, security_name, rank, strategy_score, selected)` plus the declared causal input features, arbitrary diagnostic sub-scores, probabilities, host market context, and host-generated labels. Each completed Run and its snapshots are protected by SQLite immutability triggers and SHA-256 artifact hashes over sorted, normalized saved rows and metrics. `RunStore.verify_scanner_artifacts(run_id)` recomputes these hashes, including the two early v1.5 formats. It opens no position and calculates no portfolio PnL.

Label version `scanner-forward-v2` uses **the next market trading session as session 1** and that session's Open as the reference price. The configured `horizon_sessions` is a count of market sessions, not calendar days. For horizon H, `mfe_H = max(high[1..H]) / entry_open − 1` and `mae_H = min(low[1..H]) / entry_open − 1`. Each configured `upside_targets` value X produces `hit_Xpct_Hd` when any future High reaches `entry_open × (1+X)`; `time_to_Xpct` is the first 1-based session to reach it. Each `downside_targets` value D produces `hit_minus_Dpct_Hd` and a first-session `time_to_minus_Dpct`. `new_low_after_signal` means a future Low is strictly below the signal-day Low. `false_falling_knife` means a new Low occurred and MAE is at or below its configured negative threshold; it is null if that diagnostic is disabled.

`primary_target` must be a member of `upside_targets`; `primary_adverse_target` must be a negative member of `downside_targets`. The defaults pair +5% with −5%. With `success_rule: target_touch`, the primary outcome is the primary upside touch. With `target_before_adverse`, it is the **explicit** primary upside threshold reached before the explicit adverse threshold. A same-session first touch of both has unknown intraday order; that pair's outcome is null and is excluded from primary Precision/Lift. Other excursion labels can remain available. High/Low excursions are research labels, not executable trade returns.

Observation `Precision@K` pools valid primary outcomes whose **original daily rank ≤ K** across signal dates. `Lift@K = Precision@K / base_rate`. The base rate is the fraction of valid primary successes among all host-tradable, required-feature-complete same-date symbols **before** the plugin's hard filter. It excludes censored or ambiguous primary outcomes and records labeled and censored counts. Event `Precision@K` first keeps raw daily rank ≤ K, then removes repeat signals for the same symbol (stable `security_id` in PIT mode) within `event_cooldown_sessions`; it does **not** refill Top-K after deduplication. Event `Lift@K` divides that event precision by the same observation base rate. `event_top_K_count` is the labeled event count after both steps. Average/median MFE and MAE, falling-knife rate, and target-hit rates use complete candidate labels. Market-regime success uses the configured primary outcome, grouped by the sign of causal `spy_trend`.

Each candidate snapshot stores `label_status` (`labeled` or `censored`) and `label_reason`. Censoring reasons include `insufficient_future_sessions`, `missing_symbol_bar`, `missing_price_data`, and, when a dated security master shows the interval ended, `security_no_longer_eligible`. A same-session ambiguous primary outcome is marked `ambiguous_same_session`. Candidate, background, and event labeled/censored counts and rates expose the excluded denominator. The plugin sees neither future OHLC nor forward labels; the host joins outcomes only after each signal day's selection. PIT membership and explicit censoring diagnostics do not replace a terminal-value or delisting-return policy; the system does not claim to be survivorship-bias-free.

## Strategy Backtest execution rules

The plugin runs after `t` Close. A selected symbol may be bought only at the **next valid trading session Open** in current Lab runs, subject to the engine's gap, cash, liquidity, and position limits. The portfolio engine still caps new positions (legacy default three), independently of Scanner's candidate count. Strategy-specific `exit` defines take profit, stop loss, and maximum holding sessions; each may be `null` to disable that automatic exit. Stock Radar still determines threshold triggers, gap handling, fees, slippage, and accounting. Legacy interface-v1 plugins without `exit` retain the historical host defaults, including the older `execution.stop_loss` override. The built-in Strategy2 config now explicitly states +5%, −10%, and 10 sessions; it still reproduces the saved legacy-close artifacts. A gap can produce a realized loss beyond the configured stop.

New research backtests default to `next_open`: a close-based exit condition executes at the next session's Open. `legacy_close` executes that exit at the same session's Close and remains available for historical compatibility; it does not mean entries occur at signal-day Close. Old metadata without an execution-timing field retains its historical fallback.

## Validation, testing, and trust

Before a plugin is registered, Stock Radar checks the directory, manifest, interface version, required features, imports, output contract, static code indicators, and plugin tests. Include tests for threshold boundaries, null values, deterministic tie breaking, the empty-candidate case, and no future-data access. Use the included template tests as a starting point.

Plugin Python is **research code, not an operating-system sandbox**. Static inspection can reject or warn about suspicious imports, including `subprocess`, `requests`, `alpaca`, and `socket`; `os`, `pathlib`, and `duckdb` require particular scrutiny. AST checks cannot prove code safe. Import only code you trust. Keep the strategy inside the public context instead of opening database connections, importing private engine modules, or making network calls. ZIP validation and plugin tests reduce mistakes but cannot make arbitrary Python harmless.

## Version and reproducibility requirements

Every Run records the strategy ID/version, interface version, exact config and hash, feature version, data snapshot, source revision, execution assumptions, date range, and results. A config edit creates a new Run and never overwrites a completed Run. Bump the plugin version whenever Python logic or the meaning of a config key changes. Keep `interface_version: 1` until the host publishes a new protocol. Test and final-period results are for evaluation; never optimize thresholds on an untouched final Test period.

## Minimal example

The template implements a complete example using `tradability_pass`, `ret_60`, and `drawdown_20`. Its `hard_filter` requires a strong 60-session return and a bounded pullback, its `score` ranks stronger prior returns, and its `select` returns up to the configured candidate count (20 by default). Replace the logic and metadata with the requested strategy, retaining the same API and causal-data restrictions.
