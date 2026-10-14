"""Stage B isolation and immutable selection gates."""
import json

import duckdb
import pytest

from scripts.audit_box_range_stage_b_identity import (
    as_of_t_evidence, window_episode_evidence,
)
from radar.box_labeling.stage_b import (
    EXCLUDED_SYMBOLS, VERSION, digest, freeze_blind_pool,
    materialize_blind_tasks, packed,
)


def test_private_selection_serialization_is_stable():
    a = {"version": VERSION, "rows": [{"b": 2, "a": 1}]}
    b = {"rows": [{"a": 1, "b": 2}], "version": VERSION}
    assert packed(a) == packed(b)
    assert digest(packed(a)) == digest(packed(b))
    assert len(EXCLUDED_SYMBOLS) == 6


def test_prior_manifest_is_required_before_research_access(tmp_path):
    with pytest.raises(FileNotFoundError, match="prior label manifest"):
        freeze_blind_pool(tmp_path, tmp_path / "selection.json",
                          tmp_path / "missing.json")


def test_frozen_selection_cannot_be_replaced(tmp_path):
    selection = tmp_path / "selection.json"
    selection.write_bytes(b"frozen")
    with pytest.raises(FileExistsError, match="already frozen"):
        freeze_blind_pool(tmp_path, selection, tmp_path / "missing.json")


def test_materialization_rejects_wrong_hash_before_writing(tmp_path):
    selection = tmp_path / "selection.json"
    selection.write_bytes(packed({"version": VERSION,
                                  "selection_precedes_detector": True,
                                  "rows": []}))
    output = tmp_path / "tasks"
    with pytest.raises(ValueError, match="selection receipt changed"):
        materialize_blind_tasks(tmp_path, selection, output, "0" * 64)
    assert not output.exists()


def test_materialization_rejects_unfrozen_selection(tmp_path):
    selection = tmp_path / "selection.json"
    selection.write_bytes(packed({"version": VERSION,
                                  "selection_precedes_detector": False,
                                  "rows": []}))
    with pytest.raises(ValueError, match="unfrozen"):
        materialize_blind_tasks(tmp_path, selection, tmp_path / "tasks",
                                digest(selection.read_bytes()))


def test_materialization_preserves_existing_tasks(tmp_path):
    selection = tmp_path / "selection.json"
    selection.write_bytes(packed({"version": VERSION,
                                  "selection_precedes_detector": True,
                                  "rows": []}))
    output = tmp_path / "tasks"
    output.mkdir()
    (output / "manifest.json").write_text(json.dumps([]))
    with pytest.raises(FileExistsError, match="already exists"):
        materialize_blind_tasks(tmp_path, selection, output,
                                digest(selection.read_bytes()))


def test_issuer_name_conflicts_are_classified_at_frozen_t():
    with duckdb.connect() as connection:
        connection.execute("""CREATE TABLE issuer_evidence (
            security_id VARCHAR, cik VARCHAR, available_on DATE,
            name_compatible BOOLEAN)""")
        connection.executemany("INSERT INTO issuer_evidence VALUES (?, ?, ?, ?)", [
            ("future-only", "1", "2022-01-01", True),
            ("future-only", "1", "2023-01-01", False),
            ("old-name", "2", "2022-01-01", False),
            ("old-name", "2", "2023-01-01", True),
        ])
        rows = as_of_t_evidence(connection, [
            {"security_id": "future-only", "decision_date": "2022-06-01"},
            {"security_id": "old-name", "decision_date": "2022-06-01"},
        ])
    assert {row[0]: row[1:] for row in rows} == {
        "future-only": (1, 0, 1),
        "old-name": (1, 1, 0),
    }


def test_window_issuer_audit_detects_episode_boundary_and_future_cik():
    with duckdb.connect() as connection:
        connection.execute("""CREATE TABLE ticker_episode (
            security_id VARCHAR, interval_id VARCHAR, symbol VARCHAR,
            valid_from DATE, valid_to DATE)""")
        connection.execute("""CREATE TABLE issuer_evidence (
            security_id VARCHAR, interval_id VARCHAR, cik VARCHAR,
            available_on DATE)""")
        connection.executemany("INSERT INTO ticker_episode VALUES (?, ?, ?, ?, ?)", [
            ("single", "e1", "AAA", "2020-01-01", "2023-12-31"),
            ("cross", "e2", "OLD", "2020-01-01", "2022-03-31"),
            ("cross", "e3", "NEW", "2022-04-01", "2023-12-31"),
            ("future", "e4", "FUT", "2023-01-01", "2023-12-31"),
        ])
        connection.executemany("INSERT INTO issuer_evidence VALUES (?, ?, ?, ?)", [
            ("single", "e1", "1", "2022-01-01"),
            ("single", "e1", "9", "2023-01-01"),
            ("cross", "e2", "2", "2022-01-01"),
            ("cross", "e3", "2", "2022-04-01"),
            ("future", "e4", "4", "2023-01-01"),
        ])
        rows = window_episode_evidence(connection, [
            {"security_id": "single", "window_start": "2022-01-01",
             "decision_date": "2022-06-01"},
            {"security_id": "cross", "window_start": "2022-01-01",
             "decision_date": "2022-06-01"},
            {"security_id": "future", "window_start": "2022-01-01",
             "decision_date": "2022-06-01"},
        ])
    assert {row[0]: row[1:] for row in rows} == {
        "single": (1, 1, 1),
        "cross": (2, 2, 1),
        "future": (0, 0, 0),
    }
