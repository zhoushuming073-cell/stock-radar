from scripts.audit_box_accepted_price_parity import classify
from scripts.audit_box_candidate_tday_price_bridge import ACCEPTED_PROVENANCE


def test_same_source_price_parity_requires_exact_single_row():
    shape = [("ABC", 1.0, 2.0, 0.5, 1.5, 100.0)]
    accepted = [(*shape[0], *ACCEPTED_PROVENANCE)]
    assert classify(shape, accepted) == "exact"
    assert classify([], accepted) == "shape_missing"
    assert classify(shape, []) == "accepted_missing"
    assert classify(shape * 2, accepted) == "shape_nonunique"
    assert classify(shape, accepted * 2) == "accepted_nonunique"
    assert classify(shape, [(*shape[0], "other", "feed", "raw")]) == "accepted_provenance_mismatch"
    assert classify(shape, [("XYZ", *shape[0][1:], *ACCEPTED_PROVENANCE)]) == "symbol_mismatch"
    assert classify(shape, [("ABC", 1.0, 2.0, 0.5, 1.6, 100.0,
                             *ACCEPTED_PROVENANCE)]) == "ohlcv_mismatch"
