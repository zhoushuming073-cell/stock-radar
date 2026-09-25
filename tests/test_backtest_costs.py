"""Tests for the auditable per-order fee breakdown."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from radar.backtest.costs import buy_cost, load_fee_config, sell_cost

CONFIG_PATH = Path(__file__).parents[1] / "config" / "research.yaml"
CFG = load_fee_config(CONFIG_PATH)


def test_config_loads_the_illustrative_schedule():
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["illustrative_costs"]

    assert CFG.profile == raw["profile"]
    assert CFG.commission_per_share == raw["commission_per_share"]
    assert CFG.platform_min == raw["platform_min"]
    assert CFG.finra_sell_max == raw["finra_sell_max"]
    assert CFG.slippage_bps_per_side == tuple(raw["slippage_bps_per_side"])


def test_config_without_the_fee_section_is_rejected(tmp_path):
    path = tmp_path / "research.yaml"
    path.write_text("research:\n  train_fraction: 0.6\n", encoding="utf-8")

    with pytest.raises(ValueError, match="illustrative_costs"):
        load_fee_config(path)


def test_config_with_a_missing_fee_key_is_rejected(tmp_path):
    path = tmp_path / "research.yaml"
    path.write_text(
        "illustrative_costs:\n"
        "  profile: test_profile\n"
        "  order_notional_usd: 10000\n"
        "  slippage_bps_per_side: [0, 5]\n"
        "  commission_per_share: 0.01\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="commission_min"):
        load_fee_config(path)


def test_buy_charges_per_share_fees_and_no_sell_side_fees():
    fees = buy_cost(100.0, 100, CFG)

    assert fees.notional == 10_000.0
    assert fees.commission == 1.00      # 100 * 0.01, above the 1.00 minimum
    assert fees.platform == 2.88        # 100 * 0.009 = 0.90, below the 2.88 minimum
    assert fees.settlement == 0.30
    assert fees.cat == 0.01             # 100 * 0.000003, below the 0.01 minimum
    assert fees.sec == 0.0
    assert fees.finra == 0.0
    assert fees.total == 4.19


def test_sell_adds_sec_finra_and_cat_on_top_of_the_buy_components():
    buy = buy_cost(100.0, 100, CFG)
    sell = sell_cost(100.0, 100, CFG)

    assert sell.commission == buy.commission
    assert sell.platform == buy.platform
    assert sell.settlement == buy.settlement
    assert sell.sec == 0.206            # 10_000 * 0.0000206, above the 0.01 minimum
    assert sell.finra == 0.0195         # 100 * 0.000195, above the 0.01 minimum
    assert sell.cat == buy.cat
    assert sell.total == pytest.approx(4.4155)


def test_total_is_the_sum_of_every_component():
    for fees in (buy_cost(100.0, 100, CFG), sell_cost(100.0, 100, CFG)):
        assert fees.total == pytest.approx(
            fees.commission + fees.platform + fees.settlement + fees.sec + fees.finra + fees.cat)


def test_notional_cap_binds_below_the_minimum_for_a_cheap_order():
    fees = buy_cost(5.0, 1, CFG)

    assert fees.notional == 5.0
    assert fees.commission == 0.025     # 5 * 0.005, below the 1.00 minimum
    assert fees.platform == 0.025       # 5 * 0.005, below the 2.88 minimum
    assert fees.settlement == 0.01      # 1 * 0.003 floor -> 0.01 minimum, cap not binding
    assert fees.cat == 0.01


def test_per_share_cap_binds_when_the_rate_is_large():
    cfg = replace(CFG, platform_per_share=0.5)

    fees = buy_cost(10.0, 1_000, cfg)

    assert fees.platform == 50.0        # 10_000 * 0.005, below 1_000 * 0.5


def test_finra_taf_is_capped_at_its_maximum():
    fees = sell_cost(1.0, 1_000_000, CFG)

    assert fees.finra == CFG.finra_sell_max == 9.79


def test_fees_scale_with_quantity_and_are_reported_in_bps():
    small = buy_cost(100.0, 100, CFG)
    large = buy_cost(100.0, 400, CFG)

    assert large.total > small.total
    assert large.total_bps < small.total_bps   # fixed platform minimum spreads out
    assert small.total_bps == pytest.approx(4.19 / 10_000 * 10_000)


@pytest.mark.parametrize("price,quantity", [(0.0, 10), (-1.0, 10), (100.0, 0), (100.0, -5),
                                            (float("nan"), 10), (100.0, float("inf"))])
def test_non_positive_inputs_are_rejected(price, quantity):
    with pytest.raises(ValueError):
        buy_cost(price, quantity, CFG)
    with pytest.raises(ValueError):
        sell_cost(price, quantity, CFG)
