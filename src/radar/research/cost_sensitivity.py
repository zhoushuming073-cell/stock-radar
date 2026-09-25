"""Illustrative per-trade US-stock fee and slippage sensitivity.

This is an event-study scenario using a fixed order notional. The user's actual
fee plan and portfolio sizing remain unconfirmed; this is not a portfolio PnL.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _capped_per_share(quantity, notional, per_share, minimum, cap_fraction):
    return np.minimum(np.maximum(quantity * per_share, minimum),
                      notional * cap_fraction)


def illustrative_net_returns(
    entry_open: pd.Series, exit_price: pd.Series, cfg: dict, *, slippage_bps: float,
) -> pd.Series:
    """One whole-share buy and sell at references with fees on each side."""
    entry = entry_open.to_numpy(dtype=float)
    exit_ = exit_price.to_numpy(dtype=float)
    slip = slippage_bps / 10_000
    buy = entry * (1 + slip)
    sell = exit_ * (1 - slip)
    quantity = np.floor(float(cfg["order_notional_usd"]) / buy)
    buy_notional = quantity * buy
    sell_notional = quantity * sell
    commission_buy = _capped_per_share(
        quantity, buy_notional, cfg["commission_per_share"], cfg["commission_min"],
        cfg["commission_cap_notional_fraction"])
    commission_sell = _capped_per_share(
        quantity, sell_notional, cfg["commission_per_share"], cfg["commission_min"],
        cfg["commission_cap_notional_fraction"])
    platform_buy = _capped_per_share(
        quantity, buy_notional, cfg["platform_per_share"], cfg["platform_min"],
        cfg["platform_cap_notional_fraction"])
    platform_sell = _capped_per_share(
        quantity, sell_notional, cfg["platform_per_share"], cfg["platform_min"],
        cfg["platform_cap_notional_fraction"])
    settlement_buy = _capped_per_share(
        quantity, buy_notional, cfg["settlement_per_share"], cfg["settlement_min"],
        cfg["settlement_cap_notional_fraction"])
    settlement_sell = _capped_per_share(
        quantity, sell_notional, cfg["settlement_per_share"], cfg["settlement_min"],
        cfg["settlement_cap_notional_fraction"])
    sec_fee = np.maximum(sell_notional * cfg["sec_sell_notional_fraction"], cfg["sec_sell_min"])
    finra_fee = np.minimum(
        np.maximum(quantity * cfg["finra_sell_per_share"], cfg["finra_sell_min"]),
        cfg["finra_sell_max"])
    cat_buy = np.maximum(quantity * cfg["cat_per_share"], cfg["cat_min"])
    cat_sell = np.maximum(quantity * cfg["cat_per_share"], cfg["cat_min"])
    buy_cost = buy_notional + commission_buy + platform_buy + settlement_buy + cat_buy
    sell_proceeds = (sell_notional - commission_sell - platform_sell - settlement_sell
                     - sec_fee - finra_fee - cat_sell)
    net = (sell_proceeds - buy_cost) / buy_cost
    net = np.where((quantity >= 1) & np.isfinite(entry) & np.isfinite(exit_) &
                   (entry > 0) & (exit_ > 0), net, np.nan)
    return pd.Series(net, index=entry_open.index)
