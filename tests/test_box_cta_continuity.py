from scripts.audit_box_cta_continuity import classify


def _row(market="N", instrument="0", **extra):
    return {"PrimaryListingMarketParticipantID": market,
            "InstrumentType": instrument, "HaltReason": " ",
            "Test": "0", "IPO": "0", "FinancialStatusIndicator": "0",
            **extra}


def test_cta_continuity_flags_absence_and_symbol_market_class_drift():
    assert classify("ABC", "ABC", _row(), _row()) == set()
    assert classify("ABC", "XYZ", _row(), _row(market="Q", instrument="1")) == {
        "source_symbol_changed", "listing_market_changed", "instrument_type_changed",
        "listing_market_not_nyse", "instrument_not_cta_equity"}
    assert classify("ABC", "ABC", None, None) == {
        "t_cta_symbol_absent", "cta_symbol_absent"}
    assert classify("ABC", "ABC", _row(), None) == {"cta_symbol_absent"}
    assert classify("ABC", "ABC", _row(), _row(HaltReason="H", Test="1")) == {
        "halt_reason_present", "test_flag_nonzero"}
