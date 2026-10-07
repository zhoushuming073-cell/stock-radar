import pytest
from radar.pit.decision_bounds import short_history_proof,executable_raw_bar,score_stress,holding_mapping_gaps


def fact():
    return {'available_on':'2024-01-02','issuer_name':'New Company','first_trading':'2024-01-02','source_sha256':'official'}


def test_known_ipo_exclusion_independent_of_missing_prices():
    proof=short_history_proof('2024-01-04',fact(),['2024-01-02','2024-01-03','2024-01-04'],'New Company Common Stock')
    assert proof['maximum_possible_sessions']==2 and proof['status']=='core_non_competitor'


def test_future_ipo_evidence_cannot_filter_past_members():
    f=fact();f['available_on']='2024-01-05'
    assert short_history_proof('2024-01-04',f,[], 'New Company') is None


def test_same_ticker_old_issuer_not_excluded_by_new_ipo():
    assert short_history_proof('2024-01-04',fact(),[], 'Old Issuer') is None


def test_zero_volume_authentic_provider_quote_not_executable():
    row={'open':13.57,'high':13.57,'low':13.57,'close':13.57,'volume':0,'adjustment':'raw'}
    assert not executable_raw_bar(row)
    row['volume']=100
    assert executable_raw_bar(row)


def test_adjusted_gap_candidate_cannot_be_used_as_raw():
    assert not executable_raw_bar({'open':10,'high':11,'low':9,'close':10,'volume':10,'adjustment':'split'})


def test_missingness_score_witness_preserves_cap_and_all_top3_can_change():
    rows=[{'signal_date':'d','security_id':s,'symbol':s,'strategy_score':80-i,'selected':True} for i,s in enumerate('ABC')]
    result=score_stress(rows,{'d':['X','Y','Z']},{'d':['A','B','C','D','E']})
    assert result['maximum_changed_slots']==3 and result['days'][0]['best']==['A','B','C']
    assert result['days'][0]['excluded']==result['days'][0]['best']
    assert result['days'][0]['unknown_outcome_interval']==[0,1]


def test_no_unknown_score_stress_matches_actual_selection():
    rows=[{'signal_date':'d','security_id':'A','symbol':'A','strategy_score':80,'selected':True}]
    result=score_stress(rows,{}, {'d':['A']})
    assert result['changed_days']==0 and result['maximum_changed_slots']==0


def test_exchange_or_name_interval_end_is_not_terminal():
    mappings=[{'valid_from':'2024-01-01','valid_to':'2024-12-01'},
              {'valid_from':'2024-12-02','valid_to':None}]
    assert holding_mapping_gaps(mappings,['2024-12-01','2024-12-02','2025-01-02'])==[]


def test_real_unbound_holding_interval_remains_lifecycle_unknown():
    assert holding_mapping_gaps([{'valid_from':'2024-01-01','valid_to':'2024-12-01'}],['2024-12-02'])==['2024-12-02']
