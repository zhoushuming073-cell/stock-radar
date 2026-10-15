"""Cross-tab must conserve its exact private task population."""
import pytest

from scripts.audit_box_candidate_prefix_issuer_at_t import cross_tab


def test_cross_tab_partitions_price_status_and_issuer_state():
    clear = {"cik_count": 1, "full_window_episodes": 1,
             "bad_names": 0, "known_discontinuity": 0,
             "other_active_security_ids": 0}
    alias = {**clear, "other_active_security_ids": 1}
    rows = [{"task_id": "one", **clear}, {"task_id": "two", **alias}]
    assert cross_tab(rows, {"one": "exact_tday_match",
                            "two": "accepted_tday_missing"}) == {
        "accepted_tday_missing": {"CONTEMPORANEOUS_ISSUER_ALIAS": 1},
        "exact_tday_match": {"OBSERVATIONAL_NO_KNOWN_CONFLICT": 1},
    }
    with pytest.raises(ValueError, match="tasks differ"):
        cross_tab(rows, {"one": "exact_tday_match", "other": "accepted_tday_missing"})
