import pytest

from scripts.audit_box_alpaca_action_crosscheck import compare


def test_alpaca_action_crosscheck_rejects_absence_amount_and_duplicate():
    event = {"symbol": "ABC", "ex_date": "2025-06-05",
             "rate": 0.1875, "corporate_action_type": "cash_dividends"}
    source = {("ABC", "2025-06-05"): [{"amount": 0.1875}]}
    assert compare([event], source, {"ABC"})["dolt_exact_symbol_exdate_amount_matches"] == 1
    for rows, scan in (([event, event], source),
                       ([event], {}),
                       ([event], {("ABC", "2025-06-05"): [{"amount": 0.18}]})):
        with pytest.raises(ValueError):
            compare(rows, scan, {"ABC"})
