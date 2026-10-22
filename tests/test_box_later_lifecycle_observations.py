import pytest

from scripts.audit_box_later_lifecycle_observations import summarize


def test_later_lifecycle_does_not_replace_process_window():
    symbols = [f"S{i}" for i in range(28)]
    queue = {"rows": [{"symbol": symbols[i % 28]} for i in range(142)],
             "formal_lean_ready": False}
    def request(start, end):
        return {"start": start, "end": end, "limit": 1000,
                "ca_types": None, "symbols": symbols}
    cash = {"id": "a", "symbol": "S0", "corporate_action_type": "cash_dividends",
            "process_date": "2025-06-01"}
    merger = {"id": "b", "acquiree_symbol": "S1",
              "corporate_action_type": "cash_mergers", "process_date": "2025-10-01"}
    short = {"request": request("2025-05-01", "2025-09-08"),
             "announcements": {"cash_dividends": [cash]}}
    annual = {"request": request("2025-01-01", "2025-12-31"),
              "announcements": {"cash_dividends": [cash],
                                "cash_mergers": [merger]}}
    result = summarize(queue, short, annual)
    assert result["noncash_events_through_validation_end"] == 0
    assert result["noncash_events_after_validation_end"] == 1
    assert result["later_event_candidate_days"] == 6
    with pytest.raises(ValueError):
        summarize(queue, short, {**annual, "announcements": {"cash_mergers": [merger]}})
