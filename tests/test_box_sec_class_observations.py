import pytest

from scripts.audit_box_sec_class_observations import check_review


def test_sec_class_review_requires_exact_mapping_and_pre_t_filing():
    row = {"symbol": "ABC", "observed_cik": "0001234567", "form": "10-K",
           "class_observed": "Common Stock", "exchange_observed": "NYSE",
           "filing_date": "2025-02-20", "earliest_candidate_date": "2025-05-06",
           "filing_url": "https://www.sec.gov/Archives/edgar/data/1234567/0001/abc.htm"}
    check_review(row, "2025-05-06", "ABC", "0001234567")
    for changed in ({**row, "symbol": "XYZ"},
                    {**row, "filing_date": "2025-05-06"},
                    {**row, "observed_cik": "0001234568"},
                    {**row, "class_observed": "Preferred Stock"},
                    {**row, "exchange_observed": "unknown"},
                    {**row, "filing_url": row["filing_url"].replace("www.sec.gov", "example.com")},
                    {**row, "filing_url": row["filing_url"].replace("1234567", "1234568")},
                    {**row, "earliest_candidate_date": "2025-05-07"}):
        with pytest.raises(ValueError):
            check_review(changed, "2025-05-06", "ABC", "0001234567")
