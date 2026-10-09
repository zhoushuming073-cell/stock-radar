from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from radar.research.parallel_channel import ChannelSettings, _aggregate, _fit, analyze


def fixture_daily(kind: str = "range", seed: int = 7) -> pd.DataFrame:
    """Synthetic candles, NOT historical returns or ground-truth stock labels."""
    rng = np.random.default_rng(seed)
    n = 450
    t = np.arange(n)
    if kind == "range":
        mid = 40 + 6.4 * np.sin(2 * np.pi * t / 56)
    elif kind == "down":
        mid = 80 * np.exp(-0.0046 * t) + 2.0 * np.sin(t / 10)
    elif kind == "rally":
        mid = 12 * np.exp(0.0043 * t)
    else:
        raise ValueError(kind)
    close = mid + rng.normal(0, 0.42, n)
    close = np.maximum(close, 0.01)
    op = np.maximum(close + rng.normal(0, 0.3, n), 0.01)
    high = np.maximum(op, close) + rng.uniform(0.3, 1.0, n)
    low = np.minimum(op, close) - rng.uniform(0.3, 1.0, n)
    return pd.DataFrame({"date": pd.bdate_range("2024-07-01", periods=n),
                         "open": op, "high": high, "low": low, "close": close,
                         "volume": np.full(n, 1_000_000)})


def test_clear_channel_beats_monotonic_trends():
    a = fixture_daily()
    b = fixture_daily("down")
    c = fixture_daily("rally")
    for frame in (a, b, c):
        frame["volume"] = 2_000_000
    ra = analyze(a, a.date.iloc[-1])
    rb = analyze(b, b.date.iloc[-1])
    rc = analyze(c, c.date.iloc[-1])
    assert ra["qualified"]
    assert not rb["qualified"]
    assert not rc["qualified"]
    assert ra["channel"]["support_touches"] >= 2
    assert ra["channel"]["resistance_touches"] >= 2
    assert ra["channel"]["alternations"] >= 2


def test_historical_future_has_no_influence():
    x = fixture_daily()
    t = x.date.iloc[-16]
    r = analyze(x, t)
    y = x.copy()
    y.loc[y.date > t, ["open", "high", "low", "close", "volume"]] *= 50
    assert analyze(y, t) == r


def test_partial_month_and_week_use_only_past_daily():
    a = fixture_daily()
    t = a.date.iloc[-15]
    x = a.loc[a.date <= t]
    assert _aggregate(x, "ME").iloc[-1].close == x.iloc[-1].close
    assert _aggregate(x, "W-FRI").iloc[-1].close == x.iloc[-1].close


def test_invalid_or_duplicate_bars_fail_closed():
    x = fixture_daily()
    t = x.date.iloc[-1]
    with pytest.raises(ValueError):
        analyze(pd.concat([x, x.iloc[[-1]]]), t)
    bad = x.copy()
    bad.loc[12, "high"] = bad.loc[12, "low"] - 1
    with pytest.raises(ValueError):
        analyze(bad, t)
    bad = x.copy()
    bad.loc[90, "close"] = np.nan
    with pytest.raises(ValueError):
        analyze(bad, t)
    with pytest.raises(ValueError):
        analyze(x.iloc[:100], x.date.iloc[99])


def test_latest_trading_session_required():
    x = fixture_daily()
    with pytest.raises(ValueError, match="decision session"):
        analyze(x, x.date.iloc[-1] + pd.Timedelta(days=8))


def test_no_trading_decision_or_false_allegation_of_buying():
    x = fixture_daily()
    r = analyze(x, x.date.iloc[-1])
    assert "orders" not in r
    if r["qualified"]:
        assert r["daily"]["stage"] in ("breakdown", "early_reversal", "near_lower_wait", "not_near_lower")
        assert 0 <= r["rank_score"] <= 100


def test_entry_position_setting_changes_classification():
    from radar.research.parallel_channel import _daily
    x = fixture_daily()
    low, up = 30., 55.
    tight = _daily(x, low, up, ChannelSettings(max_entry_position=.01))
    wide = _daily(x, low, up, ChannelSettings(max_entry_position=.90))
    assert tight["stage"] == "not_near_lower"
    assert wide["stage"] in ("near_lower_wait", "early_reversal")
