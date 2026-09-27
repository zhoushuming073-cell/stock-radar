"""Resolve strategy-owned exits while preserving old interface-v1 runs."""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping


def stop_loss_for_run(default: float, strategy_config: Mapping[str, Any]) -> float:
    """Return the engine stop loss, optionally overridden for one Run.

    Only ``execution.stop_loss`` is supported. Plugins still cannot place orders
    or change the other portfolio and exit rules.
    """
    execution = strategy_config.get("execution")
    if execution is None:
        return float(default)
    if not isinstance(execution, Mapping) or set(execution) != {"stop_loss"}:
        raise ValueError("execution may contain only stop_loss")
    value = execution["stop_loss"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("execution.stop_loss must be a number between -1 and 0")
    stop_loss = float(value)
    if not isfinite(stop_loss) or not -1 < stop_loss < 0:
        raise ValueError("execution.stop_loss must be a number between -1 and 0")
    return stop_loss


def resolve_exit_policy(defaults: Mapping[str, Any],
                        strategy_config: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """Return host-executed exits and their source for immutable Run metadata.

    ``exit`` is the current strategy configuration. The older
    ``execution.stop_loss`` and host defaults remain only for v1 compatibility.
    """
    keys = ("take_profit", "stop_loss", "max_holding_sessions")
    values = {key: defaults[key] for key in keys if key in defaults}
    if "exit" in strategy_config:
        exit_config = strategy_config["exit"]
        if not isinstance(exit_config, Mapping) or set(exit_config) != set(keys):
            raise ValueError("exit must define take_profit, stop_loss and max_holding_sessions")
        if "execution" in strategy_config:
            raise ValueError("use exit or legacy execution, not both")
        values = {key: exit_config[key] for key in keys}
        source = "strategy_exit"
    elif "execution" in strategy_config:
        values["stop_loss"] = stop_loss_for_run(float(defaults["stop_loss"]), strategy_config)
        source = "legacy_execution_override"
    else:
        source = "legacy_host_default"
    if source == "legacy_host_default":
        return values, source
    for key in ("take_profit", "stop_loss"):
        if key not in values:
            continue
        value = values[key]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise ValueError(f"exit.{key} must be a finite number or null")
        value = float(value)
        if key == "take_profit" and value <= 0:
            raise ValueError("exit.take_profit must be positive or null")
        if key == "stop_loss" and not -1 < value < 0:
            raise ValueError("exit.stop_loss must be between -1 and 0 or null")
        values[key] = value
    hold = values.get("max_holding_sessions")
    if hold is not None and (isinstance(hold, bool) or not isinstance(hold, int) or hold < 1):
        raise ValueError("exit.max_holding_sessions must be a positive integer or null")
    return values, source
