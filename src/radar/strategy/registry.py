"""Pluggy-backed registry of validated strategy instances."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pluggy

from radar.strategy.base import StrategyPlugin
from radar.strategy.hookspec import StrategyHookSpec, hookimpl
from radar.strategy.validation import StrategyManifest, StrategyValidationError


@dataclass(frozen=True)
class StrategyRegistration:
    manifest: StrategyManifest
    config: Mapping[str, Any]
    plugin: StrategyPlugin
    path: Path


class _PluginHook:
    def __init__(self, plugin: StrategyPlugin) -> None:
        self._plugin = plugin

    @hookimpl
    def strategy_plugin(self) -> StrategyPlugin:
        return self._plugin


class StrategyRegistry:
    def __init__(self) -> None:
        self._manager = pluggy.PluginManager("stock_radar_strategy")
        self._manager.add_hookspecs(StrategyHookSpec)
        self._registrations: dict[tuple[str, str], StrategyRegistration] = {}
        self._hooks: dict[tuple[str, str], _PluginHook] = {}
        self._enabled: set[tuple[str, str]] = set()

    def register(self, registration: StrategyRegistration) -> StrategyRegistration:
        strategy_id = registration.manifest.id
        version = registration.manifest.version
        key = (strategy_id, version)
        if key in self._registrations:
            raise StrategyValidationError(f"duplicate strategy ID/version: {strategy_id} {version}")
        hook = _PluginHook(registration.plugin)
        self._manager.register(hook, name=f"{strategy_id}:{version}")
        self._registrations[key] = registration
        self._hooks[key] = hook
        self._enabled.add(key)
        return registration

    def get(self, strategy_id: str, version: str | None = None) -> StrategyRegistration:
        """Return a specific version, or the highest semantic version.

        Disabled versions remain readable for historical Run reconstruction.
        """
        if version is None:
            versions = [item_version for item_id, item_version in self._registrations if item_id == strategy_id]
            if not versions:
                raise KeyError(f"unknown strategy ID: {strategy_id}")
            version = max(versions, key=lambda value: tuple(map(int, value.split("."))))
        try:
            return self._registrations[(strategy_id, version)]
        except KeyError as exc:
            raise KeyError(f"unknown strategy ID/version: {strategy_id} {version}") from exc

    def list_plugins(self, *, enabled_only: bool = False) -> tuple[StrategyRegistration, ...]:
        keys = self._enabled if enabled_only else self._registrations.keys()
        return tuple(
            self._registrations[key]
            for key in sorted(keys, key=lambda pair: (pair[0], tuple(map(int, pair[1].split(".")))))
        )

    def is_enabled(self, strategy_id: str, version: str) -> bool:
        return (strategy_id, version) in self._enabled

    def disable(self, strategy_id: str, version: str) -> None:
        key = (strategy_id, version)
        self.get(strategy_id, version)
        if key in self._enabled:
            self._manager.unregister(self._hooks[key])
            self._enabled.remove(key)

    def enable(self, strategy_id: str, version: str) -> None:
        key = (strategy_id, version)
        self.get(strategy_id, version)
        if key not in self._enabled:
            self._manager.register(self._hooks[key], name=f"{strategy_id}:{version}")
            self._enabled.add(key)

    def unregister(self, strategy_id: str, version: str) -> None:
        """Remove a registration entirely, e.g. when uninstalling a plugin."""
        key = (strategy_id, version)
        self.get(strategy_id, version)
        if key in self._enabled:
            self._manager.unregister(self._hooks[key])
            self._enabled.remove(key)
        del self._hooks[key]
        del self._registrations[key]

    def hook_plugins(self) -> tuple[StrategyPlugin, ...]:
        """Call the pluggy hook to enumerate registered plugin instances."""
        return tuple(self._manager.hook.strategy_plugin())
