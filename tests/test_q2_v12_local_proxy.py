"""Keep the separately authorized proxy domain distinct from certified history."""
from scripts.run_q2_v12_local_proxy import ProxyEvidence, study
from radar.research.high_beta.channel import MarketEvidence, VERSION


def test_proxy_cannot_claim_historical_certification_or_change_source():
    assert ProxyEvidence().refusal() is None
    assert ProxyEvidence().model_dump()['historical_certified'] is False
    assert ProxyEvidence(historical_certified=True).refusal() == 'proxy_domain_mismatch'
    assert ProxyEvidence(feed='iex').refusal() == 'proxy_domain_mismatch'
    assert ProxyEvidence(identity_trusted=False).refusal() == 'proxy_identity_untrusted'
    original = MarketEvidence(scope='historical_verified', identity_trusted=True,
        common_stock=True, source='alpaca', feed='sip', adjustment='split',
        joint_price_volume_adjustment=True)
    assert original.refusal() == 'historical_absolute_liquidity_uncertified'


def test_study_is_fixed_v12_train_validation_proxy_only():
    contract = study()
    assert contract['selector_version'] == VERSION
    assert set(contract['intervals']) == {'train', 'validation'}
    assert 'not_certified' in contract['scope']
    assert all(start < end < settled for start, end, settled in contract['intervals'].values())
