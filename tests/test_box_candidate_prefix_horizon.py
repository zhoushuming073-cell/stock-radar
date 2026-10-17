"""The metadata horizon is ordered and cannot cross its frozen split."""
import duckdb

from scripts.audit_box_candidate_prefix_horizon import future_sessions


def test_future_session_list_uses_only_next_ten_within_split():
    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE sessions (date DATE)")
        con.executemany("INSERT INTO sessions VALUES (?)", [
            (f"2025-01-{day:02d}",) for day in range(1, 16)])
        assert future_sessions(con, "2025-01-02", "2025-01-12") == [
            f"2025-01-{day:02d}" for day in range(3, 13)]
        assert future_sessions(con, "2025-01-10", "2025-01-12") == [
            "2025-01-11", "2025-01-12"]
    finally:
        con.close()
