"""Real evidence scopes plus adversarial identity/price acceptance failures."""
from copy import deepcopy
from pathlib import Path
import json

import pandas as pd
import pytest

from radar.pit.trust import enrich, load_catalog, episode_candidates
from radar.pit.builder import digest

ROOT = Path(__file__).resolve().parents[1]


def observations():
    # Factual observations from the first accepted master, not fictional tickers.
    frame = pd.read_csv(ROOT/'tests/fixtures/pit-real-observations.csv',keep_default_na=False)
    frame['eligible'] = frame.eligible.astype(str).str.lower().eq('true')
    return frame


def catalog():
    return load_catalog(ROOT/'config/pit_trust_evidence.json')


def test_real_bbby_reuse_and_overstock_rename_are_different_issuers():
    f,r = enrich(observations(),catalog())
    old = f[f.symbol.eq('BBBY') & f.exchange.eq('NASDAQ')].iloc[0]
    new = f[f.symbol.eq('BBBY') & f.exchange.eq('NYSE')]
    assert old.security_id == 'SEC-0000886158-COMMON'
    assert set(new.security_id) == {'SEC-0001130713-COMMON'}
    assert set(f[f.symbol.isin(['OSTK','BYON'])].security_id) == set(new.security_id)
    assert set(f[f.symbol.eq('BYON')].security_type) == {'common'}
    assert new.valid_from.min() == '2025-08-29'
    assert f[f.symbol.eq('BYON')].valid_to.max() == '2025-08-28'
    assert any(x['issue_type']=='ticker_reuse' for x in r['conflicts'])


def test_real_trading_suspensions_do_not_become_legal_delisting_or_payout():
    f,r = enrich(observations(),catalog())
    assert f[f.symbol.eq('ATVI')].valid_to.max() == '2023-10-12'
    assert f[f.symbol.eq('TWTR')].valid_to.max() == '2022-10-27'
    assert f[f.symbol.eq('SPLK')].valid_to.max() == '2024-03-15'
    assert f[f.symbol.eq('BBBY') & f.exchange.eq('NASDAQ')].valid_to.max() == '2023-05-02'
    assert f.delisting_date.eq('').all()
    assert all(e['terminal_economics']=='unresolved_not_enabled' for e in r['events'])
    assert all(e.get('settlement_model_verified') is False for e in r['events'] if 'documented_cash_consideration' in e)


def test_real_pltr_transfer_fb_meta_class_and_adr_exclusion():
    f,_ = enrich(observations(),catalog())
    assert f[f.symbol.eq('PLTR') & f.exchange.eq('NYSE')].valid_to.max() == '2024-11-25'
    assert f[f.symbol.eq('PLTR') & f.exchange.eq('NASDAQ')].valid_from.min() == '2024-11-26'
    assert set(f[f.symbol.eq('PLTR')].security_id) == {'SEC-0001321655-CLASS-A'}
    scoped = f[f.symbol.isin(['FB','META']) & f.security_name.str.contains('Class A')]
    assert set(scoped.security_id) == {'SEC-0001326801-CLASS-A'}
    baba = f[f.symbol.eq('BABA')].iloc[0]
    assert baba.security_type == 'adr' and not baba.eligible
    assert baba.classification_confidence == 'verified'
    split = next(e for e in catalog()['events'] if e['event_type']=='split')
    assert split['effective_date']=='2024-06-10' and split['to_factor']==10
    assert split['legal_effective'].startswith('2024-06-07')
    assert split['factor_series_verified'] is False


def test_candidate_similarity_never_merges_and_replay_is_deterministic():
    f = observations()
    c = catalog()
    a,r = enrich(f,c)
    b,s = enrich(f,c)
    assert a.to_csv(index=False)==b.to_csv(index=False) and digest(r)==digest(s)
    c['mappings'] = [dict(m,confidence='strongly_supported') for m in c['mappings']]
    unchanged,_ = enrich(f,c)
    assert list(unchanged.security_id)==list(f.sort_values(['symbol','valid_from','security_id']).security_id)
    assert any(x['resolution_status']=='unresolved' for x in episode_candidates(f))


@pytest.mark.parametrize('mutation',['class','scope','hash','status'])
def test_invalid_identity_catalog_cannot_certify_a_merge(tmp_path,mutation):
    c = deepcopy(catalog())
    if mutation=='class':
        c['mappings'][1]['share_class']='CLASS-B'
    elif mutation=='scope':
        c['mappings'][1]['valid_from']='2022-06-08'
    elif mutation=='hash':
        c['sources']['fb']['raw_sha256']='missing'
    else:
        c['mappings'][0]['confidence']='certain'
    p=tmp_path/'catalog.json';p.write_text(json.dumps(c))
    with pytest.raises(ValueError):load_catalog(p)


def test_raw_evidence_mutation_is_rejected(tmp_path):
    c = catalog()
    for source in c['sources'].values():
        (tmp_path/(source['raw_sha256']+'.raw')).write_bytes(b'altered disclosure')
    with pytest.raises(ValueError,match='raw hash mismatch'):
        load_catalog(ROOT/'config/pit_trust_evidence.json',tmp_path)


def test_unknown_classification_stays_ineligible():
    f=observations();f.loc[0,['symbol','security_type','eligible']]=['UNMATCHED','unknown',False]
    a,_=enrich(f,catalog())
    row=a[a.symbol.eq('UNMATCHED')].iloc[0]
    assert row.security_type=='unknown' and not row.eligible
