"""Explicit semantic controls for the v1 research UI.

Plugin configuration is never converted into controls merely because a YAML
value happens to be a scalar. Unknown v1 plugin fields remain visible in Audit.
"""

from __future__ import annotations

from typing import Any, Mapping


def _field(path: str, label: str, description: str, kind: str,
           level: str, modes: list[str], *, unit: str = "", minimum: float | None = None,
           maximum: float | None = None, step: float | None = None,
           nullable: bool = False, searchable: bool = True) -> dict[str, Any]:
    return {"path": path, "label": label, "description": description,
            "namespace": path.split(".")[0], "type": kind, "unit": unit,
            "min": minimum, "max": maximum, "step": step, "nullable": nullable,
            "level": level, "modes": modes, "searchable": searchable}


_BOTH = ["scanner", "backtest"]
_SCANNER = ["scanner"]
_BACKTEST = ["backtest"]
STRATEGY2_FIELDS = [
    _field("strategy.min_elasticity", "Minimum elasticity", "Minimum historical elasticity score.", "number", "core", _BOTH, minimum=0, maximum=100, step=1),
    _field("strategy.min_pullback", "Minimum pullback", "Minimum decline from a recent high.", "percentage", "core", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.max_pullback", "Maximum pullback", "Maximum decline from a recent high.", "percentage", "core", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.min_prior_peak_gain", "Prior peak gain", "Minimum gain before the pullback.", "percentage", "advanced", _BOTH, unit="fraction", minimum=0, maximum=5, step=.01),
    _field("strategy.max_new_low_frequency_5", "New-low frequency", "Maximum recent new-low frequency.", "percentage", "advanced", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.max_rebound_from_5d_low", "Rebound limit", "Maximum rebound from the five-day low.", "percentage", "advanced", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.max_one_day_return", "One-day return limit", "Maximum prior one-day rise.", "percentage", "advanced", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.max_distance_from_ma5", "MA5 distance limit", "Maximum distance above the five-day average.", "percentage", "advanced", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.min_close_location", "Close location", "Required close position within the daily range.", "percentage", "advanced", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.min_wick_ratio", "Wick ratio", "Minimum lower wick share.", "percentage", "advanced", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.max_volume_contraction", "Volume contraction", "Maximum volume contraction threshold.", "percentage", "advanced", _BOTH, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("strategy.exclude_explicit_funds", "Exclude named funds", "Reject explicitly named ETF/ETN securities.", "boolean", "advanced", _BOTH),
    _field("strategy.selection.max_candidates", "Strategy candidate cap", "Optional strategy output cap; blank keeps every eligible candidate.", "integer", "advanced", _BOTH, minimum=1, maximum=10000, step=1, nullable=True),
    _field("evaluation.horizon_sessions", "Outcome horizon", "Trading sessions after the signal used for forward labels.", "integer", "core", _SCANNER, unit="sessions", minimum=1, maximum=60, step=1),
    _field("evaluation.primary_target", "Primary upside target", "Target used for Scanner hit rate.", "percentage", "core", _SCANNER, unit="fraction", minimum=.01, maximum=.99, step=.01),
    _field("evaluation.primary_adverse_target", "Primary adverse target", "Downside threshold paired with the primary upside target when success_rule is target_before_adverse.", "percentage", "core", _SCANNER, unit="fraction", minimum=-.999, maximum=-.001),
    _field("evaluation.top_k_values", "Evaluation Top-K", "Ranks used for precision and lift; does not truncate candidates.", "integer_list", "core", _SCANNER),
    _field("evaluation.upside_targets", "Upside targets", "Forward upside thresholds; include the primary target.", "number_list", "advanced", _SCANNER, unit="fractions"),
    _field("evaluation.downside_targets", "Downside targets", "Adverse forward thresholds for order research.", "number_list", "advanced", _SCANNER, unit="fractions"),
    _field("evaluation.event_cooldown_sessions", "Event cooldown", "Sessions separating repeat signals for the same symbol.", "integer", "advanced", _SCANNER, unit="sessions", minimum=0, maximum=60, step=1),
    _field("evaluation.success_rule", "Success rule", "How Scanner counts a successful candidate.", "choice", "advanced", _SCANNER),
    _field("evaluation.false_falling_knife.enabled", "Falling-knife label", "Enable the adverse new-low label.", "boolean", "advanced", _SCANNER),
    _field("evaluation.false_falling_knife.max_drawdown_threshold", "Falling-knife drawdown", "Maximum adverse move counted as a falling knife.", "percentage", "advanced", _SCANNER, unit="fraction", minimum=-.999, maximum=-.001, step=.01),
    _field("execution.max_new_positions_per_day", "Daily position intake", "Maximum new backtest positions opened each session.", "integer", "core", _BACKTEST, minimum=0, maximum=100, step=1),
    _field("execution.slippage_bps", "Slippage", "Slippage charged per simulated fill.", "number", "core", _BACKTEST, unit="bps", minimum=0, maximum=100, step=1),
    _field("execution.exit.take_profit", "Take profit", "Host-executed profit exit; blank disables it.", "percentage", "core", _BACKTEST, unit="fraction", minimum=.001, maximum=10, step=.01, nullable=True),
    _field("execution.exit.stop_loss", "Stop loss", "Host-executed loss exit; blank disables it.", "percentage", "core", _BACKTEST, unit="fraction", minimum=-.999, maximum=-.001, step=.01, nullable=True),
    _field("execution.exit.max_holding_sessions", "Max holding", "Host-executed time exit; blank disables it.", "integer", "core", _BACKTEST, unit="sessions", minimum=1, maximum=10000, step=1, nullable=True),
    _field("execution.initial_capital", "Initial capital", "Starting simulated cash.", "number", "advanced", _BACKTEST, unit="USD", minimum=1, step=1000),
    _field("execution.sizing.method", "Allocator", "Cash allocation among new positions.", "choice", "advanced", _BACKTEST),
    _field("execution.sizing.max_position_fraction", "Max position share", "Maximum portfolio share per position.", "percentage", "advanced", _BACKTEST, unit="fraction", minimum=.001, maximum=1, step=.01),
    _field("execution.sizing.min_position_fraction", "Min position share", "Minimum portfolio share required to open.", "percentage", "advanced", _BACKTEST, unit="fraction", minimum=0, maximum=1, step=.01),
    _field("execution.liquidity.max_adv_participation", "ADV participation", "Maximum share of average daily dollar volume; must be greater than zero.", "percentage", "advanced", _BACKTEST, unit="fraction", minimum=.000001, maximum=1),
    _field("execution.market_guard.mode", "Market guard", "Optional SPY 200-session moving-average gate.", "choice", "advanced", _BACKTEST),
    _field("execution.execution_timing", "Exit fill timing", "Next open: close-based exit condition executes at next-session Open. Legacy close: close-based exit executes at same-session Close.", "choice", "advanced", _BACKTEST),
    _field("execution.entry_gap.enabled", "Entry gap gate", "Enable the next-open gap filter.", "boolean", "advanced", _BACKTEST),
    _field("execution.entry_gap.min", "Minimum entry gap", "Lowest allowed open gap versus prior close.", "percentage", "advanced", _BACKTEST, unit="fraction", minimum=-1, maximum=1, step=.01),
    _field("execution.entry_gap.max", "Maximum entry gap", "Highest allowed open gap versus prior close.", "percentage", "advanced", _BACKTEST, unit="fraction", minimum=-1, maximum=1, step=.01),
]


def parameter_schema(strategy_id: str, strategy_defaults: Mapping[str, Any],
                     evaluation_defaults: Mapping[str, Any],
                     execution_defaults: Mapping[str, Any]) -> list[dict[str, Any]]:
    if strategy_id != "full_strategy2_v1":
        return []
    values = {"strategy": strategy_defaults, "evaluation": evaluation_defaults,
              "execution": execution_defaults}
    output = []
    for spec in STRATEGY2_FIELDS:
        item = dict(spec)
        current: Any = values
        for part in item["path"].split("."):
            current = current.get(part) if isinstance(current, Mapping) else None
        item["default"] = current
        output.append(item)
    return output
