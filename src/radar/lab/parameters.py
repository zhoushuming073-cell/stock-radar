"""Canonical, immutable research configuration for newly queued runs.

Legacy metadata remains readable; this module does not reinterpret old runs.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from typing import Any, Mapping


NAMESPACES = frozenset({"strategy", "evaluation", "execution", "dataset", "view"})
RESEARCH_NAMESPACES = ("strategy", "evaluation", "execution", "dataset")
SOURCE_NAMES = frozenset({"host_default", "strategy_default", "run_override"})
UNIVERSE_MODES = frozenset({"current_snapshot", "point_in_time", "research_infrastructure_v1"})


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def leaves(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, Mapping):
            result.update(leaves(item, path))
        else:
            result[path] = item
    return result


def research_hash(value: Mapping[str, Any]) -> str:
    """Hash only result-changing namespaces, regardless of view state."""
    unknown = set(value) - NAMESPACES
    if unknown:
        raise ValueError(f"unknown research namespaces: {sorted(unknown)}")
    encoded = json.dumps(
        {key: plain(value.get(key, {})) for key in RESEARCH_NAMESPACES},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ResolvedRunConfig:
    values: dict[str, Any]
    sources: dict[str, str]
    hash: str

    def __post_init__(self) -> None:
        if set(self.values) != set(RESEARCH_NAMESPACES):
            raise ValueError("resolved config requires strategy/evaluation/execution/dataset")
        actual = set(leaves(self.values))
        if set(self.sources) != actual or set(self.sources.values()) - SOURCE_NAMES:
            raise ValueError("each resolved leaf must have one valid source")
        if self.hash != research_hash(self.values):
            raise ValueError("resolved config hash mismatch")

    def metadata(self) -> dict[str, Any]:
        return {"values": deepcopy(self.values), "sources": dict(self.sources),
                "hash": self.hash}


def _merge(base: dict[str, Any], updates: Mapping[str, Any], sources: dict[str, str],
           prefix: str, source: str) -> None:
    for key, item in updates.items():
        path = f"{prefix}.{key}"
        if isinstance(item, Mapping):
            old = base.get(key)
            if old is not None and not isinstance(old, dict):
                raise ValueError(f"cannot merge object into scalar {path}")
            nested = base.setdefault(key, {})
            _merge(nested, item, sources, path, source)
        else:
            base[key] = plain(item)
            sources[path] = source


def resolve_config(*, strategy_defaults: Mapping[str, Any],
                   strategy_draft: Mapping[str, Any] | None,
                   evaluation_defaults: Mapping[str, Any],
                   execution_defaults: Mapping[str, Any],
                   dataset: Mapping[str, Any],
                   evaluation_overrides: Mapping[str, Any] | None = None,
                   execution_overrides: Mapping[str, Any] | None = None) -> ResolvedRunConfig:
    """Resolve host defaults -> strategy defaults -> run overrides.

    Strategy drafts are full copies in the v1 UI. Only changed leaves are marked
    as run overrides. Legacy strategy-owned evaluation and exits are moved to
    their canonical namespaces without changing the plugin's v1 input shape.
    """
    defaults = plain(strategy_defaults)
    draft = plain(strategy_draft if strategy_draft is not None else strategy_defaults)
    if not isinstance(defaults, dict) or not isinstance(draft, dict):
        raise ValueError("strategy configuration must be an object")
    if set(leaves(draft)) - set(leaves(defaults)):
        # The one v1 exception is a legacy stop-loss override.
        extras = set(leaves(draft)) - set(leaves(defaults))
        if extras - {"execution.stop_loss", "selection.max_candidates"}:
            raise ValueError(f"unknown strategy override paths: {sorted(extras)}")
    values: dict[str, Any] = {key: {} for key in RESEARCH_NAMESPACES}
    sources: dict[str, str] = {}
    strategy_keys = {"evaluation", "exit", "execution", "max_new"}
    strategy_base = {key: item for key, item in defaults.items() if key not in strategy_keys}
    strategy_current = {key: item for key, item in draft.items() if key not in strategy_keys}
    _merge(values["strategy"], strategy_base, sources, "strategy", "strategy_default")
    for path, item in leaves(strategy_current).items():
        if path not in leaves(strategy_base) or item != leaves(strategy_base)[path]:
            _set_path(values["strategy"], path, item)
            sources[f"strategy.{path}"] = "run_override"
    _merge(values["evaluation"], plain(evaluation_defaults), sources,
           "evaluation", "host_default")
    if isinstance(defaults.get("evaluation"), Mapping):
        _merge(values["evaluation"], defaults["evaluation"], sources,
               "evaluation", "strategy_default")
    if isinstance(draft.get("evaluation"), Mapping):
        _changed_merge(values["evaluation"], defaults.get("evaluation", {}),
                       draft["evaluation"], sources, "evaluation")
    if evaluation_overrides:
        _merge(values["evaluation"], evaluation_overrides, sources,
               "evaluation", "run_override")
    _merge(values["execution"], plain(execution_defaults), sources,
           "execution", "host_default")
    for owner, config in (("strategy_default", defaults), ("run_override", draft)):
        if isinstance(config.get("exit"), Mapping):
            if owner == "strategy_default":
                _merge(values["execution"], {"exit": config["exit"]}, sources,
                       "execution", owner)
            else:
                _changed_merge(values["execution"], {"exit": defaults.get("exit", {})},
                               {"exit": config["exit"]}, sources, "execution")
        elif isinstance(config.get("execution"), Mapping) and "stop_loss" in config["execution"]:
            stop = config["execution"]["stop_loss"]
            if owner == "strategy_default" or stop != (
                    defaults.get("execution") or {}).get("stop_loss"):
                _merge(values["execution"], {"exit": {"stop_loss": stop}}, sources,
                       "execution", owner)
    if "max_new" in defaults:
        _merge(values["execution"], {"max_new_positions_per_day": defaults["max_new"]},
               sources, "execution", "strategy_default")
    if "max_new" in draft and draft["max_new"] != defaults.get("max_new"):
        _merge(values["execution"], {"max_new_positions_per_day": draft["max_new"]},
               sources, "execution", "run_override")
    if execution_overrides:
        _merge(values["execution"], execution_overrides, sources,
               "execution", "run_override")
    _merge(values["dataset"], plain(dataset), sources, "dataset", "run_override")
    mode = values["dataset"].get("universe_mode", "current_snapshot")
    if mode not in UNIVERSE_MODES:
        raise ValueError(f"unknown universe mode: {mode}")
    if mode == "point_in_time" and not values["dataset"].get("universe_fingerprint"):
        raise ValueError("point_in_time requires a verified security-master fingerprint")
    return ResolvedRunConfig(values, sources, research_hash(values))


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = plain(value)


def _changed_merge(target: dict[str, Any], defaults: Mapping[str, Any],
                   draft: Mapping[str, Any], sources: dict[str, str],
                   prefix: str) -> None:
    before = leaves(defaults)
    for path, item in leaves(draft).items():
        if path not in before or item != before[path]:
            _set_path(target, path, item)
            sources[f"{prefix}.{path}"] = "run_override"


def execution_defaults_from_legacy(raw: Mapping[str, Any], *,
                                   slippage_bps: float,
                                   execution_timing: str) -> dict[str, Any]:
    """Translate the existing host YAML without silently choosing an allocator."""
    source = dict(raw)
    result = {
        "initial_capital": source.get("initial_capital", 1_000_000.0),
        "max_new_positions_per_day": source.get("max_new_candidates", 3),
        "entry_gap": {"enabled": True, "min": source.get("entry_gap_min", -0.10),
                      "max": source.get("entry_gap_max", 0.05)},
        "sizing": {
            "method": source.get("allocator", "equal_cash"),
            "max_position_fraction": source.get("max_position_fraction", 1 / 3),
            "min_position_fraction": source.get("minimum_position_fraction", 0.01),
        },
        "liquidity": {"max_adv_participation":
                      source.get("max_order_to_avg_dollar_volume", 0.02)},
        "slippage_bps": float(slippage_bps),
        "market_guard": {"mode": source.get("market_guard", "none")},
        "execution_timing": execution_timing,
        "exit": {
            "take_profit": source.get("take_profit", 0.05),
            "stop_loss": source.get("stop_loss", -0.10),
            "max_holding_sessions": source.get("max_holding_sessions", 10),
        },
    }
    validate_execution(result)
    return result


def validate_execution(value: Mapping[str, Any]) -> None:
    """Catch impossible run overrides before a run is persisted."""
    allowed = {"initial_capital", "max_new_positions_per_day", "entry_gap",
               "sizing", "liquidity", "slippage_bps", "market_guard",
               "execution_timing", "exit"}
    if set(value) - allowed:
        raise ValueError(f"unknown execution fields: {sorted(set(value) - allowed)}")
    nested = {"entry_gap": {"enabled", "min", "max"},
              "sizing": {"method", "max_position_fraction", "min_position_fraction"},
              "liquidity": {"max_adv_participation"},
              "market_guard": {"mode"},
              "exit": {"take_profit", "stop_loss", "max_holding_sessions"}}
    for key, fields in nested.items():
        section = value.get(key)
        if not isinstance(section, Mapping) or set(section) != fields:
            raise ValueError(f"execution.{key} requires exactly {sorted(fields)}")
    cap = value["max_new_positions_per_day"]
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        raise ValueError("execution.max_new_positions_per_day must be non-negative")
    capital = value["initial_capital"]
    if isinstance(capital, bool) or not isinstance(capital, (int, float)) or (
            not isfinite(capital) or capital <= 0):
        raise ValueError("execution.initial_capital must be positive")
    if value["sizing"]["method"] not in (
            "equal_cash", "strategy_score", "strategy_times_elasticity"):
        raise ValueError("unknown execution.sizing.method")
    if value["market_guard"]["mode"] not in ("none", "spy_ma200"):
        raise ValueError("unknown execution.market_guard.mode")
    if value["execution_timing"] not in ("next_open", "legacy_close"):
        raise ValueError("unknown execution.execution_timing")
    gap = value["entry_gap"]
    if not isinstance(gap["enabled"], bool):
        raise ValueError("execution.entry_gap.enabled must be boolean")
    for key in ("min", "max"):
        item = gap[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(item):
            raise ValueError(f"execution.entry_gap.{key} must be finite")
    if value["entry_gap"]["enabled"] and (
            value["entry_gap"]["min"] >= value["entry_gap"]["max"]):
        raise ValueError("invalid execution.entry_gap bounds")
    sizing = value["sizing"]
    maximum, minimum = sizing["max_position_fraction"], sizing["min_position_fraction"]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x)
           for x in (maximum, minimum)) or not 0 < maximum <= 1 or not 0 <= minimum <= maximum:
        raise ValueError("invalid execution.sizing position fractions")
    participation = value["liquidity"]["max_adv_participation"]
    if (isinstance(participation, bool) or not isinstance(participation, (int, float)) or
            not isfinite(participation) or not 0 < participation <= 1):
        raise ValueError("invalid execution.liquidity.max_adv_participation")
    slip = value["slippage_bps"]
    if isinstance(slip, bool) or not isinstance(slip, (int, float)) or not isfinite(slip) or not 0 <= slip <= 100:
        raise ValueError("execution.slippage_bps must be between 0 and 100")
    for key in ("take_profit", "stop_loss"):
        item = value["exit"][key]
        if item is None:
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(item):
            raise ValueError(f"execution.exit.{key} must be finite or null")
        if key == "take_profit" and item <= 0:
            raise ValueError("take profit must be positive")
        if key == "stop_loss" and not -1 < item < 0:
            raise ValueError("execution.stop_loss / execution.exit.stop_loss must be between -1 and 0")
    hold = value["exit"]["max_holding_sessions"]
    if hold is not None and (isinstance(hold, bool) or not isinstance(hold, int) or hold < 1):
        raise ValueError("max holding sessions must be positive or null")


def engine_legacy_fields(value: Mapping[str, Any]) -> dict[str, Any]:
    """Pass the resolved execution policy to the unchanged backtest engine."""
    validate_execution(value)
    gap = value["entry_gap"]
    return {
        "initial_capital": value["initial_capital"],
        "max_new_candidates": value["max_new_positions_per_day"],
        "take_profit": value["exit"]["take_profit"],
        "stop_loss": value["exit"]["stop_loss"],
        "max_holding_sessions": value["exit"]["max_holding_sessions"],
        "entry_gap_min": gap["min"] if gap["enabled"] else -float("inf"),
        "entry_gap_max": gap["max"] if gap["enabled"] else float("inf"),
        "max_position_fraction": value["sizing"]["max_position_fraction"],
        "minimum_position_fraction": value["sizing"]["min_position_fraction"],
        "max_order_to_avg_dollar_volume": value["liquidity"]["max_adv_participation"],
        "slippage_bps": value["slippage_bps"],
        "allocator": value["sizing"]["method"],
        "market_guard": value["market_guard"]["mode"],
        "execution_timing": value["execution_timing"],
    }
