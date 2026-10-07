"""Real rename/split boundary facts in non-executable format examples."""
from decimal import Decimal
from radar.pit.lean_plan import mapped_symbol,factor_row,execution_design_status


def test_real_fb_meta_map_uses_end_dates_not_effective_start_dates():
    rows=['20210901,fb','20220608,fb','20501231,meta']
    assert mapped_symbol(rows,'2022-06-08')=='fb'
    assert mapped_symbol(rows,'2022-06-09')=='meta'
    assert execution_design_status()['execution_ready'] is False


def test_real_split_fact_does_not_claim_complete_dividend_factors():
    example=factor_row('20240607,1,0.1,1208.88')
    assert example['split_factor']==Decimal('0.1') and example['reference_price']==Decimal('1208.88')
    status=execution_design_status()
    assert not status['execution_ready'] and 'unresolved' in status['terminal_policy']
