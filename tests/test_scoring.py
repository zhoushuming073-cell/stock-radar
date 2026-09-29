import numpy as np
import pandas as pd

from radar.features.scoring import ResearchConfig, score_elasticity, tradability_gate


def config():
    return ResearchConfig({"beta": .15, "atr": .20, "idio": .20,
                           "burst": .25, "hit_rate": .20}, 2, 1_000_000, 126)


def test_score_uses_only_same_date_cross_section_and_requires_all_components():
    names = ("beta", "atr", "idio", "burst", "hit")
    raw = {f"elasticity_{name}_raw": [1., 2., 3., 99., np.nan] for name in names}
    data = pd.DataFrame({"date": ["2025-01-01"] * 3 + ["2025-01-02"] * 2, **raw})
    scored = score_elasticity(data, config())
    assert np.isclose(scored.loc[0, "elasticity_score"], 100 / 3)
    assert np.isclose(scored.loc[2, "elasticity_score"], 100)
    assert np.isclose(scored.loc[3, "elasticity_score"], 100)
    assert np.isnan(scored.loc[4, "elasticity_score"])


def test_tradability_is_separate_from_elasticity():
    frame = pd.DataFrame({"close": [3, 1.9], "avg_dollar_volume_20": [2e6, 2e6],
                          "history_sessions": [126, 126]})
    assert tradability_gate(frame, config()).tolist() == [True, False]


def test_historical_gate_ignores_mutable_current_asset_metadata():
    frame = pd.DataFrame({"close": [3, 3], "avg_dollar_volume_20": [2e6, 2e6],
                          "history_sessions": [126, 126],
                          "tradable": [False, True], "exchange": ["OTC", "NYSE"]})
    assert tradability_gate(frame, config()).tolist() == [True, True]
