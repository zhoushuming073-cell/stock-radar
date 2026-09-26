"""Local bounded subprocess manager for independent Strategy Lab Runs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import RLock
from typing import Any, Mapping

import psutil
import yaml

from radar.backtest.costs import load_fee_config
from radar.backtest.runner import split_dates
from radar.lab.data import available_features, source_watermark
from radar.lab.store import RunStore
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


class RunManager:
    """Keeps the browser responsive and preserves runs across UI refreshes."""

    def __init__(self, root: Path, *, max_workers: int = 2,
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
        self._snapshot_cache: tuple[int, int, str] | None = None
        self.registry = StrategyRegistry()
        self._discover_plugins()

    def _discover_plugins(self) -> None:
        available = available_features(self.database)
        folders = list((self.root / "strategies").glob("*/manifest.yaml"))
        folders += list(self.plugin_dir.glob("*/manifest.yaml"))
        for manifest_path in sorted(folders):
            load_strategy_directory(manifest_path.parent, available,
                                    registry=self.registry, run_tests=True)

    def list_strategies(self) -> list[StrategyRegistration]:
        return list(self.registry.list_plugins())

    def import_zip(self, path: Path) -> StrategyRegistration:
        with self._lock:
            return install_strategy_zip(path, self.plugin_dir,
                                        available_features(self.database),
                                        registry=self.registry, run_tests=True)

    def _data_snapshot(self) -> str:
        stat = self.database.stat()
        key = (stat.st_size, stat.st_mtime_ns)
        if self._snapshot_cache is None or self._snapshot_cache[:2] != key:
            self._snapshot_cache = (*key, sha256_file(self.database))
        return self._snapshot_cache[2]

    def _git_revision(self) -> str:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root,
                                capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else "unavailable"

    def _git_dirty(self) -> bool:
        result = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                                capture_output=True, text=True, check=False)
        return result.returncode != 0 or bool(result.stdout.strip())

    def queue_runs(
        self, strategy_ids: list[str], *, split: str = "validation",
        slippage_bps: float = 10.0,
        configs_by_strategy: dict[str, dict] | None = None,
        window_override: tuple[str, str, str] | None = None,
        experiment: dict | None = None,
    ) -> list[str]:
        if split not in {"train", "validation", "test", "walk_forward"}:
            raise ValueError("backtest period must be Train, Validation, or Test")
        if split == "walk_forward" and window_override is None:
            raise ValueError("walk-forward requires a date window")
        if not 0 <= float(slippage_bps) <= 100:
            raise ValueError("slippage must be between 0 and 100 basis points")
        if not strategy_ids:
            return []
        with self._lock:
            dates = split_dates(self.database, self.root / "config" / "research.yaml")
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
            snapshot = self._data_snapshot()
            watermark = source_watermark(self.database)
            commit = self._git_revision()
            created: list[str] = []
            for reference in strategy_ids:
                if "@" in reference:
                    strategy_id, version = reference.rsplit("@", 1)
                    registration = self.registry.get(strategy_id, version)
                else:
                    strategy_id = reference
                    registration = self.registry.get(strategy_id)
                if not self.registry.is_enabled(registration.manifest.id,
                                                registration.manifest.version):
                    raise ValueError(f"strategy disabled: {reference}")
                configs = configs_by_strategy or {}
                config = _plain(configs.get(reference, configs.get(strategy_id,
                                                                    registration.config)))
                if not isinstance(config, dict):
                    raise ValueError("strategy configuration must be a mapping")
                metadata = {
                    "strategy_id": registration.manifest.id,
                    "strategy_version": registration.manifest.version,
                    "plugin_interface_version": registration.manifest.interface_version,
                    "strategy_name": registration.manifest.name,
                    "strategy_path": str(registration.path),
                    "strategy_code_hash": sha256_file(registration.path / "strategy.py"),
                    "engine_code_hash": sha256_file(self.root / "src" / "radar" / "backtest" / "engine.py"),
                    "adapter_code_hash": sha256_file(self.root / "src" / "radar" / "strategy" / "adapter.py"),
                    "legacy_strategy_code_hash": sha256_file(self.root / "src" / "radar" / "strategy" / "full_strategy2.py"),
                    "config": config,
                    "config_hash": _config_hash(config),
                    "git_revision": commit,
                    "git_dirty": self._git_dirty(),
                    "feature_version": FEATURE_VERSION,
                    "data_snapshot": snapshot,
                    "source_watermark": watermark,
                    "fee_profile": fee_profile,
                    "slippage_bps": float(slippage_bps),
                    "backtest_config_hash": sha256_file(backtest_path),
                    "research_config_hash": sha256_file(research_path),
                    "execution_policy": {key: backtest_raw[key] for key in (
                        "initial_capital", "max_new_candidates", "take_profit", "stop_loss",
                        "max_holding_sessions", "entry_gap_min", "entry_gap_max",
                        "max_position_fraction", "minimum_position_fraction",
                        "max_order_to_avg_dollar_volume")},
                    "split": split,
                    "window": window,
                    "start_date": window[0],
                    "end_date": window[1],
                    "evaluation_end": window[2],
                }
                if experiment:
                    metadata["experiment"] = experiment
                created.append(self.store.create_run(metadata))
            return created

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
        with self._lock:
            self.refresh()
            runs = self.store.list_runs(limit=10_000)
            active = sum(run["status"] in {"running", "cancel_requested"} for run in runs)
            queued_active: set[str] = set()
            for run in runs:
                if run["status"] != "queued":
                    continue
                run_id = run["run_id"]
                process = self._processes.get(run_id)
                if (process is not None and process.poll() is None) or self._worker_pid(run_id):
                    queued_active.add(run_id)
            active += len(queued_active)
            for run in runs:
                if active >= self.max_workers:
                    break
                if run["status"] != "queued":
                    continue
                run_id = run["run_id"]
                if run_id in queued_active:
                    continue
                log_path = self.log_dir / f"{run_id}.log"
                python = Path(sys.executable)
                pythonw = python.with_name("pythonw.exe")
                if os.name == "nt" and pythonw.exists():
                    python = pythonw
                command = [str(python), "-m", "radar.lab.worker", "--root",
                           str(self.root), "--store", str(self.store.path), "--run", run_id]
                with log_path.open("ab") as log:
                    process = subprocess.Popen(
                        command, cwd=self.root, stdin=subprocess.DEVNULL,
                        stdout=log, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                self._processes[run_id] = process
                active += 1

    def cancel(self, run_id: str) -> None:
        record = self.store.get_run(run_id)
        if record["status"] == "queued":
            self.store.cancel_run(run_id)
        elif record["status"] == "running":
            self.store.request_cancel(run_id)
