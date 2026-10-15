"""Three independent gate populations must match before intersection."""
import pytest

from scripts.audit_box_candidate_prefix_data_gates import aggregate_gates


def _issuer(task: str) -> dict:
    return {"task_id": task, "cik_count": 1, "full_window_episodes": 1,
            "bad_names": 0, "known_discontinuity": 0,
            "other_active_security_ids": 0}


def _horizon(task: str, complete: bool) -> dict:
    return {"task_id": task, "complete_horizon_within_split": complete,
            "sessions": ([{"same_source_raw_rows": 1, "raw_ready": True,
                           "raw_identity_flag": False, "raw_split_flag": False}]
                         * 10 if complete else [])}


def test_three_way_intersection_preserves_tasks_and_raw_gate():
    table = aggregate_gates(
        {"one": "exact_tday_match", "two": "accepted_tday_missing"},
        [_issuer("one"), _issuer("two")],
        [_horizon("one", True), _horizon("two", False)])
    assert table["exact_tday_match"]["OBSERVATIONAL_NO_KNOWN_CONFLICT"] == {
        "raw_metadata_complete": 1, "raw_metadata_incomplete": 0}
    assert table["accepted_tday_missing"]["OBSERVATIONAL_NO_KNOWN_CONFLICT"] == {
        "raw_metadata_complete": 0, "raw_metadata_incomplete": 1}
    with pytest.raises(ValueError, match="populations differ"):
        aggregate_gates({"one": "exact_tday_match"}, [_issuer("one")],
                        [_horizon("other", True)])
