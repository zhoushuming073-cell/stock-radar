from pathlib import Path

import pandas as pd
import yaml

from radar.research.cost_sensitivity import illustrative_net_returns


CONFIG = yaml.safe_load((Path(__file__).parents[1] / "config" / "research.yaml").read_text(
    encoding="utf-8"))["illustrative_costs"]


def test_both_side_fees_and_slippage_reduce_reference_return():
    buy = pd.Series([100.0])
    sell = pd.Series([105.0])
    no_slip = illustrative_net_returns(buy, sell, CONFIG, slippage_bps=0).iloc[0]
    with_slip = illustrative_net_returns(buy, sell, CONFIG, slippage_bps=20).iloc[0]
    assert 0 < with_slip < no_slip < 0.05


def test_missing_exit_does_not_create_a_net_outcome():
    result = illustrative_net_returns(pd.Series([100.0]), pd.Series([float("nan")]),
                                      CONFIG, slippage_bps=0)
    assert pd.isna(result.iloc[0])
