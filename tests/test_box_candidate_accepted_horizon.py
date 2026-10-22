"""Accepted horizon reads dates and provenance, never later prices."""
import duckdb

from scripts.audit_box_candidate_accepted_horizon import accepted_session_metadata


def connection():
    con = duckdb.connect()
    # Deliberately omit OHLCV columns: the metadata probe must not need them.
    con.execute("""CREATE TABLE daily_bars (
        security_id VARCHAR,date DATE,symbol VARCHAR,
        provider VARCHAR,feed VARCHAR,adjustment VARCHAR)""")
    return con


def test_complete_dated_raw_metadata_without_price_columns():
    con = connection()
    try:
        con.execute("""INSERT INTO daily_bars VALUES
            ('A','2024-01-03','AAA','Dolt','post-no-preference/stocks','raw'),
            ('A','2024-01-04','AAA','Dolt','post-no-preference/stocks','raw'),
            ('A','2024-01-05','AAA','Dolt','post-no-preference/stocks','raw')""")
        result = accepted_session_metadata(
            con, "A", ["2024-01-03", "2024-01-04"], "AAA")
        assert result == {"matching_raw": 2}
    finally:
        con.close()


def test_missing_duplicate_wrong_source_and_symbol_transition():
    con = connection()
    try:
        con.execute("""INSERT INTO daily_bars VALUES
            ('A','2024-01-03','BBB','Dolt','post-no-preference/stocks','raw'),
            ('A','2024-01-04','AAA','Other','post-no-preference/stocks','raw'),
            ('A','2024-01-05','AAA','Dolt','post-no-preference/stocks','raw'),
            ('A','2024-01-05','AAA','Dolt','post-no-preference/stocks','raw')""")
        result = accepted_session_metadata(con, "A",
            ["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"], "AAA")
        assert result == {"matching_raw": 1, "symbol_transition": 1,
                          "provenance_mismatch": 1, "nonunique": 1, "missing": 1}
    finally:
        con.close()
