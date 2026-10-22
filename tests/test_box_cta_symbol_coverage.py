import json

import pytest

from scripts.audit_box_cta_symbol_coverage import compare, parse_cta


HEADER = "Symbol,PrimaryListingMarketParticipantID,InstrumentType\n"


def test_cta_symbols_are_case_sensitive_and_date_bound(tmp_path):
    path = tmp_path / "CTA.Symbol.File.20250701.csv"
    path.write_text(HEADER + "TPC,N,0\nTpC,N,0\n", encoding="utf-8")
    rows = parse_cta(path, "2025-07-01")
    assert set(rows) == {"TPC", "TpC"}
    with pytest.raises(ValueError, match="filename/date"):
        parse_cta(path, "2025-07-02")
    path.write_text(HEADER + "TPC,N,0\nTPC,N,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        parse_cta(path, "2025-07-01")


def test_aggregate_never_exposes_private_security_id():
    private_id = "private-security-id-123"
    request = {"security_id": private_id, "source": "Dolt:example",
               "basis": "raw"}
    cta = {"TPC": {"PrimaryListingMarketParticipantID": "N",
                   "InstrumentType": "0"}}
    result = compare([request], {(private_id, "Dolt:example", "raw"): "TPC"}, cta)
    assert result["by_source_basis"][0]["status"] == "cta_symbol_present"
    assert result["matched_listing_market_codes"] == {"N": 1}
    assert private_id not in json.dumps(result)
    with pytest.raises(ValueError, match="population differs"):
        compare([request], {}, cta)
