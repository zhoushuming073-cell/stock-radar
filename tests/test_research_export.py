"""Research bundles preserve complete Scanner evidence and audit hashes."""

import csv
import hashlib
import json
from zipfile import ZipFile

import pyarrow.parquet as pq

from radar.lab.research_export import build_research_bundle, list_research_bundles
from radar.lab.store import RunStore, SCHEMA_VERSION, _REQUIRED_METADATA


def test_export_includes_every_candidate_and_matching_csv_parquet(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3")
    metadata = {key: "fixture" for key in (
        "strategy_id", "strategy_version", "plugin_interface_version", "config",
        "selection", "evaluation", "feature_version", "market_feature_version",
        "data_snapshot", "source_watermark", "git_revision", "signal_start",
        "signal_end", "label_version", "strategy_code_hash", "config_hash")}
    metadata["config"] = {}
    metadata["selection"] = {}
    metadata["evaluation"] = {"horizon_sessions": 10, "top_k_values": [7]}
    run_id = store.create_scanner_run(metadata)
    store.start_scanner_run(run_id, 12345)
    candidates = [{"signal_date": "2025-01-02", "symbol": symbol, "rank": rank,
                   "strategy_score": 1.0 / rank, "selected": True,
                   "features": {"ret_1": .01 * rank},
                   "label": {"hit_5pct_10d": rank == 1}}
                  for rank, symbol in enumerate(("AAA", "BBB", "CCC"), 1)]
    store.finish_scanner_run(run_id, candidates, {"candidate_count": 3,
                                                   "event_precision_at_7": 1 / 3})
    result = build_research_bundle(store, [run_id], tmp_path / "exports")
    assert list_research_bundles(tmp_path / "exports")[0]["bundle_id"] == result["bundle_id"]
    with ZipFile(result["path"]) as archive:
        names = set(archive.namelist())
        assert f"runs/{run_id}/candidates.csv" in names
        assert f"runs/{run_id}/candidates.parquet" in names
        rows = list(csv.DictReader(archive.read(f"runs/{run_id}/candidates.csv")
                                   .decode("utf-8-sig").splitlines()))
        assert [row["symbol"] for row in rows] == ["AAA", "BBB", "CCC"]
        with archive.open(f"runs/{run_id}/candidates.parquet") as stream:
            parquet = pq.read_table(stream).to_pydict()
        assert parquet["symbol"] == ["AAA", "BBB", "CCC"]
        assert json.loads(rows[0]["features"]) == {"ret_1": .01}
        hashes = json.loads(archive.read("provenance/hashes.json"))
        for name, digest in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["run_ids"] == [run_id]
        assert manifest["run_count"] == 1
        rows = list(csv.DictReader(archive.read("comparisons/topk_metrics.csv")
                                   .decode("utf-8-sig").splitlines()))
        assert [int(row["k"]) for row in rows] == [7]
        environment = json.loads(archive.read("provenance/environment.json"))
        assert environment["sqlite_store_schema"] == SCHEMA_VERSION


def test_presentation_edits_do_not_change_exported_run_evidence(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3")
    metadata = {key: "fixture" for key in _REQUIRED_METADATA}
    metadata.update(config={}, execution_policy={}, split="validation")
    run_id = store.create_run(metadata)
    store.start_run(run_id, 1234)
    store.finish_run(run_id, {"equity": [], "trades": [], "orders": [], "events": []}, {})
    first = build_research_bundle(store, [run_id], tmp_path / "exports")
    store.rename_run(run_id, "My edited title")
    store.set_run_archived(run_id, True)
    second = build_research_bundle(store, [run_id], tmp_path / "exports")
    with ZipFile(first["path"]) as before, ZipFile(second["path"]) as after:
        path = f"runs/{run_id}/run.json"
        assert before.read(path) == after.read(path)
        assert "display_name" not in json.loads(after.read(path))
        assert "archived_at" not in json.loads(after.read(path))
