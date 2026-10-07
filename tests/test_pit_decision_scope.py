"""Decision bounds must protect missing failed names and preserve strict inputs."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from radar.pit.decision import (competitor_interval,resolved_core,daily_top,top_stability,
                               missingness_envelope,candidate_identity,scoped_readiness,require_scoped_ready)

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def rules():
    return json.loads((ROOT/'config/pit_research_decision_rules.json').read_text())


def pass_findings():
    return {'frozen_before_analysis':True,'causal_selection_verified':True,'decision_uncertainty_bounded':True,
        'membership_crosschecks_verified':True,'maximum_daily_true_competitors':0,
        'top3_slot_overlap':1.,'identical_top3_days':1.,'maximum_unknown_changed_top3_slots':0,
        'outcomes_stable':True,'candidate_identity_unresolved':0,'candidate_execution_gaps':0,
        'candidate_material_unresolved':0,'known_split_terminal_unresolved':0,
        'feature_ranking_scope_complete':True,'ordinary_dividend_return_bound':0.,'native_input_verified':True}


def test_exact_twenty_day_liquidity_proves_noncompetitor_despite_history_gap():
    known=[('A',100.),('B',90.)]
    result=competitor_interval('missing-failed',[80.]*20,known,target=2)
    assert result['category']=='core_non_competitor' and result['best_rank']==3


def test_missing_volume_has_no_empirical_upper_bound():
    result=competitor_interval('failed',[1.]*19+[None],[('A',100.)],target=1)
    assert result['dollar_volume_upper'] is None and result['best_rank']==1
    assert result['category']=='unbounded_competitor'


def test_cutoff_tie_uses_stable_security_id():
    assert competitor_interval('Z',[100.]*20,[('A',100.)],target=1)['category']=='core_non_competitor'
    assert competitor_interval('0',[100.]*20,[('A',100.)],target=1)['best_rank']==1


def test_borderline_resolution_requires_identity_and_complete_history():
    known=[('A',100.),('B',90.)]
    item=competitor_interval('C',[95.]*20,known,target=2)
    assert not item['eligible_proven'] and resolved_core(known,[item],target=2)==['A','B']
    item=competitor_interval('C',[95.]*20,known,target=2,history_complete=True,identity_resolved=True)
    assert item['category']=='resolved_eligible_competitor'
    assert resolved_core(known,[item],target=2)==['A','C']


def test_late_identity_resolution_does_not_claim_old_eligibility():
    item=competitor_interval('C',[150.]*20,[('A',100.)],target=1,history_complete=False,identity_resolved=True)
    assert resolved_core([('A',100.)],[item],target=1)==['A']


def test_top3_uses_rank_not_label_or_future_outcome():
    rows=[{'signal_date':'d','security_id':s,'symbol':s,'rank':i,'selected':True,'label':{'future_gain':v}}
          for i,s,v in [(3,'C',100),(1,'A',-99),(2,'B',0),(4,'D',999)]]
    assert daily_top(rows,['d'])=={'d':['A','B','C']}


def test_top3_stability_counts_missing_slots_and_empty_days_separately():
    result=top_stability({'a':['A','B','C'],'b':[]},{'a':['A'],'b':[]})
    assert result['slot_overlap']==pytest.approx(1/3)
    assert result['identical_day_fraction']==.5 and result['empty_both_days']==1


def test_top3_order_change_disclosed_even_with_identical_set():
    result=top_stability({'d':['A','B']},{'d':['B','A']})
    assert result['slot_overlap']==1 and result['identical_order_fraction']==0


def test_same_missing_competitors_in_c_and_d_cannot_pass():
    top={'d':['A','B','C']}
    assert top_stability(top,top)['slot_overlap']==1
    impact=missingness_envelope(top,{'d':['failed']})
    assert impact['status']=='FAIL' and impact['maximum_daily_changed_slots']==3


def test_missingness_best_worst_excluded_are_not_filled_prices():
    result=missingness_envelope({'d':['A','B']},{'d':['failed1','failed2']})
    assert result['scenario_best']['changed_existing_slots']==0
    assert result['scenario_worst']['hit_rate_interval']==[0,1]
    assert result['scenario_excluded']['unresolved_removed']==0


def test_one_unknown_can_change_percentile_eligibility_of_all_slots():
    result=missingness_envelope({'d':['A','B','C']},{'d':['X']})
    assert result['days'][0]['independent_score_injection_displacement']==1
    assert result['maximum_daily_changed_slots']==3


def test_candidate_only_gate_ignores_unrelated_full_market_blockers(rules):
    finding={**pass_findings(),'full_market_missing':999999,'full_market_identity_unresolved':6000}
    assert scoped_readiness(finding,rules)['ready']


@pytest.mark.parametrize('field,gate',[
    ('candidate_identity_unresolved','Research identity'),('candidate_execution_gaps','Research price'),
    ('candidate_material_unresolved','Material corporate actions'),('known_split_terminal_unresolved','Terminal')])
def test_each_actual_candidate_defect_remains_blocked(rules,field,gate):
    finding=pass_findings();finding[field]=1
    assert scoped_readiness(finding,rules)['scorecard'][gate]=='FAIL'


def test_ranking_feature_gap_cannot_be_excused_by_complete_entry_prices(rules):
    finding=pass_findings();finding['feature_ranking_scope_complete']=False
    assert scoped_readiness(finding,rules)['scorecard']['Research price']=='FAIL'


def test_unresolved_decision_input_not_causally_irrelevant(rules):
    finding=pass_findings();finding['decision_uncertainty_bounded']=False
    assert scoped_readiness(finding,rules)['scorecard']['Causal integrity']=='FAIL'


def test_pre_return_freeze_required(rules):
    finding=pass_findings();finding['frozen_before_analysis']=False
    with pytest.raises(ValueError,match='BLOCKED'):require_scoped_ready(finding,rules)


def test_ordinary_cash_budget_is_not_final_portfolio_bound(rules):
    finding=pass_findings();finding['ordinary_dividend_return_bound']=None
    assert scoped_readiness(finding,rules)['scorecard']['Material corporate actions']=='FAIL'


def test_no_current_fallback_when_scoped_native_gate_fails(rules):
    finding=pass_findings();finding['native_input_verified']=False
    with pytest.raises(ValueError,match='no Current fallback'):require_scoped_ready(finding,rules)


def test_explicit_class_does_not_waive_multiple_issuer_reuse(rules):
    from test_pit_research_grade import record
    base=json.loads((ROOT/'config/pit_research_grade_rules.json').read_text())
    r=record();r['mappings'][0].update(security_name='Example Class A Common Stock',
        first_source_commit='early',last_source_commit='late')
    risk={'strict_verified':False,'reasons':['ticker has multiple observed identity episodes'],'lifecycle_disappearance':False}
    observations=[{'cik':'1','name':'Example','available_on':'2024-01-01'},
                  {'cik':'2','name':'Example','available_on':'2024-02-01'}]
    assert not candidate_identity(r,observations,risk,base)['pass']


@pytest.mark.skipif(os.environ.get('STOCK_RADAR_TEST_LEAN')!='1',reason='explicit real engine opt-in')
def test_scoped_pass_routes_to_existing_native_research_fixture_and_reconciliation(tmp_path,rules):
    # Real Native engine with a fixture verifies coupling; not actual Strategy 2 acceptance.
    from test_pit_research_grade import test_native_research_grade_reconciliation_and_label
    require_scoped_ready(pass_findings(),rules)
    base=json.loads((ROOT/'config/pit_research_grade_rules.json').read_text())
    test_native_research_grade_reconciliation_and_label(tmp_path,base)
