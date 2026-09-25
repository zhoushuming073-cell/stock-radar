"""Forward research labels. Keep this module out of feature computation."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


HORIZONS = (1, 3, 5, 10)


def compute_forward_labels(
    bars: pd.DataFrame, *, take_profit: float = 0.05,
    stop_loss: float = -0.10, max_holding: int = 10,
) -> pd.DataFrame:
    """Label a signal at close t using next-session Open as the entry reference.

    ``bars`` must be indexed by the full market-session calendar. Missing stock
    sessions stay missing: an incomplete future path never becomes a successful
    event by silently skipping an absent bar. High/Low are diagnostic only.
    """
    if not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("bars must have a sorted, unique session index")
    if not 0 < take_profit or not -1 < stop_loss < 0 or max_holding < 1:
        raise ValueError("invalid execution parameters")
    data = bars.loc[:, ["open", "high", "low", "close"]].astype(float)
    values = data.to_numpy()
    out: list[dict] = []
    for pos in range(len(data)):
        row: dict = {"entry_date": pd.NaT, "entry_open": np.nan}
        for horizon in HORIZONS:
            row[f"return_close_{horizon}d"] = np.nan
        for horizon in (5, 10):
            row[f"mfe_high_{horizon}d"] = np.nan
            row[f"mae_low_{horizon}d"] = np.nan
            row[f"exec_hit_tp_{horizon}d"] = pd.NA
            row[f"exec_hit_sl_{horizon}d"] = pd.NA
        row.update(simulated_exit_date=pd.NaT, simulated_exit_price=np.nan,
                   simulated_exit_reason=None, simulated_gross_return=np.nan)
        entry = pos + 1
        if entry >= len(data) or not math.isfinite(values[entry, 0]) or values[entry, 0] <= 0:
            out.append(row)
            continue
        cost = values[entry, 0]
        row["entry_date"] = data.index[entry]
        row["entry_open"] = cost
        for horizon in HORIZONS:
            end = entry + horizon - 1
            if end >= len(data):
                continue
            path = values[entry:end + 1]
            if not np.isfinite(path).all():
                continue
            row[f"return_close_{horizon}d"] = path[-1, 3] / cost - 1
            if horizon in (5, 10):
                row[f"mfe_high_{horizon}d"] = path[:, 1].max() / cost - 1
                row[f"mae_low_{horizon}d"] = path[:, 2].min() / cost - 1
        tp_hit = False
        sl_hit = False
        for holding_day in range(1, min(max_holding, len(data) - entry) + 1):
            date_pos = entry + holding_day - 1
            day = values[date_pos]
            if not np.isfinite(day).all():
                break
            open_price, _, _, close_price = day
            reason = None
            price = None
            if holding_day > 1:
                if open_price / cost - 1 >= take_profit:
                    reason, price = "take_profit_gap", open_price
                elif open_price / cost - 1 <= stop_loss:
                    reason, price = "stop_loss_gap", open_price
            if reason is None:
                if close_price / cost - 1 >= take_profit:
                    reason, price = "take_profit_close", close_price
                elif close_price / cost - 1 <= stop_loss:
                    reason, price = "stop_loss_close", close_price
                elif holding_day == max_holding:
                    reason, price = "max_holding_period", close_price
            if reason is not None:
                tp_hit = reason.startswith("take_profit")
                sl_hit = reason.startswith("stop_loss")
                row.update(simulated_exit_date=data.index[date_pos],
                           simulated_exit_price=price, simulated_exit_reason=reason,
                           simulated_gross_return=price / cost - 1)
            for horizon in (5, 10):
                if holding_day == horizon or reason is not None and holding_day <= horizon:
                    # A complete horizon is required to classify a negative event.
                    if entry + horizon <= len(data) and np.isfinite(values[entry:entry + horizon]).all():
                        row[f"exec_hit_tp_{horizon}d"] = tp_hit
                        row[f"exec_hit_sl_{horizon}d"] = sl_hit
            if reason is not None:
                break
        out.append(row)
    return pd.DataFrame(out, index=data.index)
