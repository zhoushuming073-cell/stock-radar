"""Summary statistics for a finished backtest.

``summarize_backtest`` condenses two artefacts of a backtest run into one flat
dict that is safe to log, export or compare across parameter sweeps:

  * ``equity``  - one row per session: ``date``, ``equity``, ``cash`` and
    ``positions`` (a mapping/collection of open symbols, or a position count).
  * ``trades``  - one row per closed round trip: ``net_pnl``, ``net_return``,
    ``holding_sessions``, ``exit_reason``, ``gross_pnl``, ``buy_fee_total``,
    ``sell_fee_total`` and ``slippage_cost``.

Conventions used here, so the numbers stay reproducible:

  * A year is ``TRADING_DAYS_PER_YEAR`` sessions, and CAGR annualises over
    ``sessions / 252`` years - no calendar-day arithmetic.
  * Risk-free rate is 0, so Sharpe is ``mean(daily return) / std(daily return)
    * sqrt(252)`` with a sample standard deviation (``ddof=1``).
  * ``max_drawdown`` is a negative fraction of the running equity peak. The
    peak baseline starts at ``initial_capital``, so a loss suffered before the
    first row of the curve is still counted.
  * ``net_pnl`` is equity-curve based (``final_equity - initial_capital``);
    ``net_pnl_trades`` is the sum of the blotter's ``net_pnl`` column. The two
    differ when a run ends with open positions, and that gap is worth auditing.
  * Empty inputs are safe: an empty curve or an empty blotter yields zeroed
    metrics instead of raising. Required *columns* are still validated.
"""

from __future__ import annotations

import json
import math

import pandas as pd

TRADING_DAYS_PER_YEAR = 252

EQUITY_COLUMNS = ("date", "equity", "cash", "positions")
TRADE_COLUMNS = ("net_pnl", "net_return", "holding_sessions", "exit_reason",
                 "gross_pnl", "buy_fee_total", "sell_fee_total", "slippage_cost")

_MONEY_DIGITS = 6


def _finite(value: object, default: float = 0.0) -> float:
    """Coerce ``value`` to a finite float, falling back to ``default``."""
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _round(value: object, default: float = 0.0) -> float:
    return round(_finite(value, default), _MONEY_DIGITS)


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing required column(s): {', '.join(missing)}")


def _numeric(series: pd.Series) -> pd.Series:
    """Coerce a column to float, turning junk and infinities into NaN."""
    values = pd.to_numeric(series, errors="coerce")
    return values.replace([float("inf"), float("-inf")], float("nan"))


def _mean(values: pd.Series) -> float:
    clean = values.dropna()
    return 0.0 if clean.empty else _round(clean.mean())


def _median(values: pd.Series) -> float:
    clean = values.dropna()
    return 0.0 if clean.empty else _round(clean.median())


def _total(values: pd.Series) -> float:
    clean = values.dropna()
    return 0.0 if clean.empty else _round(clean.sum())


def _as_date(value: object) -> str | None:
    if value is None:
        return None
    to_date = getattr(value, "date", None)
    if callable(to_date):
        try:
            return to_date().isoformat()
        except (TypeError, ValueError, AttributeError):
            pass
    return str(value)


