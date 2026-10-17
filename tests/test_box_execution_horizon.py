"""Split-bounded metadata checks do not create LEAN-ready price claims."""
import duckdb
import pytest

from scripts.audit_box_execution_horizon import horizon_metadata, summarize


def test_horizon_stops_at_train_boundary_and_distinguishes_raw_source():
    with duckdb.connect() as c:
        c.execute("CREATE TABLE sessions (date DATE)")
        c.executemany("INSERT INTO sessions VALUES (?)", [
            ("2024-08-28",), ("2024-08-29",), ("2024-09-30",)])
        c.execute("""CREATE TABLE shape_price (
            security_id VARCHAR,date DATE,source VARCHAR,basis VARCHAR,
            shape_research_ready BOOLEAN,identity_conflict BOOLEAN,
            class_or_name_boundary BOOLEAN,known_split BOOLEAN,
            invalid_split_action BOOLEAN,suspected_split BOOLEAN)""")
        clean = (True, False, False, False, False, False)
        c.executemany("INSERT INTO shape_price VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("one", "2024-08-29", "S", "split", *clean),
            ("one", "2024-08-29", "OTHER", "raw", *clean),
            ("one", "2024-09-30", "S", "raw", *clean),
        ])
        request = [{"task_id": "a", "security_id": "one", "decision_date": "2024-08-28",
                    "split": "train", "split_end": "2024-08-29", "source": "S", "basis": "split"}]
        rows = horizon_metadata(c, request, horizon=2)
    assert len(rows) == 1
    assert str(rows[0]["date"]) == "2024-08-29"
    assert rows[0]["matching_rows"] == 1
    assert rows[0]["any_raw_rows"] == 1
    assert rows[0]["same_source_raw_rows"] == 0
    private, public = summarize(request, rows, horizon=2)
    assert private[0]["complete_horizon_within_split"] is False
    assert public["split_censored_tasks"] == 1
    assert public["same_source_raw_complete_tasks"] == 0


def test_complete_horizon_requires_unflagged_unique_raw():
    with duckdb.connect() as c:
        c.execute("CREATE TABLE sessions (date DATE)")
        c.executemany("INSERT INTO sessions VALUES (?)", [
            ("2024-01-02",), ("2024-01-03",), ("2024-01-04",)])
        c.execute("""CREATE TABLE shape_price (
            security_id VARCHAR,date DATE,source VARCHAR,basis VARCHAR,
            shape_research_ready BOOLEAN,identity_conflict BOOLEAN,
            class_or_name_boundary BOOLEAN,known_split BOOLEAN,
            invalid_split_action BOOLEAN,suspected_split BOOLEAN)""")
        clean = (True, False, False, False, False, False)
        flagged = (True, False, False, True, False, False)
        c.executemany("INSERT INTO shape_price VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("one", "2024-01-03", "S", "raw", *clean),
            ("one", "2024-01-04", "S", "raw", *flagged),
        ])
        request = [{"task_id": "a", "security_id": "one", "decision_date": "2024-01-02",
                    "split": "train", "split_end": "2024-01-04", "source": "S", "basis": "raw"}]
        rows = horizon_metadata(c, request, horizon=2)
    _, public = summarize(request, rows, horizon=2)
    assert public["split_censored_tasks"] == 0
    assert public["matching_basis_complete_tasks"] == 0
    assert public["same_source_raw_complete_tasks"] == 0
    assert public["issues"]["same_source_raw_action_flag"] == 1


def test_noncontiguous_session_step_fails_closed():
    request = [{"task_id": "a", "security_id": "one", "decision_date": "2024-01-02",
                "split": "train", "source": "S", "basis": "raw"}]
    with pytest.raises(ValueError, match="noncontiguous"):
        summarize(request, [{"task_id": "a", "step": 2}], horizon=2)
