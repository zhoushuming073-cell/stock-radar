# Example Measured Pullback

This is a complete example for Stock Radar Strategy Plugin interface version 1. Replace its `id`, name, description, author, thresholds, and selection logic before importing it as your own strategy.

## What it does

After each trading session closes, the strategy keeps tradable symbols that gained at least 15% over 60 sessions and are now 8%–30% below their 20-session high. It ranks the remaining symbols by 60-session return and proposes at most three new candidates. The Stock Radar engine decides whether those candidates can be bought at the next session Open and manages all exits.

## Files

- `manifest.yaml`: strategy identity, version, author, required causal features.
- `strategy.yaml`: editable thresholds. Changing a threshold creates a new Run; it does not require a new Python file.
- `strategy.py`: exports `PLUGIN` and implements the four-method strategy contract.
- `tests/test_strategy.py`: examples covering eligibility, nulls, ranking, and determinism.

## Interface and available data

`strategy.py` exports `PLUGIN`. It must implement `required_features() -> set[str]`, `hard_filter(context, config) -> pd.Series[bool]`, `score(context, config) -> pd.Series[number]`, and `select(candidates, config) -> pd.DataFrame`. Filter and score results must align exactly with `context.frame.index`; `select` sees only eligible rows with a `strategy_score` column and returns a sorted subset. `config` is a read-only `Mapping[str, Any]` loaded from `strategy.yaml`.

Plugin code receives only `context.signal_date` and a copy of `context.frame` for signal date `t`. Base columns are `symbol`, `security_name`, and `close`. Existing causal feature examples include `tradability_pass`, `elasticity_score`, `ret_60`, `drawdown_20`, `pullback_days_20`, `decline_acceleration`, `support_reclaim`, `reclaim_ma_5`, and `avg_dollar_volume_20`. Declare every feature you read in both `manifest.yaml` and `required_features()`. The host checks availability before running.

Never read `forward_labels`, next-session Open, future returns, later bars, later equity, files, networks, or backtest internals. The plugin proposes candidates only. The engine owns next-session Open entry, gaps, cash, fills, fees, slippage, and exits. The exact contract, full safety notes, and more feature examples are in `docs/STRATEGY_PLUGIN_SPEC.md` in the Stock Radar repository.

Keep `interface_version: 1`. Bump `version` when Python logic or parameter meaning changes. Change a numeric threshold in `strategy.yaml` for a new immutable Run without copying the Python implementation. An AI author can use this directory as the structure for a new strategy ZIP.

To run the template tests from this directory in a Stock Radar Python environment:

```text
python -m pytest tests/test_strategy.py
```

Package this directory as one ZIP for import. Do not put passwords, tokens, datasets, or generated result files in the ZIP.
