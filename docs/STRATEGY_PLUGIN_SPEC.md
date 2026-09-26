# Stock Radar Strategy Plugin Specification (interface version 1)

This document is sufficient to author a Stock Radar research strategy without editing the backtest engine. A plugin proposes **which symbols to buy** from information available after signal day `t` closes. Stock Radar controls orders, fills, portfolio accounting, exits, costs, and result storage.

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
  max_candidates: 3
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
4. The host calls `select()` with a DataFrame containing eligible rows and a numeric `strategy_score` column. Return a DataFrame with a subset of those rows, in desired rank order, with at most `selection.max_candidates` rows. Break score ties deterministically, normally by ascending `symbol`. Do not fabricate rows or mutate the input. Zero rows are valid.
5. All four methods must be deterministic for the same inputs. They must not place orders, read the database, perform network requests, access files, or alter backtest state.

The host validates output shape, indices, booleans, numeric scores, selected symbols, and candidate limits. Invalid output prevents registration or a Run and produces a readable error. Stock Radar also excludes already-held symbols and applies its execution constraints outside the plugin.

## StrategyContext and allowed data

`StrategyContext` exposes only:

```python
context.signal_date  # pandas.Timestamp: date t, after the close
context.frame        # pandas.DataFrame: one row per symbol at date t
```

`context.frame` is supplied as a copy. Its base columns are `symbol`, `security_name`, and `close`, plus selected, causal feature columns that were computable from observations through `t` Close. It does **not** expose daily Open or a raw price history, DuckDB connections, the Alpaca client, `forward_labels`, later bars, future equity, or final Test metrics. Some features are null while rolling windows warm up; use explicit null handling.

Examples of existing causal feature names (the available list is checked against the installed feature version):

| Group | Example features |
| --- | --- |
| Tradability and strength | `tradability_pass`, `elasticity_score`, `ret_20`, `ret_60`, `relative_strength_spy_20`, `relative_strength_qqq_20` |
| Trend and pullback | `drawdown_20`, `drawdown_60`, `pullback_days_20`, `dist_ma_5`, `dist_ma_20`, `rebound_from_low_5` |
| Exhaustion | `decline_speed_prev_3`, `decline_acceleration`, `red_body_avg_3`, `red_body_avg_5`, `range_contraction`, `volume_contraction` |
| Support and reversal | `failed_breakdown`, `support_reclaim`, `lower_wick_ratio`, `close_location`, `higher_low_proxy`, `reclaim_ma_5`, `new_low_frequency_5` |
| Volatility and liquidity | `atr_pct_20`, `realized_vol_20`, `avg_dollar_volume_20`, `body_pct` |

Declare every feature used in code in both places. If a feature such as `support_reclaim` is unavailable, the loader rejects the plugin with a missing-feature message. Do not compute a substitute from future data or bypass the context. To request a genuinely new causal feature, add it to the host feature pipeline as a separate, reviewed change.

**Prohibited future data:** `forward_labels`, `entry_open`, `return_close_1d`, `return_close_3d`, `return_close_5d`, `return_close_10d`, `mfe_high_5d`, `mae_low_5d`, any `t+1` bar, and any metric calculated from later trades or equity. Names in this list are examples, not the complete set. Future data must not influence signal day `t`.

## Execution rules owned by Stock Radar

The plugin runs after `t` Close. A selected symbol may be bought only at the **next valid trading session Open**, subject to the engine's gap, cash, liquidity, and position limits. The default policy allows at most three **new candidates per day**, no pyramiding, no leverage, and zero candidates. Existing holdings consume cash. Exits are determined by the engine: +5% take profit, −10% stop loss, or a maximum of 10 trading sessions, with Open/Close execution and actual Open price for a gap through a threshold. Fees and slippage apply. A plugin cannot alter these through `strategy.yaml` or its return values. A future, explicitly versioned Execution Policy API would be required to change them.

## Validation, testing, and trust

Before a plugin is registered, Stock Radar checks the directory, manifest, interface version, required features, imports, output contract, static code indicators, and plugin tests. Include tests for threshold boundaries, null values, deterministic tie breaking, the empty-candidate case, and no future-data access. Use the included template tests as a starting point.

Plugin Python is **research code, not an operating-system sandbox**. Static inspection can reject or warn about suspicious imports, including `subprocess`, `requests`, `alpaca`, and `socket`; `os`, `pathlib`, and `duckdb` require particular scrutiny. AST checks cannot prove code safe. Import only code you trust. Keep the strategy inside the public context instead of opening database connections, importing private engine modules, or making network calls. ZIP validation and plugin tests reduce mistakes but cannot make arbitrary Python harmless.

## Version and reproducibility requirements

Every Run records the strategy ID/version, interface version, exact config and hash, feature version, data snapshot, source revision, execution assumptions, date range, and results. A config edit creates a new Run and never overwrites a completed Run. Bump the plugin version whenever Python logic or the meaning of a config key changes. Keep `interface_version: 1` until the host publishes a new protocol. Test and final-period results are for evaluation; never optimize thresholds on an untouched final Test period.

## Minimal example

The template implements a complete example using `tradability_pass`, `ret_60`, and `drawdown_20`. Its `hard_filter` requires a strong 60-session return and a bounded pullback, its `score` ranks stronger prior returns, and its `select` returns up to three names. Replace the logic and metadata with the requested strategy, retaining the same API and causal-data restrictions.