def _position_count(value: object) -> int:
    """Number of open positions in one ``positions`` cell.

    Accepts a mapping of symbol -> quantity, any collection of symbols, a JSON
    or comma-separated string, or a bare integer count. Anything unreadable
    counts as zero rather than failing the whole summary.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        return len(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            parsed = json.loads(text)
        except ValueError:
            return len([part for part in text.split(",") if part.strip()])
        if isinstance(parsed, (dict, list, tuple)):
            return len(parsed)
        return 1
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _curve_metrics(equity: pd.DataFrame, capital: float) -> dict:
    curve = _numeric(equity["equity"]).dropna().astype(float)
    sessions = int(len(equity))
    final_equity = float(curve.iloc[-1]) if not curve.empty else capital
    net_pnl = final_equity - capital
    years = sessions / TRADING_DAYS_PER_YEAR

    if years <= 0 or curve.empty:
        cagr = 0.0
    elif final_equity <= 0:
        cagr = -1.0                      # capital fully lost
    else:
        cagr = (final_equity / capital) ** (1.0 / years) - 1.0

    if curve.empty:
        max_drawdown = 0.0
    else:
        full = pd.concat([pd.Series([capital], dtype=float), curve], ignore_index=True)
        max_drawdown = float((full / full.cummax() - 1.0).min())

    returns = curve.pct_change().replace([float("inf"), float("-inf")], float("nan")).dropna()
    if len(returns) < 2:
        volatility = 0.0
        sharpe = 0.0
    else:
        deviation = float(returns.std(ddof=1))
        if deviation > 0:
            volatility = deviation * math.sqrt(TRADING_DAYS_PER_YEAR)
            sharpe = float(returns.mean()) / deviation * math.sqrt(TRADING_DAYS_PER_YEAR)
        else:
            volatility = 0.0
            sharpe = 0.0                 # a flat curve has no risk to divide by

    equity_value = _numeric(equity["equity"])
    cash_value = _numeric(equity["cash"])
    funded = equity_value > 0
    utilisation = ((equity_value - cash_value) / equity_value).where(funded)
    cash_pct = (cash_value / equity_value).where(funded)

    dates = equity["date"].dropna()
    return {
        "sessions": sessions,
        "start_date": _as_date(dates.iloc[0]) if len(dates) else None,
        "end_date": _as_date(dates.iloc[-1]) if len(dates) else None,
        "final_equity": _round(final_equity, capital),
        "net_pnl": _round(net_pnl),
        "total_return": _round(net_pnl / capital),
        "cagr": _round(cagr),
        "max_drawdown": _round(max_drawdown),
        "annual_volatility": _round(volatility),
        "sharpe": _round(sharpe),
        "avg_position_utilization": _mean(utilisation),
        "avg_cash_pct": _mean(cash_pct),
        "max_concurrent_positions": max(
            (_position_count(value) for value in equity["positions"]), default=0),
    }


def _trade_metrics(trades: pd.DataFrame) -> dict:
    net = _numeric(trades["net_pnl"])
    wins = net[net > 0]
    losses = net[net < 0]
    scored = net.dropna()
    gross_profit = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = float(losses.sum()) if not losses.empty else 0.0

    if gross_loss < 0:
        profit_factor = gross_profit / abs(gross_loss)
    elif gross_profit > 0:
        profit_factor = float("inf")     # no losing trade to divide by
    else:
        profit_factor = 0.0

    reasons = trades["exit_reason"].dropna()
    return {
        "trade_count": int(len(trades)),
        "win_rate": _round(len(wins) / len(scored)) if len(scored) else 0.0,
        "avg_trade_pnl": _mean(net),
        "median_trade_pnl": _median(net),
        "avg_trade_return": _mean(_numeric(trades["net_return"])),
        "median_trade_return": _median(_numeric(trades["net_return"])),
        "profit_factor": profit_factor,
        "avg_holding_sessions": _mean(_numeric(trades["holding_sessions"])),
        "median_holding_sessions": _median(_numeric(trades["holding_sessions"])),
        "exit_reason_counts": {
            str(reason): int(count) for reason, count in reasons.value_counts().items()
        },
        "gross_pnl": _total(_numeric(trades["gross_pnl"])),
        "fees": _total(_numeric(trades["buy_fee_total"]) + _numeric(trades["sell_fee_total"])),
        "slippage_cost": _total(_numeric(trades["slippage_cost"])),
        "net_pnl_trades": _total(net),
    }


def summarize_backtest(
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    initial_capital: float,
) -> dict:
    """Summarise an equity curve and a trade blotter into one metric dict.

    Raises ``ValueError`` when a required column is absent or when
    ``initial_capital`` is not a finite positive number. Empty frames are
    handled instead of raising: their metrics come back as zeros.
    """
    _require_columns(equity, EQUITY_COLUMNS, "equity")
    _require_columns(trades, TRADE_COLUMNS, "trades")
    capital = _finite(initial_capital, float("nan"))
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("initial_capital must be a finite positive number")

    return {
        "initial_capital": _round(capital),
        **_curve_metrics(equity, capital),
        **_trade_metrics(trades),
    }
