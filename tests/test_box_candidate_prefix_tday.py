"""The prefix bridge selects Dolt/raw at decision T only."""
from collections import Counter

import duckdb
import pytest

from scripts.audit_box_candidate_prefix_tday import classify_requests


def _request(day: str, sid: str, source: str, basis: str) -> dict:
    return {"decision_date": day, "security_id": sid,
            "source": source, "basis": basis}


def test_prefix_tday_ignores_legacy_and_later_prices():
    shape = duckdb.connect()
    accepted = duckdb.connect()
    shape.execute("""CREATE TABLE shape_price (
        security_id VARCHAR,date DATE,symbol VARCHAR,open DOUBLE,high DOUBLE,
        low DOUBLE,close DOUBLE,volume DOUBLE,source VARCHAR,basis VARCHAR)""")
    accepted.execute("""CREATE TABLE daily_bars (
        security_id VARCHAR,date DATE,symbol VARCHAR,open DOUBLE,high DOUBLE,
        low DOUBLE,close DOUBLE,volume DOUBLE,provider VARCHAR,feed VARCHAR,
        adjustment VARCHAR)""")
    try:
        shape.execute("""INSERT INTO shape_price VALUES
            ('A','2024-10-01','AAA',10,11,9,10,100,
             'Dolt:post-no-preference/stocks','raw')""")
        accepted.execute("""INSERT INTO daily_bars VALUES
            ('A','2024-10-01','AAA',10,11,9,10,100,
             'Dolt','post-no-preference/stocks','raw'),
            ('A','2024-10-02','AAA',200,210,190,200,999,
             'Dolt','post-no-preference/stocks','raw')""")
        requests = [_request("2024-10-01", "A", "Dolt:post-no-preference/stocks", "raw"),
                    _request("2024-10-01", "B", "legacy:alpaca:sip", "split")]
        assert classify_requests(requests, shape, accepted, "2024-10-01") == Counter(
            exact_tday_match=1)
        accepted.execute("UPDATE daily_bars SET close=1 WHERE date='2024-10-02'")
        assert classify_requests(requests, shape, accepted, "2024-10-01") == Counter(
            exact_tday_match=1)
        with pytest.raises(ValueError, match="decision-date"):
            classify_requests(requests, shape, accepted, "2024-10-02")
    finally:
        shape.close()
        accepted.close()
