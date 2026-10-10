"""Local bounded subprocess manager for independent Strategy Lab Runs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

import psutil
import pandas as pd
import yaml

from radar.backtest.costs import load_fee_config
from radar.backtest.runner import split_dates
from radar.lab.data import MARKET_FEATURE_VERSION, available_features, source_watermark
from radar.lab.parameters import (engine_legacy_fields, execution_defaults_from_legacy,
                                  research_hash, resolve_config, ResolvedRunConfig,
                                  validate_execution)
from radar.lab.scanner import LABEL_VERSION, evaluation_settings, validate_frozen_horizon
from radar.lab.readiness import local_readiness
from radar.lab.research_backend import MODE as RESEARCH_MODE, FEATURES as RESEARCH_FEATURES, backend_receipt
from radar.lab.terminal import TERMINAL_LABEL_VERSION, load_terminal_events, TERMINAL_POLICY
from radar.lab.store import RunStore
from radar.lab.universe import load_universe
from radar.lab.worker import sha256_file
from radar.research.pipeline import FEATURE_VERSION
from radar.strategy.loader import install_strategy_zip, load_strategy_directory
from radar.strategy.registry import StrategyRegistration, StrategyRegistry


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _config_hash(config: dict) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_UNSET = object()


class RunManager:
    """Keeps the browser responsive and preserves runs across UI refreshes."""

    def __init__(self, root: Path, *, max_workers: int = 1,
                 store_path: Path | None = None) -> None:
        self.root = Path(root).resolve()
        self.database = self.root / "data" / "phase2-research.duckdb"
        self.lab_dir = self.root / "data" / "strategy-lab"
        self.lab_dir.mkdir(parents=True, exist_ok=True)
        self.plugin_dir = self.lab_dir / "plugins"
        self.plugin_dir.mkdir(exist_ok=True)
        self.log_dir = self.lab_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)
        self.store = RunStore(store_path or self.lab_dir / "runs.sqlite3")
        self.max_workers = max(1, min(int(max_workers), 4))
        self._lock = RLock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._scanner_processes: dict[str, subprocess.Popen] = {}
        self._snapshot_cache: tuple[int, int, str] | None = None
        self.registry = StrategyRegistry()
        self._discover_plugins()

    def _discover_plugins(self) -> None:
        available = available_features(self.database) | RESEARCH_FEATURES
        folders = list((self.root / "strategies").glob("*/manifest.yaml"))
        folders += list(self.plugin_dir.glob("*/manifest.yaml"))
        for manifest_path in sorted(folders):
            load_strategy_directory(manifest_path.parent, available,
                                    registry=self.registry, run_tests=True)

    def list_strategies(self) -> list[StrategyRegistration]:
        return list(self.registry.list_plugins())

    def queue_scanner(self, strategy_id: str, **options: Any) -> str:
        return self.queue_scanner_requests([{"strategy_id": strategy_id, **options}])[0]

    def queue_scanner_requests(self, requests: list[dict[str, Any]]) -> list[str]:
        with self._lock:
            context = self._capture_batch_context()
            prepared = [(str(uuid4()), self._prepare_scanner_run(**request, _batch_context=context)) for request in requests]
            self._validate_batch_context(context, [metadata for _, metadata in prepared])
            return self.store.create_scanner_runs_batch(prepared)

    def _capture_batch_context(self) -> dict:
        """Seal one batch's research inputs before variant preparation."""
        paths = [self.root / "config/research.yaml", self.root / "config/backtest.yaml",
                 self.root / "data/security-master.csv", self.root / "data/security-master-manifest.json",
                 self.root / "data/terminal-events.csv", self.root / "data/terminal-events-manifest.json"]
        paths.append(self.root / "data/security-master-feature-store.json")
        context = {"snapshot": self._data_snapshot(), "watermark": source_watermark(self.database),
                   "files": {str(path): sha256_file(path) if path.exists() else None for path in paths}}
        context["windows"] = split_dates(self.database, self.root / "config/research.yaml")
        return context

    def _validate_batch_context(self, context: dict, metadata: list[dict]) -> None:
        if any(row.get("universe_mode") != RESEARCH_MODE and (
               row["data_snapshot"] != context["snapshot"] or
               row["source_watermark"] != context["watermark"]) for row in metadata):
            raise ValueError("research snapshot changed during batch preparation")
        for row in metadata:
            if row.get("universe_mode") == RESEARCH_MODE and row.get("research_backend") != backend_receipt(self.root):
                raise ValueError("Research Infrastructure v1 changed during batch preparation")
        current = self._capture_batch_context()
        for row in metadata:
            if row.get('pit_dependency'):
                from radar.pit.run import load_dependency
                load_dependency(row['pit_dependency'])
        if any(context[key] != current[key] for key in ("snapshot", "watermark", "files")):
            raise ValueError("research sources changed during batch preparation; no Runs queued")
        if any(row.get("research_config_hash") != context["files"][str(self.root / "config/research.yaml")]
               for row in metadata):
            raise ValueError("research configuration changed during batch preparation")

    def _prepare_scanner_run(self, strategy_id: str, *, split: str = "validation",
                      max_candidates: int | None | object = _UNSET,
                      config_override: dict | None = None,
                      evaluation_overrides: dict | None = None,
                      universe_mode: str = "current_snapshot",
                      experiment: dict | None = None,
                      _batch_context: dict | None = None) -> dict[str, Any]:
        if split not in {"train", "validation", "test", "fresh_oos"}:
            raise ValueError("scanner split must be train, validation, test or fresh_oos")
        if max_candidates is not _UNSET and max_candidates is not None and (
                isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or
                max_candidates < 0):
            raise ValueError("max_candidates must be non-negative or null")
        with self._lock:
            if "@" in strategy_id:
                identifier, version = strategy_id.rsplit("@", 1)
                registration = self.registry.get(identifier, version)
            else:
                registration = self.registry.get(strategy_id)
            if not self.registry.is_enabled(registration.manifest.id,
                                            registration.manifest.version):
                raise ValueError(f"strategy disabled: {strategy_id}")
            if registration.config.get("data_backend") == RESEARCH_MODE:
                raise ValueError("Research Infrastructure v1 plugin uses the LEAN Backtest path; Scanner adapter is not installed")
            if universe_mode == RESEARCH_MODE:
                raise ValueError("Scanner cannot use the Research Infrastructure v1 Backtest-only backend")
            config = _plain(config_override if config_override is not None else registration.config)
            if not isinstance(config, dict):
                raise ValueError("strategy configuration must be a mapping")
            warnings = []
            if max_candidates is not _UNSET:
                config["selection"] = {**(config.get("selection") or {}),
                                       "max_candidates": max_candidates}
                warnings.append(
                    "Deprecated Scanner max_candidates changes strategy output truncation; "
                    "use evaluation.top_k_values for quality metrics.")
            windows = (_batch_context["windows"] if _batch_context else
                       split_dates(self.database, self.root / "config" / "research.yaml"))
            if split not in windows:
                raise ValueError(f"{split} is not available in the current research store")
            dates = windows[split]
            sessions = [day for day in windows.get("sessions", dates)
                        if dates[0] <= day <= dates[2]]
            provider, provenance = load_universe(self.root, universe_mode, sessions)
            self._validate_pit_feature_binding(provider, _batch_context["snapshot"] if _batch_context else self._data_snapshot())
            readiness = local_readiness(self.root, universe_mode, sessions)
            terminal = load_terminal_events(self.root) if universe_mode == "point_in_time" else None
            label_version = TERMINAL_LABEL_VERSION if terminal is not None else LABEL_VERSION
            dataset = {
                "split": split, "signal_start": str(dates[0].date()),
                "signal_end": str(dates[1].date()),
                "evaluation_end": str(dates[2].date()),
                "feature_version": FEATURE_VERSION,
                "market_feature_version": MARKET_FEATURE_VERSION,
                "label_version": label_version,
                "terminal_fingerprint": terminal.fingerprint if terminal else None,
                "terminal_policy": TERMINAL_POLICY if terminal else None,
                "data_snapshot": _batch_context["snapshot"] if _batch_context else self._data_snapshot(),
                "universe_mode": universe_mode,
                "universe_fingerprint": provenance.fingerprint,
                "universe_provider": provenance.provider,
                "universe_version": provenance.source_version,
                "universe_coverage_start": provenance.coverage_start,
                "universe_coverage_end": provenance.coverage_end,
            }
            resolved = resolve_config(
                strategy_defaults=registration.config, strategy_draft=config,
                evaluation_defaults=evaluation_settings(None),
                execution_defaults={}, dataset=dataset,
                evaluation_overrides=evaluation_overrides)
            evaluation = evaluation_settings(resolved.values["evaluation"])
            validate_frozen_horizon(evaluation, yaml.safe_load(
                (self.root / "config/research.yaml").read_text(encoding="utf-8")))
            canonical = {**resolved.values, "evaluation": evaluation}
            resolved = ResolvedRunConfig(canonical, resolved.sources, research_hash(canonical))
            metadata = {
                "strategy_id": registration.manifest.id,
                "strategy_version": registration.manifest.version,
                "plugin_interface_version": registration.manifest.interface_version,
                "strategy_name": registration.manifest.name,
                "strategy_path": str(registration.path),
                "strategy_code_hash": sha256_file(registration.path / "strategy.py"),
                "strategy_manifest_hash": sha256_file(registration.path / "manifest.yaml"),
                "adapter_code_hash": sha256_file(self.root / "src/radar/strategy/adapter.py"),
                "scanner_code_hash": sha256_file(self.root / "src/radar/lab/scanner.py"),
                "scanner_worker_code_hash": sha256_file(self.root / "src/radar/lab/scanner_worker.py"),
                "data_code_hash": sha256_file(self.root / "src/radar/lab/data.py"),
                "research_config_hash": sha256_file(self.root / "config/research.yaml"),
                "host_source_hashes": {
                    name: sha256_file(self.root / name) for name in (
                        "src/radar/strategy/base.py", "src/radar/strategy/context.py",
                        "src/radar/strategy/validation.py", "src/radar/strategy/loader.py",
                        "src/radar/strategy/full_strategy2.py",
                        "src/radar/backtest/runner.py", "src/radar/research/pipeline.py",
                        "src/radar/lab/universe.py", "src/radar/lab/parameters.py",
                        "src/radar/lab/terminal.py", "src/radar/lab/readiness.py",
                    )
                },
                "config": config,
                "config_hash": _config_hash(config),
                "selection": config.get("selection", {"max_candidates": None}),
                "evaluation": evaluation,
                "resolved_config": resolved.metadata(),
                "resolved_config_hash": resolved.hash,
                "universe_mode": universe_mode,
                "survivorship_bias_risk": provenance.bias_risk,
                "universe_provenance": provenance.metadata(),
                "research_validity": readiness["research_validity"],
                "pit_readiness": readiness,
                "deprecation_warnings": warnings,
                "feature_version": FEATURE_VERSION,
                "market_feature_version": MARKET_FEATURE_VERSION,
                "data_snapshot": dataset["data_snapshot"],
                "source_watermark": _batch_context["watermark"] if _batch_context else source_watermark(self.database),
                "git_revision": self._git_revision(),
                "git_dirty": self._git_dirty(),
                "signal_start": str(dates[0].date()),
                "signal_end": str(dates[1].date()),
                "label_version": label_version,
                "split": split,
            }
            if experiment:
                metadata["experiment"] = experiment
            return metadata

    def import_zip(self, path: Path) -> StrategyRegistration:
        with self._lock:
            return install_strategy_zip(path, self.plugin_dir,
                                        available_features(self.database) | RESEARCH_FEATURES,
                                        registry=self.registry, run_tests=True)

    def uninstall_strategy(self, strategy_id: str) -> int:
        """Remove one exact ZIP-imported strategy version.

        Built-in strategies under ``root/strategies`` are source-controlled and
        cannot be removed through the lab. Historical Runs are immutable and
        are never deleted; an active Run of the strategy blocks uninstalling.
        """
        with self._lock:
            identifier, separator, version = strategy_id.rpartition("@")
            if not separator or not identifier or not version:
                raise ValueError("uninstall requires strategy_id@version")
            strategy_id = identifier
            if self.store.has_active_strategy_runs(strategy_id, version):
                raise ValueError(f"strategy has an active run: {strategy_id}")
            registrations = [
                item for item in self.registry.list_plugins()
                if item.manifest.id == strategy_id
                and item.manifest.version == version
            ]
            if not registrations:
                raise ValueError(f"unknown strategy: {strategy_id}")
            plugin_root = self.plugin_dir.resolve()
            for registration in registrations:
                path = registration.path
                expected_name = f"{strategy_id}@{registration.manifest.version}"
                if (path.is_symlink() or path.name != expected_name
                        or path.parent.resolve() != plugin_root):
                    raise ValueError(f"built-in strategy cannot be uninstalled: {strategy_id}")
            removed = 0
            for registration in registrations:
                shutil.rmtree(registration.path)
                self.registry.unregister(registration.manifest.id,
                                         registration.manifest.version)
                removed += 1
            return removed

    def _data_snapshot(self) -> str:
        stat = self.database.stat()
        key = (stat.st_size, stat.st_mtime_ns)
        if self._snapshot_cache is None or self._snapshot_cache[:2] != key:
            self._snapshot_cache = (*key, sha256_file(self.database))
        return self._snapshot_cache[2]

    def _validate_pit_feature_binding(self, provider, snapshot: str) -> None:
        if provider is not None:
            store = getattr(provider, "feature_store", None)
            if not store:
                raise ValueError("PIT requires an identity-bounded causal feature store")
            if store["source_database_sha256"] != snapshot:
                raise ValueError("PIT features are bound to another research snapshot")
            if store["research_config_sha256"] != sha256_file(self.root / "config/research.yaml"):
                raise ValueError("PIT feature research configuration changed; rebuild separately")

    def _git_revision(self) -> str:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root,
                                capture_output=True, text=True, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.stdout.strip() if result.returncode == 0 else "unavailable"

    def _git_dirty(self) -> bool:
        result = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                                capture_output=True, text=True, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.returncode != 0 or bool(result.stdout.strip())

    def queue_runs(self, strategy_ids: list[str], **options: Any) -> list[str]:
        return self.queue_run_requests([{"strategy_ids": strategy_ids, **options}])

    def queue_run_requests(self, requests: list[dict[str, Any]]) -> list[str]:
        with self._lock:
            context = self._capture_batch_context()
            prepared: list[tuple[str, dict[str, Any]]] = []
            for request in requests:
                options = dict(request)
                assigned_ids = options.pop("assigned_ids", None)
                metadata = self._prepare_runs(**options, _batch_context=context)
                ids = assigned_ids if assigned_ids is not None else [str(uuid4()) for _ in metadata]
                if len(ids) != len(metadata):
                    raise ValueError("assigned run IDs do not match prepared Runs")
                prepared.extend(zip(ids, metadata))
            self._validate_batch_context(context, [metadata for _, metadata in prepared])
            return self.store.create_runs_batch(prepared)

    def _prepare_runs(
        self, strategy_ids: list[str], *, split: str = "validation",
        slippage_bps: float = 10.0,
        configs_by_strategy: dict[str, dict] | None = None,
        window_override: tuple[str, str, str] | None = None,
        experiment: dict | None = None,
        batch_id: str | None = None,
        execution_timing: str = "next_open",
        after_run_id: str | None = None,
        pace_ms: int = 0,
        execution_overrides: dict | None = None,
        universe_mode: str = "current_snapshot",
        source_scanner_run_id: str | None = None,
        engine: str | None = None,
        _batch_context: dict | None = None,
    ) -> list[dict[str, Any]]:
        if split not in {"train", "validation", "test", "fresh_oos", "walk_forward"}:
            raise ValueError("backtest period must be Train, Validation, Test or Fresh OOS")
        if split == "walk_forward" and window_override is None:
            raise ValueError("walk-forward requires a date window")
        if not 0 <= float(slippage_bps) <= 100:
            raise ValueError("slippage must be between 0 and 100 basis points")
        if execution_timing not in {"legacy_close", "next_open"}:
            raise ValueError("unknown execution timing")
        if isinstance(pace_ms, bool) or not isinstance(pace_ms, int) or not 0 <= pace_ms <= 2000:
            raise ValueError("pace_ms must be between 0 and 2000")
        if not strategy_ids:
            return []
        from radar.lean.runtime import installation, settings
        lean_settings = settings(self.root)
        engine = engine or lean_settings.get('default_engine', 'legacy')
        if engine not in {'lean', 'legacy'}:
            raise ValueError('unknown backtest engine')
        engine_identity = installation(self.root)[1] if engine == 'lean' else None
        if engine == 'lean' and execution_timing != 'next_open':
            raise ValueError('LEAN requires next-session Open execution')
        max_positions = lean_settings.get('max_simultaneous_positions', 30)
        if isinstance(max_positions, bool) or not isinstance(max_positions, int) or max_positions < 1:
            raise ValueError('LEAN max_simultaneous_positions must be a positive integer')
        with self._lock:
            dates = (_batch_context["windows"] if _batch_context else
                     split_dates(self.database, self.root / "config" / "research.yaml"))
            if split == "fresh_oos" and split not in dates:
                raise ValueError("fresh_oos is not available in the current research store")
            window = list(window_override) if window_override else [str(day.date()) for day in dates[split]]
            if window_override:
                sessions = {str(day.date()) for day in dates["sessions"]}
                if len(window) != 3 or not all(day in sessions for day in window):
                    raise ValueError("walk-forward window must use trading sessions")
                if not window[0] <= window[1] <= window[2]:
                    raise ValueError("walk-forward dates are out of order")
                if window[2] >= str(dates["test_start"].date()):
                    raise ValueError("experiments cannot use the untouched Test period")
            backtest_path = self.root / "config" / "backtest.yaml"
            research_path = self.root / "config" / "research.yaml"
            fee_profile = load_fee_config(research_path).profile
            backtest_raw = yaml.safe_load(backtest_path.read_text(encoding="utf-8"))
            snapshot = _batch_context["snapshot"] if _batch_context else self._data_snapshot()
            watermark = _batch_context["watermark"] if _batch_context else source_watermark(self.database)
            commit = self._git_revision()
            prepared: list[dict[str, Any]] = []
            requested_universe_mode = universe_mode
            for reference in strategy_ids:
                universe_mode = requested_universe_mode
                if "@" in reference:
                    strategy_id, version = reference.rsplit("@", 1)
                    registration = self.registry.get(strategy_id, version)
                else:
                    strategy_id = reference
                    registration = self.registry.get(strategy_id)
                if not self.registry.is_enabled(registration.manifest.id,
                                                registration.manifest.version):
                    raise ValueError(f"strategy disabled: {reference}")
                declared_backend = registration.config.get("data_backend")
                if declared_backend not in (None, RESEARCH_MODE):
                    raise ValueError(f"unknown plugin data backend: {declared_backend}")
                research_plugin = declared_backend == RESEARCH_MODE
                if research_plugin:
                    if engine != "lean":
                        raise ValueError("Research Infrastructure v1 plugin requires local LEAN")
                    if split == "fresh_oos":
                        raise ValueError("Q2 v1.3 historical backend excludes Fresh")
                    if source_scanner_run_id:
                        raise ValueError("Q2 v1.3 cannot reuse Scanner signals from another backend")
                    universe_mode = RESEARCH_MODE
                    receipt = backend_receipt(self.root)
                    snapshot = receipt["core_database_sha256"]
                    watermark = receipt["semantic_hash"]
                else:
                    if universe_mode == RESEARCH_MODE:
                        raise ValueError("Research Infrastructure v1 requires a matching plugin backend declaration")
                    receipt = None
                    snapshot = _batch_context["snapshot"] if _batch_context else self._data_snapshot()
                    watermark = _batch_context["watermark"] if _batch_context else source_watermark(self.database)
                configs = configs_by_strategy or {}
                config = _plain(configs.get(reference, configs.get(strategy_id,
                                                                    registration.config)))
                if not isinstance(config, dict):
                    raise ValueError("strategy configuration must be a mapping")
                if config.get("data_backend") != declared_backend:
                    raise ValueError("strategy configuration cannot change the plugin data backend")
                available_sessions = dates["sessions"] if "sessions" in dates else dates[split]
                universe_sessions = [day for day in available_sessions
                                     if pd.Timestamp(window[0]) <= day <= pd.Timestamp(window[2])]
                provider, provenance = load_universe(self.root, universe_mode, universe_sessions)
                self._validate_pit_feature_binding(provider, snapshot)
                readiness = local_readiness(self.root, universe_mode, universe_sessions)
                terminal = load_terminal_events(self.root) if universe_mode == "point_in_time" else None
                if source_scanner_run_id:
                    scanner = self.store.get_scanner_run(source_scanner_run_id)
                    study = scanner["metadata"]
                    if scanner["status"] != "completed" or not self.store.verify_scanner_artifacts(
                            source_scanner_run_id):
                        raise ValueError("source Scanner run must be completed and verified")
                    if (study["strategy_id"], study["strategy_version"]) != (
                            registration.manifest.id, registration.manifest.version):
                        raise ValueError("source Scanner strategy does not match")
                    if study["data_snapshot"] != snapshot or study["split"] != split:
                        raise ValueError("source Scanner dataset does not match")
                    if (study.get("universe_mode", "current_snapshot") != universe_mode or
                            (study.get("universe_provenance") or {}).get("fingerprint") != provenance.fingerprint or
                            (study.get("universe_provenance") or {}).get("feature_store_sha256") != provenance.feature_store_sha256):
                        raise ValueError("source Scanner universe does not match")
                    if (study["signal_start"] != window[0] or
                            study["signal_end"] != window[1]):
                        raise ValueError("source Scanner signal interval does not match")
                    if _config_hash(config) != study["config_hash"]:
                        raise ValueError("source Scanner strategy config does not match")
                    expected_implementation = {
                        "strategy_code_hash": sha256_file(registration.path / "strategy.py"),
                        "strategy_manifest_hash": sha256_file(registration.path / "manifest.yaml"),
                        "adapter_code_hash": sha256_file(self.root / "src/radar/strategy/adapter.py"),
                    }
                    if any(study.get(key) != value for key, value in expected_implementation.items()):
                        raise ValueError("source Scanner signal-producing implementation does not match")
                    if any(study.get("host_source_hashes", {}).get(key) != sha256_file(self.root / key)
                           for key in ("src/radar/strategy/full_strategy2.py",
                                       "src/radar/strategy/context.py", "src/radar/strategy/validation.py",
                                       "src/radar/strategy/loader.py")):
                        raise ValueError("source Scanner signal-producing host implementation does not match")
                dataset = {
                    "split": split, "signal_start": window[0], "signal_end": window[1],
                    "evaluation_end": window[2], "feature_version": FEATURE_VERSION,
                    "market_feature_version": MARKET_FEATURE_VERSION,
                    "data_snapshot": snapshot, "universe_mode": universe_mode,
                    "universe_fingerprint": provenance.fingerprint,
                    "universe_provider": provenance.provider,
                    "universe_version": provenance.source_version,
                    "universe_coverage_start": provenance.coverage_start,
                    "universe_coverage_end": provenance.coverage_end,
                    "terminal_fingerprint": terminal.fingerprint if terminal else None,
                    "terminal_policy": TERMINAL_POLICY if terminal else None,
                    "source_scanner_run_id": source_scanner_run_id,
                    "signal_source_provenance_hash": _config_hash(study) if source_scanner_run_id else None,
                }
                defaults = execution_defaults_from_legacy(
                    backtest_raw, slippage_bps=slippage_bps,
                    execution_timing=execution_timing)
                resolved = resolve_config(
                    strategy_defaults=registration.config, strategy_draft=config,
                    evaluation_defaults={}, execution_defaults=defaults,
                    dataset=dataset, execution_overrides=execution_overrides)
                validate_execution(resolved.values["execution"])
                if research_plugin and resolved.values["execution"]["market_guard"]["mode"] != "none":
                    raise ValueError("Q2 Research Infrastructure v1 requires market guard 'none'")
                execution_policy = engine_legacy_fields(resolved.values["execution"])
                exit_source = resolved.sources.get("execution.exit.stop_loss", "host_default")
                metadata = {
                    "engine": engine,
                    "engine_identity": engine_identity,
                    "initial_capital": resolved.values['execution']['initial_capital'],
                    "lean_max_positions": max_positions if engine == 'lean' else None,
                    "strategy_id": registration.manifest.id,
                    "strategy_version": registration.manifest.version,
                    "plugin_interface_version": registration.manifest.interface_version,
                    "strategy_name": registration.manifest.name,
                    "strategy_path": str(registration.path),
                    "strategy_code_hash": sha256_file(registration.path / "strategy.py"),
                    "engine_code_hash": sha256_file(self.root / "src/radar/lean/algorithm.py" if engine == 'lean' else self.root / "src/radar/backtest/engine.py"),
                    "adapter_code_hash": sha256_file(self.root / "src" / "radar" / "strategy" / "adapter.py"),
                    "legacy_strategy_code_hash": sha256_file(self.root / "src" / "radar" / "strategy" / "full_strategy2.py"),
                    "host_source_hashes": {
                        name: sha256_file(self.root / name) for name in (
                            "src/radar/lab/worker.py", "src/radar/lab/data.py",
                            "src/radar/lab/parameters.py", "src/radar/lab/universe.py",
                            "src/radar/lab/terminal.py", "src/radar/lab/readiness.py",
                            "src/radar/backtest/runner.py", "src/radar/research/pipeline.py",
                            "src/radar/strategy/context.py", "src/radar/strategy/validation.py",
                            "src/radar/strategy/loader.py",
                        )
                    },
                    "config": config,
                    "config_hash": _config_hash(config),
                    "git_revision": commit,
                    "git_dirty": self._git_dirty(),
                    "feature_version": FEATURE_VERSION,
                    "market_feature_version": MARKET_FEATURE_VERSION,
                    "data_snapshot": snapshot,
                    "source_watermark": watermark,
                    "fee_profile": fee_profile,
                    "slippage_bps": float(slippage_bps),
                    "backtest_config_hash": sha256_file(backtest_path),
                    "research_config_hash": sha256_file(research_path),
                    "execution_policy": execution_policy,
                    "exit_policy_source": exit_source,
                    "resolved_config": resolved.metadata(),
                    "resolved_config_hash": resolved.hash,
                    "universe_mode": universe_mode,
                    "research_backend": receipt,
                    "survivorship_bias_risk": provenance.bias_risk,
                    "universe_provenance": provenance.metadata(),
                    "research_validity": readiness["research_validity"],
                    "pit_readiness": readiness,
                    "source_scanner_run_id": source_scanner_run_id,
                    "split": split,
                    "signal_source_provenance": study if source_scanner_run_id else None,
                    "window": window,
                    "start_date": window[0],
                    "end_date": window[1],
                    "evaluation_end": window[2],
                }
                if engine == 'lean':
                    if resolved.values['execution']['execution_timing'] != 'next_open':
                        raise ValueError('LEAN requires next-session Open execution')
                    metadata['host_source_hashes'].update({
                        str(path.relative_to(self.root)).replace('\\', '/'): sha256_file(path)
                        for path in (self.root / 'src/radar/lean').glob('*.py')})
                    metadata['host_source_hashes']['src/radar/backtest/costs.py'] = sha256_file(self.root / 'src/radar/backtest/costs.py')
                    lean_config = self.root / 'config/lean.yaml'
                    if lean_config.exists():
                        metadata['host_source_hashes']['config/lean.yaml'] = sha256_file(lean_config)
                    if research_plugin:
                        for relative in ("src/radar/lab/research_backend.py",
                                         "src/radar/research/infrastructure.py",
                                         "config/research_infrastructure_v1.json"):
                            metadata['host_source_hashes'][relative] = sha256_file(self.root / relative)
                    if universe_mode == 'point_in_time':
                        from radar.lab.data import load_strategy_segment
                        from radar.lean.export import freeze_signals
                        from radar.backtest.runner import load_spy_ma200_guard
                        from radar.pit.run import local_dependency, save_dependency, readiness
                        frame = load_strategy_segment(self.database, pd.Timestamp(window[0]), pd.Timestamp(window[2]),
                                                      set(registration.manifest.required_features), provider)
                        execution = resolved.values['execution']
                        guard = (load_spy_ma200_guard(self.database, universe_sessions[-1])
                                 if execution['market_guard']['mode'] == 'spy_ma200' else None)
                        signals, _ = freeze_signals(frame, universe_sessions, metadata, registration.plugin,
                                                    self.store, execution, guard)
                        closure = local_dependency(self.root, provider, metadata, frame, available_sessions, signals)
                        metadata['pit_dependency'] = save_dependency(self.root, closure)
                        metadata['run_pit_readiness'] = readiness(closure)
                        # Persist blocked attempts for Run History. The worker verifies
                        # the same frozen closure and rejects before invoking LEAN.
                        metadata['research_validity'] = metadata['run_pit_readiness']['research_validity']
                        metadata['host_source_hashes'].update({
                            str(path.relative_to(self.root)).replace('\\', '/'): sha256_file(path)
                            for path in (self.root / 'src/radar/pit').glob('*.py')})
                if experiment:
                    metadata["experiment"] = experiment
                if batch_id:
                    metadata["batch_id"] = batch_id
                if after_run_id:
                    metadata["after_run_id"] = after_run_id
                if pace_ms:
                    metadata["pace_ms"] = pace_ms
                prepared.append(metadata)
            return prepared

    @staticmethod
    def _process_matches(pid: int | None, run_id: str) -> bool:
        if not pid:
            return False
        try:
            command = psutil.Process(int(pid)).cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            return False
        return "radar.lab.worker" in command and run_id in command

    @staticmethod
    def _worker_pid(run_id: str) -> int | None:
        """Find a worker after a Windows venv launcher exits or UI reconnects."""
        for process in psutil.process_iter(["pid"]):
            try:
                command = process.cmdline()
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                continue
            if "radar.lab.worker" in command and run_id in command:
                return process.pid
        return None

    def refresh(self) -> None:
        with self._lock:
            for run in self.store.list_runs(limit=10_000):
                if run["status"] not in {"queued", "running", "cancel_requested"}:
                    continue
                run_id = run["run_id"]
                process = self._processes.get(run_id)
                if run["status"] == "queued":
                    if process is None or process.poll() is None:
                        continue
                    latest = self.store.get_run(run_id)
                    if latest["status"] == "queued" and self._worker_pid(run_id) is None:
                        self.store.fail_run(run_id, "backtest worker stopped before starting")
                    self._processes.pop(run_id, None)
                    continue
                if process is not None and process.poll() is None:
                    continue
                if self._process_matches(run.get("worker_pid"), run_id):
                    continue
                if run["status"] == "cancel_requested":
                    self.store.cancel_run(run_id)
                else:
                    self.store.fail_run(run_id, "backtest worker stopped unexpectedly")
                self._processes.pop(run_id, None)

    def launch_queued(self) -> None:
        self.dispatch_queued()

    def dispatch_queued(self) -> None:
        """Oldest queued Run first across Backtest and Scanner."""
        with self._lock:
            self.refresh()
            for run in self.store.list_scanner_runs(limit=10000):
                if run["status"] not in {"running", "cancel_requested"}:
                    continue
                run_id = run["run_id"]
                process = self._scanner_processes.get(run_id)
                if (process is not None and process.poll() is None) or self._scanner_worker_pid(run_id):
                    continue
                if run["status"] == "cancel_requested":
                    self.store.finish_scanner_cancel(run_id)
                else:
                    self.store.fail_scanner_run(run_id, "scanner worker stopped unexpectedly")
                self._scanner_processes.pop(run_id, None)
            runs = self.store.list_runs(limit=10_000)
            scanners = self.store.list_scanner_runs(limit=10000)
            by_id = {run["run_id"]: run for run in runs}
            active = sum(run["status"] in {"running", "cancel_requested"} for run in runs)
            active += sum(run["status"] in {"running", "cancel_requested"} for run in scanners)
            pending = sorted([("backtest", run) for run in runs if run["status"] == "queued"] +
                             [("scanner", run) for run in scanners if run["status"] == "queued"],
                             key=lambda pair: (pair[1]["created_at"], pair[1]["run_id"]))
            queued_active = set()
            for run_type, run in pending:
                run_id = run["run_id"]
                processes = self._scanner_processes if run_type == "scanner" else self._processes
                process = processes.get(run_id)
                worker_pid = (self._scanner_worker_pid(run_id) if run_type == "scanner"
                              else self._worker_pid(run_id))
                if (process is not None and process.poll() is None) or worker_pid:
                    queued_active.add(run_id)
            active += len(queued_active)
            for run_type, run in pending:
                if active >= self.max_workers:
                    break
                run_id = run["run_id"]
                if run_id in queued_active:
                    continue
                processes = self._scanner_processes if run_type == "scanner" else self._processes
                predecessor_id = (run["metadata"].get("after_run_id")
                                  if run_type == "backtest" else None)
                if predecessor_id:
                    predecessor = by_id.get(predecessor_id)
                    if predecessor is None:
                        self.store.fail_run(run_id, "timeline predecessor is missing")
                        continue
                    if predecessor["status"] in {"failed", "cancelled"}:
                        self.store.cancel_run(run_id, "previous timeline stage did not complete")
                        continue
                    if predecessor["status"] != "completed":
                        continue
                log_path = self.log_dir / (f"scanner-{run_id}.log" if run_type == "scanner"
                                           else f"{run_id}.log")
                python = Path(sys.executable)
                pythonw = python.with_name("pythonw.exe")
                if os.name == "nt" and pythonw.exists():
                    python = pythonw
                module = "radar.lab.scanner_worker" if run_type == "scanner" else "radar.lab.worker"
                command = [str(python), "-m", module, "--root",
                           str(self.root), "--store", str(self.store.path), "--run", run_id]
                with log_path.open("ab") as log:
                    process = subprocess.Popen(
                        command, cwd=self.root, stdin=subprocess.DEVNULL,
                        stdout=log, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                processes[run_id] = process
                active += 1

    def cancel(self, run_id: str, run_type: str = "backtest") -> None:
        if run_type == "scanner":
            self.store.request_scanner_cancel(run_id)
            return
        if run_type != "backtest":
            raise ValueError("unknown run type")
        record = self.store.get_run(run_id)
        if record["status"] == "queued":
            self.store.cancel_run(run_id)
        elif record["status"] == "running":
            self.store.request_cancel(run_id)

    def launch_queued_scanners(self) -> None:
        self.dispatch_queued()

    @staticmethod
    def _scanner_worker_pid(run_id: str) -> int | None:
        for process in psutil.process_iter(["pid"]):
            try:
                command = process.cmdline()
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                continue
            if "radar.lab.scanner_worker" in command and run_id in command:
                return process.pid
        return None
