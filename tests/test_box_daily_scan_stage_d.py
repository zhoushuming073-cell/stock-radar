"""Private daily scan must reject split drift and resume corruption."""
import json

import duckdb
import pytest

from radar.box_labeling.stage_b import digest, packed
from scripts.scan_box_daily_stage_d import (
    chunks, dates_in_split, indexed_rows, verify_existing,
)
from scripts.verify_box_daily_stage_d import check_payload, reject_unexpected_chunks


def test_split_boundaries_exclude_test_fresh_and_cross_split():
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE sessions (date DATE)")
        connection.executemany("INSERT INTO sessions VALUES (?)", [
            ("2024-08-29",), ("2024-09-30",), ("2025-09-08",),
            ("2025-09-23",), ("2026-09-29",)])
        assert dates_in_split(connection, "train", "2024-08-29", "2024-08-29") == ["2024-08-29"]
        assert dates_in_split(connection, "validation", "2025-09-08", "2025-09-08") == ["2025-09-08"]
        with pytest.raises(ValueError, match="inside one frozen"):
            dates_in_split(connection, "train", "2024-08-29", "2024-09-30")
        with pytest.raises(ValueError, match="inside one frozen"):
            dates_in_split(connection, "test", "2025-09-23", "2025-09-23")
        with pytest.raises(ValueError, match="inside one frozen"):
            dates_in_split(connection, "validation", "2026-09-29", "2026-09-29")


def test_index_denominator_and_deterministic_chunks():
    with duckdb.connect() as connection:
        connection.execute("""CREATE TABLE universe_window_index (
            security_id VARCHAR,source VARCHAR,basis VARCHAR,
            membership_status VARCHAR,decision_date DATE,length INTEGER,
            supported_membership BOOLEAN,shape_research_ready BOOLEAN)""")
        connection.executemany("INSERT INTO universe_window_index VALUES (?,?,?,?,?,?,?,?)", [
            ("B", "S", "split", "confirmed_member", "2024-01-02", 126, True, True),
            ("A", "S", "raw", "probable_member", "2024-01-02", 126, True, True),
            ("X", "S", "raw", "unknown", "2024-01-02", 126, False, True),
            ("Z", "S", "raw", "confirmed_member", "2024-01-02", 126, True, False),
        ])
        rows, counts = indexed_rows(connection, "2024-01-02")
    assert [r["security_id"] for r in rows] == ["A", "B"]
    assert counts == {"indexed": 4, "supported": 3, "ready": 3, "eligible": 2}
    assert [len(g) for g in chunks(rows, 1)] == [1, 1]
    assert chunks([], 256) == [[]]
    with pytest.raises(ValueError, match="chunk_size"):
        chunks(rows, 0)


def test_resume_verifies_payload_hash_and_config(tmp_path):
    path = tmp_path / "chunk.json"
    payload = {"version": "v1", "selection_sha256": "abc", "processed": 2}
    path.write_bytes(packed({"payload": payload, "payload_sha256": digest(packed(payload))}))
    assert verify_existing(path, {"version": "v1", "selection_sha256": "abc"}) == payload
    with pytest.raises(ValueError, match="drift"):
        verify_existing(path, {"version": "v2"})
    altered = json.loads(path.read_bytes())
    altered["payload"]["processed"] = 3
    path.write_bytes(packed(altered))
    with pytest.raises(ValueError, match="corrupted"):
        verify_existing(path, {"version": "v1"})


def test_chunk_verifier_reconciles_both_detector_counts():
    names = ("quantile-zone-v1", "confirmed-pivot-zone-v1")
    group = [{"security_id": "A"}, {"security_id": "B"}]
    payload = {"requested": 2, "processed": 2, "excluded": [], "contexts": [],
               "states": {name: {"NO_ACTIVE_RANGE": 2} for name in names},
               "statuses": {name: {"NONE": 2} for name in names}}
    check_payload(payload, group)
    payload["states"][names[0]]["NO_ACTIVE_RANGE"] = 1
    with pytest.raises(ValueError, match="does not reconcile"):
        check_payload(payload, group)


def test_verifier_rejects_stale_or_partial_chunk(tmp_path):
    expected = {"0000-of-0001.json"}
    (tmp_path / "0000-of-0001.json").write_text("{}")
    reject_unexpected_chunks(tmp_path, expected)
    extra = tmp_path / "0001-of-0002.json"
    extra.write_text("{}")
    with pytest.raises(ValueError, match="unexpected"):
        reject_unexpected_chunks(tmp_path, expected)
    extra.unlink()
    (tmp_path / "0000-of-0001.partial").write_text("{}")
    with pytest.raises(ValueError, match="partial"):
        reject_unexpected_chunks(tmp_path, expected)
