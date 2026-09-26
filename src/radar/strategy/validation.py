"""Manifest, source and runtime contract checks for strategy plugins.

Static checks are error prevention, not an operating-system sandbox. Python
plugins and their tests execute with the host user's permissions.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Literal, Mapping

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_BASE_COLUMNS = frozenset({"symbol", "security_name", "close"})
_FUTURE_COLUMNS = frozenset({
    "forward_labels", "entry_open", "return_close_1d", "return_close_3d",
    "return_close_5d", "return_close_10d", "mfe_high_5d", "mae_low_5d",
})
_RAW_BAR_COLUMNS = frozenset({
    "open", "high", "low", "volume", "vwap", "trade_count",
})
_BANNED_IMPORT_ROOTS = frozenset({
    "os", "sys", "pathlib", "subprocess", "socket", "requests", "httpx",
    "urllib", "alpaca", "duckdb", "sqlite3", "importlib", "runpy",
    "shutil", "ctypes", "pickle", "shelve", "multiprocessing", "threading",
    "asyncio", "ftplib", "smtplib", "builtins",
})
_BANNED_CALLS = frozenset({"open", "exec", "eval", "compile", "__import__", "input"})
_BANNED_METHODS = frozenset({
    "read_csv", "read_parquet", "read_sql", "read_pickle", "read_json",
    "to_csv", "to_parquet", "to_sql", "to_pickle", "read_text",
    "read_bytes", "write_text", "write_bytes", "connect", "request",
    "get_stock_bars", "get_all_assets",
})
_ALLOWED_RADAR_IMPORTS = frozenset({
    "radar.strategy.base", "radar.strategy.context",
    "radar.strategy.full_strategy2",
})


class StrategyValidationError(ValueError):
    """A plugin failed a host-enforced contract check."""


class StrategyAuthor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["human", "ai", "other"]
    name: str = Field(min_length=1)


class StrategyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    id: str
    version: str
    interface_version: Literal[1]
    author: StrategyAuthor
    description: str = Field(min_length=1)
    required_features: tuple[str, ...]
    tags: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("id must be lowercase snake_case")
        return value

    @field_validator("version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if not _SEMVER.fullmatch(value):
            raise ValueError("version must be MAJOR.MINOR.PATCH")
        return value

    @field_validator("required_features")
    @classmethod
    def valid_features(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("required_features contains duplicates")
        for value in values:
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"invalid feature name: {value!r}")
            if value in _BASE_COLUMNS or value in _RAW_BAR_COLUMNS or is_future_feature(value):
                raise ValueError(f"base or prohibited data is not a required feature: {value}")
        return values

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("tags contains duplicates")
        return values


def is_future_feature(name: str) -> bool:
    return (
        name in _FUTURE_COLUMNS
        or name.startswith(("forward_", "future_", "entry_", "mfe_", "mae_"))
        or name.startswith("return_close_")
    )


def validate_available_features(
    manifest: StrategyManifest, available_features: set[str] | frozenset[str]
) -> None:
    missing = set(manifest.required_features) - set(available_features)
    if missing:
        raise StrategyValidationError(
            f"{manifest.id}: unavailable required_features: {', '.join(sorted(missing))}"
        )


def validate_plugin_identity(plugin: object, manifest: StrategyManifest) -> StrategyPlugin:
    if not isinstance(plugin, StrategyPlugin):
        raise StrategyValidationError("strategy.py PLUGIN must be a StrategyPlugin instance")
    actual = plugin.required_features()
    if not isinstance(actual, set) or not all(isinstance(x, str) for x in actual):
        raise StrategyValidationError("required_features() must return set[str]")
    if actual != set(manifest.required_features):
        raise StrategyValidationError(
            f"{manifest.id}: required_features() differs from manifest: "
            f"method={sorted(actual)}, manifest={sorted(manifest.required_features)}"
        )
    return plugin


def inspect_plugin_source(path: Path) -> None:
    """Reject known dangerous source indicators before any plugin import/test."""
    for source in (path / "strategy.py", path / "tests" / "test_strategy.py"):
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise StrategyValidationError(f"cannot parse {source.name}: {exc}") from exc
        issues: list[str] = []
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
                if node.level:
                    issues.append(f"line {node.lineno}: relative import")
            for module in modules:
                root = module.split(".", 1)[0]
                if root in _BANNED_IMPORT_ROOTS:
                    issues.append(f"line {node.lineno}: import {module}")
                if root == "radar" and module not in _ALLOWED_RADAR_IMPORTS:
                    issues.append(f"line {node.lineno}: private host import {module}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in _BANNED_CALLS:
                    issues.append(f"line {node.lineno}: call {node.func.id}()")
                if isinstance(node.func, ast.Attribute) and node.func.attr in _BANNED_METHODS:
                    issues.append(f"line {node.lineno}: call .{node.func.attr}()")
            if isinstance(node, ast.Attribute) and node.attr in {
                "__dict__", "__class__", "__globals__", "__subclasses__", "_frame"
            }:
                issues.append(f"line {node.lineno}: introspection {node.attr}")
        if issues:
            raise StrategyValidationError(
                f"{source.name} failed static inspection: {'; '.join(issues)}. "
                "Static inspection is not an OS sandbox."
            )


def validate_plugin_outputs(
    plugin: StrategyPlugin,
    context: StrategyContext,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Run a plugin against a real signal-day frame and verify its outputs."""
    frame = context.frame
    missing_base = _BASE_COLUMNS - set(frame.columns)
    if missing_base:
        raise StrategyValidationError(
            f"context missing base columns: {', '.join(sorted(missing_base))}"
        )
    if not frame.index.is_unique or "symbol" not in frame or frame["symbol"].duplicated().any():
        raise StrategyValidationError("context must have unique index and symbols")
    if any(is_future_feature(str(column)) or column in _RAW_BAR_COLUMNS for column in frame.columns):
        raise StrategyValidationError("context contains future or raw-bar columns")
    missing = plugin.required_features() - set(frame.columns)
    if missing:
        raise StrategyValidationError(f"context missing features: {', '.join(sorted(missing))}")

    eligible = plugin.hard_filter(context, config)
    scores = plugin.score(context, config)
    if not isinstance(eligible, pd.Series) or not eligible.index.equals(frame.index):
        raise StrategyValidationError("hard_filter must return a Series aligned to context.frame")
    if not pd.api.types.is_bool_dtype(eligible.dtype) or eligible.isna().any():
        raise StrategyValidationError("hard_filter must return non-null booleans")
    if not isinstance(scores, pd.Series) or not scores.index.equals(frame.index):
        raise StrategyValidationError("score must return a Series aligned to context.frame")
    if pd.api.types.is_bool_dtype(scores.dtype) or not pd.api.types.is_numeric_dtype(scores.dtype):
        raise StrategyValidationError("score must return numeric values")
    try:
        eligible_scores = scores.loc[eligible].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise StrategyValidationError("eligible scores must be numeric") from exc
    if not np.isfinite(eligible_scores).all():
        raise StrategyValidationError("eligible scores must be finite")

    candidates = frame.loc[eligible].copy(deep=True)
    candidates["strategy_score"] = scores.loc[eligible]
    original = candidates.copy(deep=True)
    selected = plugin.select(candidates, config)
    try:
        pd.testing.assert_frame_equal(candidates, original, check_like=False)
    except AssertionError as exc:
        raise StrategyValidationError("select mutated its candidate input") from exc
    if not isinstance(selected, pd.DataFrame):
        raise StrategyValidationError("select must return a DataFrame")
    if not selected.index.is_unique or not selected.index.isin(original.index).all():
        raise StrategyValidationError("select must return a subset of candidate rows")
    if list(selected.columns) != list(original.columns):
        raise StrategyValidationError("select must preserve candidate columns")
    try:
        pd.testing.assert_frame_equal(selected, original.loc[selected.index], check_like=False)
    except AssertionError as exc:
        raise StrategyValidationError("select modified or fabricated candidate rows") from exc
    selection_config = config.get("selection", {})
    if not isinstance(selection_config, Mapping):
        raise StrategyValidationError("selection config must be a mapping")
    maximum = selection_config.get("max_candidates", 3)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 0 <= maximum <= 3:
        raise StrategyValidationError("selection.max_candidates must be an integer from 0 to 3")
    if len(selected) > maximum:
        raise StrategyValidationError("select exceeded selection.max_candidates")
    repeat_eligible = plugin.hard_filter(context, config)
    repeat_scores = plugin.score(context, config)
    repeat_selected = plugin.select(original.copy(deep=True), config)
    try:
        pd.testing.assert_series_equal(eligible, repeat_eligible)
        pd.testing.assert_series_equal(scores, repeat_scores)
        pd.testing.assert_frame_equal(selected, repeat_selected)
    except AssertionError as exc:
        raise StrategyValidationError("plugin outputs are not deterministic for this input") from exc
    return selected.copy(deep=True)
