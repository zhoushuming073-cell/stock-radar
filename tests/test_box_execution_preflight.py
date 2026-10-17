"""Execution metadata preflight must select T's source and basis exactly."""
import duckdb

from scripts.audit_box_execution_preflight import next_session_metadata, reasons


def test_next_session_distinguishes_alternative_basis_from_duplicate_match():
    with duckdb.connect() as c:
        c.execute("CREATE TABLE sessions (date DATE)")
        c.executemany("INSERT INTO sessions VALUES (?)", [
            ("2024-01-02",), ("2024-01-03",), ("2024-01-04",)])
        c.execute("""CREATE TABLE shape_price (
            security_id VARCHAR,date DATE,source VARCHAR,basis VARCHAR,
            shape_research_ready BOOLEAN,identity_conflict BOOLEAN,
            class_or_name_boundary BOOLEAN,known_split BOOLEAN,
            invalid_split_action BOOLEAN,suspected_split BOOLEAN,
            membership_status VARCHAR)""")
        base = (True, False, False, False, False, False, "confirmed_member")
        c.executemany("INSERT INTO shape_price VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
            ("one", "2024-01-03", "S", "split", *base),
            ("one", "2024-01-03", "S", "raw", *base),
            ("two", "2024-01-03", "S", "raw", *base),
        ])
        selected = [{"task_id": "a", "security_id": "one", "decision_date": "2024-01-02",
                     "source": "S", "basis": "split"},
                    {"task_id": "b", "security_id": "two", "decision_date": "2024-01-02",
                     "source": "S", "basis": "split"}]
        result = next_session_metadata(c, selected)
    by_id = {r["task_id"]: r for r in result}
    assert by_id["a"]["total_price_rows"] == 2
    assert by_id["a"]["matching_price_rows"] == 1
    assert reasons(by_id["a"], selected[0]) == ()
    assert by_id["b"]["total_price_rows"] == 1
    assert by_id["b"]["matching_price_rows"] == 0
    assert reasons(by_id["b"], selected[1]) == ("next_source_basis_unavailable",)


def test_missing_session_and_flagged_bar_fail_closed():
    expected = {"source": "S", "basis": "raw"}
    empty = {"next_session": None, "total_price_rows": 0,
             "matching_price_rows": 0}
    assert reasons(empty, expected) == ("no_next_session_in_frozen_core",
                                        "no_next_security_bar")
    flagged = {"next_session": "2024-01-03", "total_price_rows": 1,
               "matching_price_rows": 1, "source": "S", "basis": "raw",
               "all_ready": False, "identity_flag": True, "split_flag": True,
               "membership_status": "unknown"}
    assert reasons(flagged, expected) == (
        "next_bar_not_research_ready", "next_bar_identity_flag",
        "next_bar_split_flag", "next_membership_not_supported")
