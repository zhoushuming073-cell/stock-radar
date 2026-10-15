"""T-day bridge must stay dated and fail closed on provenance/value drift."""
from hashlib import sha256
import json

import duckdb
import pytest

from scripts.audit_box_candidate_tday_price_bridge import (
    accepted_database, compare_tday,
)


def databases():
    shape, accepted = duckdb.connect(), duckdb.connect()
    shape.execute("""CREATE TABLE shape_price (security_id VARCHAR,date DATE,
        symbol VARCHAR,open DOUBLE,high DOUBLE,low DOUBLE,close DOUBLE,
        volume DOUBLE,source VARCHAR,basis VARCHAR)""")
    accepted.execute("""CREATE TABLE daily_bars (security_id VARCHAR,date DATE,
        symbol VARCHAR,open DOUBLE,high DOUBLE,low DOUBLE,close DOUBLE,
        volume DOUBLE,provider VARCHAR,feed VARCHAR,adjustment VARCHAR)""")
    shape.execute("""INSERT INTO shape_price VALUES
        ('A','2024-01-02','AAA',10,11,9,10.5,1000,
         'Dolt:post-no-preference/stocks','raw')""")
    accepted.execute("""INSERT INTO daily_bars VALUES
        ('A','2024-01-02','AAA',10,11,9,10.5,1000,
         'Dolt','post-no-preference/stocks','raw'),
        ('A','2024-01-03','AAA',100,110,90,105,10000,
         'Dolt','post-no-preference/stocks','raw')""")
    return shape, accepted


def test_only_tday_values_enter_exact_comparison():
    shape, accepted = databases()
    try:
        assert compare_tday(shape, accepted, "A", "2024-01-02") == "exact_tday_match"
        accepted.execute("UPDATE daily_bars SET close=999 WHERE date='2024-01-03'")
        assert compare_tday(shape, accepted, "A", "2024-01-02") == "exact_tday_match"
        accepted.execute("UPDATE daily_bars SET close=12 WHERE date='2024-01-02'")
        assert compare_tday(shape, accepted, "A", "2024-01-02") == "tday_ohlcv_mismatch"
    finally:
        shape.close()
        accepted.close()


def test_missing_duplicate_and_provenance_are_separate_failures():
    shape, accepted = databases()
    try:
        accepted.execute("DELETE FROM daily_bars WHERE date='2024-01-02'")
        assert compare_tday(shape, accepted, "A", "2024-01-02") == "accepted_tday_missing"
        accepted.execute("""INSERT INTO daily_bars VALUES
            ('A','2024-01-02','AAA',10,11,9,10.5,1000,
             'Other','post-no-preference/stocks','raw')""")
        assert compare_tday(shape, accepted, "A", "2024-01-02") == "accepted_provenance_mismatch"
        accepted.execute("UPDATE daily_bars SET provider='Dolt'")
        accepted.execute("""INSERT INTO daily_bars VALUES
            ('A','2024-01-02','AAA',10,11,9,10.5,1000,
             'Dolt','post-no-preference/stocks','raw')""")
        assert compare_tday(shape, accepted, "A", "2024-01-02") == "accepted_tday_nonunique"
    finally:
        shape.close()
        accepted.close()


def test_manifest_hash_and_private_location_required(tmp_path):
    root = tmp_path / "root"
    data = root / "data"
    data.mkdir(parents=True)
    db = data / "accepted.duckdb"
    db.write_bytes(b"sealed")
    manifest = data / "manifest.json"
    payload = {"database": str(db), "database_sha256": sha256(b"sealed").hexdigest(),
               "quality_tier": "research-grade", "price_basis": "raw",
               "source_version": "pinned", "license": "test"}
    manifest.write_text(json.dumps(payload))
    assert accepted_database(root, manifest)[0] == db
    db.write_bytes(b"changed")
    with pytest.raises(ValueError, match="drift"):
        accepted_database(root, manifest)
    db.write_bytes(b"sealed")
    payload["database"] = str(tmp_path / "outside.duckdb")
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="drift"):
        accepted_database(root, manifest)
