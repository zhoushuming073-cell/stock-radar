from types import SimpleNamespace

import pandas as pd

from radar.research.event_study import causal_liquid


def test_current_asset_status_mutation_cannot_change_historical_factor_sample():
    frame = pd.DataFrame({"symbol": ["AAA", "BBB", "CCC"],
                          "close": [10., 10., 1.],
                          "avg_dollar_volume_20": [1_000_000.] * 3,
                          "tradability_pass": [True, False, True],
                          "tradable": [False, True, True],
                          "exchange": ["OTC", "NASDAQ", "NYSE"]})
    gate = SimpleNamespace(min_price=2., min_avg_dollar_volume_20=100_000.)
    selected = causal_liquid(frame, gate)
    changed = frame.assign(tradable=~frame.tradable, exchange="FUTURE")
    assert selected.symbol.tolist() == ["AAA"]
    assert causal_liquid(changed, gate).symbol.tolist() == ["AAA"]
