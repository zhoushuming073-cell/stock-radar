"""Pluggy extension point for a strategy plugin instance."""

from __future__ import annotations

import pluggy

from radar.strategy.base import StrategyPlugin


hookspec = pluggy.HookspecMarker("stock_radar_strategy")
hookimpl = pluggy.HookimplMarker("stock_radar_strategy")


class StrategyHookSpec:
    @hookspec
    def strategy_plugin(self) -> StrategyPlugin:
        """Return the plugin implemented by this registered module."""
