"""Necessary gate must preserve near-lower states and uncertain prefixes."""
import duckdb
import pytest

from radar.box_labeling.fast_gate import necessary_near_lower
from radar.box_labeling.lower_band import LowerBandConfig
from scripts.audit_box_fast_gate_stage_d import recent_prefixes, safe_prefix


def base():
    return [100.0]*20, [98.0]*20, [1000.0]*20


def test_each_stage_c_necessary_condition_and_boundaries():
    config = LowerBandConfig()
    close, low, volume = base()
    assert necessary_near_lower(close, low, volume, config) == (True, ())
    close[-1] = 107
    assert "last_day_overextended" in necessary_near_lower(close, low, volume, config)[1]
    close[-1] = 99.5
    assert necessary_near_lower(close, low, volume, config)[0]
    close[-1] = 99
    assert "last_day_declining" in necessary_near_lower(close, low, volume, config)[1]
    close[-1] = 100
    close[-4] = 88
    assert "three_day_overextended" in necessary_near_lower(close, low, volume, config)[1]
    close[-4] = 100
    low[-1] = 90
    assert "recent_low_falling" in necessary_near_lower(close, low, volume, config)[1]
    low[-1] = 98
    volume[:17] = [0.0]*17
    assert "volume_baseline_unavailable" in necessary_near_lower(close, low, volume, config)[1]
    volume[:17] = [1000.0]*17
    volume[-3:] = [5000.0]*3
    assert "volume_spike" in necessary_near_lower(close, low, volume, config)[1]


def test_unknown_data_is_retained_for_full_provider():
    config = LowerBandConfig()
    c, lo, v = base()
    assert necessary_near_lower(c[:-1], lo[:-1], v[:-1], config) == (
        True, ("unknown_recent_prefix",))
    c[0] = float("nan")
    assert necessary_near_lower(c, lo, v, config) == (True, ("unknown_recent_prefix",))


def test_bulk_recent_query_uses_only_prefix_and_source_basis():
    with duckdb.connect() as c:
        c.execute("""CREATE TABLE universe_window_index (
            security_id VARCHAR,series_id VARCHAR,session_no INTEGER,
            source VARCHAR,basis VARCHAR,decision_date DATE,length INTEGER,
            supported_membership BOOLEAN,shape_research_ready BOOLEAN)""")
        c.execute("""CREATE TABLE shape_price (
            security_id VARCHAR,series_id VARCHAR,session_no INTEGER,date DATE,
            source VARCHAR,basis VARCHAR,shape_research_ready BOOLEAN,
            close DOUBLE,low DOUBLE,volume DOUBLE)""")
        c.execute("""INSERT INTO universe_window_index VALUES (
            'A','series',20,'S','split','2024-01-30',126,true,true)""")
        c.executemany("INSERT INTO shape_price VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("A", "series", n, f"2024-01-{n+10:02d}", "S", "split", True,
             float(90+n), float(88+n), 1000.0) for n in range(1, 21)])
        c.execute("""INSERT INTO shape_price VALUES (
            'A','series',21,'2024-01-31','S','split',true,999,999,999)""")
        c.execute("""INSERT INTO shape_price VALUES (
            'A','series',20,'2024-02-01','S','split',true,999,999,999)""")
        rows = recent_prefixes(c, "2024-01-30")
        assert len(rows) == 1 and safe_prefix(rows[0])
        c.execute("UPDATE shape_price SET basis='raw' WHERE session_no=19")
        mismatched = recent_prefixes(c, "2024-01-30")
    assert len(rows[0]["closes"]) == 20
    assert max(rows[0]["closes"]) == 110
    assert 999 not in rows[0]["closes"]
    assert not safe_prefix(mismatched[0])
