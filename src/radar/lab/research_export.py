"""Local, auditable experiment bundles built from immutable Run snapshots."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from radar.lab.store import RunStore, SCHEMA_VERSION, _json


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _flat(value):
    return _json(value) if isinstance(value, (dict, list, tuple)) else value


def _table(path: Path, records: list[dict], columns: list[str], *, parquet: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([{key: _flat(row.get(key)) for key in columns}
                          for row in records], columns=columns)
    if parquet:
        pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path)
    else:
        frame.to_csv(path, index=False, encoding="utf-8-sig")


def _signature(run: dict, run_type: str) -> dict:
    metadata = run["metadata"]
    values = {key: metadata.get(key) for key in (
        "feature_version", "market_feature_version", "data_snapshot",
        "universe_mode", "split", "adapter_code_hash")}
    if run_type == "scanner":
        values["label_version"] = metadata.get("label_version")
        values["scanner_worker_code_hash"] = metadata.get("scanner_worker_code_hash")
        evaluation = metadata.get("evaluation") or {}
        values["evaluation"] = {key: evaluation.get(key) for key in (
            "horizon_sessions", "success_rule", "primary_target",
            "primary_adverse_target", "event_cooldown_sessions", "top_k_values")}
    else:
        values['engine'] = metadata.get('engine', 'legacy')
        identity = metadata.get('engine_identity') or {}
        values['engine_build'] = {key: identity.get(key) for key in (
            'commit', 'engine_sha256', 'launcher_sha256', 'local_patch_sha256')}
        values['max_simultaneous_positions'] = metadata.get('lean_max_positions')
        values["engine_code_hash"] = metadata.get("engine_code_hash")
        values["execution_policy"] = metadata.get("execution_policy")
        values["fee_profile"] = metadata.get("fee_profile")
        values["slippage_bps"] = metadata.get("slippage_bps")
    return values


def build_research_bundle(store: RunStore, run_ids: list[str], output_dir: Path,
                          *, name: str = "Research export") -> dict:
    """Export every requested Run, including failed attempts, without changing the store."""
    if not isinstance(run_ids, list) or not 1 <= len(run_ids) <= 64 or len(run_ids) != len(set(run_ids)):
        raise ValueError("choose 1 to 64 distinct Run IDs")
    for run_id in run_ids:
        try:
            UUID(run_id)
        except (ValueError, AttributeError, TypeError) as error:
            raise ValueError("invalid Run ID") from error
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_id = str(uuid4())
    final_zip = output_dir / f"research-{bundle_id}.zip"
    with TemporaryDirectory(prefix="research-build-", dir=output_dir) as temporary:
        base = Path(temporary) / f"research-{bundle_id}"
        base.mkdir()
        records: list[dict] = []
        scanner_snapshots: dict[str, set[tuple[str, str]]] = {}
        groups: dict[str, dict] = {}
        warnings: list[str] = []
        for run_id in run_ids:
            try:
                run, run_type = store.get_run(run_id), "backtest"
            except ValueError:
                run, run_type = store.get_scanner_run(run_id), "scanner"
            metrics = run.get("metrics") or {}
            metadata = run["metadata"]
            signature = _signature(run, run_type)
            group_key = _json({"run_type": run_type, **signature})
            groups.setdefault(group_key, {"signature": signature, "run_type": run_type,
                                          "run_ids": []})["run_ids"].append(run_id)
            run_dir = base / "runs" / run_id
            run_dir.mkdir(parents=True)
            evidence = {key: value for key, value in run.items()
                        if key not in {"display_name", "archived_at"}}
            (run_dir / "run.json").write_text(_json(evidence), encoding="utf-8")
            (run_dir / "metrics.json").write_text(_json(metrics), encoding="utf-8")
            records.append({"run_id": run_id, "run_type": run_type,
                            "strategy_id": metadata.get("strategy_id"),
                            "strategy_version": metadata.get("strategy_version"),
                            "status": run["status"], "split": metadata.get("split"),
                            "signal_start": metadata.get("signal_start", metadata.get("start_date")),
                            "signal_end": metadata.get("signal_end", metadata.get("end_date")),
                            "total_return": metrics.get("total_return"),
                            "max_drawdown": metrics.get("max_drawdown"),
                            "candidate_count": metrics.get("candidate_count"),
                            "research_validity": metadata.get("research_validity"),
                            "git_dirty": metadata.get("git_dirty"),
                            "comparison_group": hashlib.sha256(group_key.encode()).hexdigest()[:12]})
            if run["status"] != "completed":
                warnings.append(f"{run_id}: {run['status']} Run; results may be incomplete")
                continue
            if metadata.get("git_dirty"):
                warnings.append(f"{run_id}: source checkout had uncommitted changes")
            if metadata.get("survivorship_bias_risk"):
                warnings.append(f"{run_id}: current-snapshot universe has survivorship bias")
            if metadata.get("split") == "test":
                warnings.append(f"{run_id}: historical Test has already been viewed; exploratory only")
            if run_type == "scanner":
                if not store.verify_scanner_artifacts(run_id):
                    raise ValueError(f"Scanner artifact verification failed: {run_id}")
                expected = int(metrics.get("candidate_count", 0))
                candidates = store.get_scanner_candidates(run_id, limit=max(1, expected))
                if len(candidates) != expected:
                    raise ValueError(f"Scanner candidate count mismatch: {run_id}")
                columns = ["signal_date", "symbol", "security_id", "security_name", "rank",
                           "strategy_score", "selected", "signal_event", "label_status",
                           "label_reason", "features", "diagnostics", "probabilities", "label",
                           "market_context"]
                _table(run_dir / "candidates.csv", candidates, columns)
                _table(run_dir / "candidates.parquet", candidates, columns, parquet=True)
                if pq.read_metadata(run_dir / "candidates.parquet").num_rows != expected:
                    raise ValueError(f"Parquet candidate count mismatch: {run_id}")
                scanner_snapshots[run_id] = {
                    (row["signal_date"], row["symbol"]) for row in candidates if row["selected"]}
            else:
                for label, frame in (("equity", store.get_equity(run_id)),
                                     ("trades", store.get_trades(run_id)),
                                     ("events", store.get_events(run_id))):
                    rows = frame.to_dict("records")
                    columns = list(frame.columns)
                    _table(run_dir / f"{label}.csv", rows, columns)
                    _table(run_dir / f"{label}.parquet", rows, columns, parquet=True)
        _table(base / "experiment_summary.csv", records,
               ["run_id", "run_type", "strategy_id", "strategy_version", "status", "split",
                "signal_start", "signal_end", "total_return", "max_drawdown",
                "candidate_count", "research_validity", "git_dirty", "comparison_group"])
        topk, regime, risk, overlap = [], [], [], []
        for run_id in run_ids:
            record = next(row for row in records if row["run_id"] == run_id)
            if record["status"] != "completed":
                continue
            run = (store.get_scanner_run(run_id) if record["run_type"] == "scanner"
                   else store.get_run(run_id))
            metrics = run.get("metrics") or {}
            if record["run_type"] == "scanner":
                for k in run["metadata"].get("evaluation", {}).get("top_k_values", []):
                    if f"event_precision_at_{k}" in metrics:
                        topk.append({"run_id": run_id, "k": k,
                                     "event_precision": metrics.get(f"event_precision_at_{k}"),
                                     "event_lift": metrics.get(f"event_lift_at_{k}"),
                                     "event_count": metrics.get(f"event_top_{k}_count")})
                for region in ("spy_above_ma20", "spy_below_ma20"):
                    regime.append({"run_id": run_id, "regime": region,
                                   "candidate_count": metrics.get(f"{region}_candidate_count"),
                                   "labeled_count": metrics.get(f"{region}_labeled_count"),
                                   "success_rate": metrics.get(f"{region}_success_rate")})
            else:
                risk.append({"run_id": run_id, "total_return": metrics.get("total_return"),
                             "max_drawdown": metrics.get("max_drawdown"),
                             "trade_count": metrics.get("trade_count"),
                             "win_rate": metrics.get("win_rate")})
        for left_id, right_id in combinations(scanner_snapshots, 2):
            if _signature(store.get_scanner_run(left_id), "scanner") != _signature(
                    store.get_scanner_run(right_id), "scanner"):
                continue
            left, right = scanner_snapshots[left_id], scanner_snapshots[right_id]
            shared = len(left & right)
            overlap.append({"left_run_id": left_id, "right_run_id": right_id,
                            "shared_selected": shared, "left_selected": len(left),
                            "right_selected": len(right),
                            "jaccard": shared / len(left | right) if left | right else None})
        for label, rows, columns in (
            ("topk_metrics", topk, ["run_id", "k", "event_precision", "event_lift", "event_count"]),
            ("candidate_overlap", overlap, ["left_run_id", "right_run_id", "shared_selected",
                                              "left_selected", "right_selected", "jaccard"]),
            ("regime_breakdown", regime, ["run_id", "regime", "candidate_count",
                                          "labeled_count", "success_rate"]),
            ("risk_summary", risk, ["run_id", "total_return", "max_drawdown",
                                    "trade_count", "win_rate"]),
        ):
            _table(base / "comparisons" / f"{label}.csv", rows, columns)
        if len(groups) > 1:
            warnings.append("Multiple provenance/evaluation/implementation groups: do not average across groups")
        manifest = {"format": "stock-radar-research-bundle-v1", "bundle_id": bundle_id,
                    "name": str(name)[:120], "created_at": datetime.now(timezone.utc).isoformat(),
                    "run_ids": run_ids, "run_count": len(records),
                    "comparison_groups": list(groups.values()),
                    "warnings": sorted(set(warnings)),
                    "limitations": ["Historical current-snapshot universes may omit delisted securities",
                                    "Existing Test results have been viewed and are exploratory",
                                    "Comparison groups preserve distinct evaluation and execution definitions"]}
        (base / "manifest.json").write_text(_json(manifest), encoding="utf-8")
        hashes = {str(path.relative_to(base)).replace("\\", "/"): _hash(path)
                  for path in sorted(base.rglob("*")) if path.is_file()}
        provenance = base / "provenance"
        provenance.mkdir()
        (provenance / "hashes.json").write_text(_json(hashes), encoding="utf-8")
        (provenance / "environment.json").write_text(_json({
            "exporter": "stock-radar-research-bundle-v1", "pyarrow": pa.__version__,
            "sqlite_store_schema": SCHEMA_VERSION}), encoding="utf-8")
        temporary_zip = output_dir / f".{bundle_id}.tmp"
        try:
            with ZipFile(temporary_zip, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
                for path in sorted(base.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(base))
            os.replace(temporary_zip, final_zip)
        finally:
            temporary_zip.unlink(missing_ok=True)
    result = {"bundle_id": bundle_id, "filename": final_zip.name,
              "path": str(final_zip), "sha256": _hash(final_zip),
              "name": manifest["name"], "created_at": manifest["created_at"],
              "run_count": len(records), "warnings": manifest["warnings"]}
    sidecar = output_dir / f"research-{bundle_id}.json"
    temporary_sidecar = output_dir / f".{bundle_id}.json.tmp"
    temporary_sidecar.write_text(_json(result), encoding="utf-8")
    os.replace(temporary_sidecar, sidecar)
    return result


def list_research_bundles(output_dir: Path, *, limit: int = 50) -> list[dict]:
    if not output_dir.is_dir():
        return []
    results = []
    for sidecar in sorted(output_dir.glob("research-*.json"),
                          key=lambda path: path.stat().st_mtime_ns, reverse=True)[:limit]:
        try:
            result = json.loads(sidecar.read_text(encoding="utf-8"))
            if (result.get("bundle_id") and
                    (output_dir / f"research-{result['bundle_id']}.zip").is_file()):
                results.append({key: result.get(key) for key in (
                    "bundle_id", "filename", "name", "created_at", "run_count", "sha256")})
        except (OSError, ValueError):
            continue
    return results
