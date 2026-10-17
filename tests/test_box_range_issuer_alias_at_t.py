"""Decision-dated issuer alias audit does not use future links."""
import duckdb

from scripts.audit_box_range_issuer_alias_at_t import classify, dated_evidence


def test_same_cik_other_active_id_is_flagged_but_future_or_stale_is_not():
    with duckdb.connect() as c:
        c.execute("""CREATE TABLE ticker_episode (
            security_id VARCHAR, interval_id VARCHAR, valid_from DATE, valid_to DATE)""")
        c.execute("""CREATE TABLE issuer_evidence (
            security_id VARCHAR, interval_id VARCHAR, cik VARCHAR,
            available_on DATE, name_compatible BOOLEAN)""")
        c.execute("""CREATE TABLE review_annotation (
            security_id VARCHAR, known_on DATE, disputed_start DATE,
            disputed_end DATE)""")
        c.executemany("INSERT INTO ticker_episode VALUES (?,?,?,?)", [
            ("main", "current", "2022-01-01", "2024-12-31"),
            ("main", "old", "2020-01-01", "2021-12-31"),
            ("other", "other-current", "2022-01-01", "2024-12-31"),
            ("stale", "stale", "2020-01-01", "2022-12-31"),
            ("future", "future", "2022-01-01", "2024-12-31"),
            ("badname", "badname", "2022-01-01", "2024-12-31"),
        ])
        c.executemany("INSERT INTO issuer_evidence VALUES (?,?,?,?,?)", [
            ("main", "current", "1", "2023-01-01", True),
            ("main", "old", "9", "2021-01-01", True),
            ("other", "other-current", "1", "2023-01-01", True),
            ("stale", "stale", "1", "2022-01-01", True),
            ("future", "future", "1", "2024-01-01", True),
            ("badname", "badname", "2", "2023-01-01", False),
        ])
        result = dated_evidence(c, [
            {"task_id": "one", "security_id": "main", "window_start": "2023-01-01",
             "decision_date": "2023-06-01"},
            {"task_id": "two", "security_id": "badname", "window_start": "2023-01-01",
             "decision_date": "2023-06-01"},
        ])
    by_task = {row["task_id"]: row for row in result}
    assert by_task["one"]["cik_count"] == 1
    assert by_task["one"]["cik"] == "1"
    assert by_task["one"]["other_active_security_ids"] == 1
    assert classify(by_task["one"]) == "CONTEMPORANEOUS_ISSUER_ALIAS"
    assert classify(by_task["two"]) == "KNOWN_IDENTITY_CONFLICT"


def test_observational_clear_remains_explicitly_non_official():
    row = {"cik_count": 1, "full_window_episodes": 1,
           "bad_names": 0, "known_discontinuity": 0,
           "other_active_security_ids": 0}
    assert classify(row) == "OBSERVATIONAL_NO_KNOWN_CONFLICT"
