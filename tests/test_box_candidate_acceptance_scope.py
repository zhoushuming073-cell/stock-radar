"""Missing accepted rows must not all be called missing raw data."""
from scripts.audit_box_candidate_acceptance_scope import scope_classification


def test_scope_partition_and_overlapping_retrospective_gates():
    assert scope_classification(None) == ("outside_original_dependency", ())
    category, flags = scope_classification({
        "research_identity_pass": False,
        "material_review_required": True,
        "source_price_conflict": False,
    })
    assert category == "inside_dependency_rejected_by_whole_closure_gate"
    assert flags == ("whole_closure_identity_fail", "whole_closure_material_review")
    assert scope_classification({
        "research_identity_pass": True,
        "material_review_required": False,
        "source_price_conflict": False,
    }) == ("inside_dependency_gates_passed_but_tday_not_accepted", ())
