"""Read-only Strategy Lab adapter for frozen Research Infrastructure v1.

Membership is always read from its dated Shape index. The operational market
database supplies SPY observations only; it never supplies stock membership.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.research.infrastructure import shape_research_universe_v1

MODE = "research_infrastructure_v1"
FEATURES = frozenset({"beta_spy_126", "avg_dollar_volume_20", "market_input_safe"})
SOURCE = "legacy:alpaca:sip"
BASIS = "split"


def _benchmark(root: Path, end: pd.Timestamp, symbol: str = "SPY") -> pd.DataFrame:
    with duckdb.connect(str(root / "data/market.duckdb"), read_only=True) as conn:
        bars = conn.execute("""SELECT date, close, provider, feed, adjustment
            FROM daily_bars WHERE symbol=? AND date<=? ORDER BY date""",
            [symbol, end.date()]).df()
    if bars.empty or not bars.provider.eq("alpaca").all() or not bars.feed.eq("sip").all() or not bars.adjustment.eq("split").all():
        raise ValueError(f"causal {symbol} SIP split benchmark unavailable")
    bars["date"] = pd.to_datetime(bars.date)
    if bars.date.duplicated().any() or bars.close.le(0).any():
        raise ValueError(f"unsafe {symbol} benchmark")
    bars["spy_return"] = bars.close.pct_change(fill_method=None)
    return bars


class ResearchHistory:
    """Bounded, T-clipped host capability. No plugin receives a connection."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.api = shape_research_universe_v1(self.root)
        self._cache: dict[tuple[str, str, int], pd.DataFrame] = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.api.__exit__(*args)

    @property
    def fingerprint(self) -> str:
        return self.api.fingerprint

    @property
    def database_sha256(self) -> str:
        return self.api.profile["semantics"]["core_database_sha256"]

    @property
    def core_path(self) -> Path:
        return self.root / self.api.profile["core_directory"] / "shape.duckdb"

    def history(self, security_id: str, decision: pd.Timestamp, sessions: int = 430) -> pd.DataFrame:
        day = pd.Timestamp(decision).normalize()
        if day >= pd.Timestamp(self.api.profile["semantics"]["fresh_start"]):
            raise ValueError("Fresh research requires a separately frozen method")
        key = (security_id, str(day.date()), sessions)
        if key not in self._cache:
            # The frozen 126-session window establishes dated membership,
            # source, basis and a complete safe prefix through T.
            safe = self.api.window(security_id, day, 126, dataset=False)
            series = safe.metadata["series_id"]
            bars = self.api.core.connection.execute("""SELECT date, open, high, low, close,
                volume, session_no, shape_research_ready, source, basis
                FROM shape_price WHERE series_id=? AND date<=? ORDER BY date DESC LIMIT ?""",
                [series, day.date(), sessions]).df().iloc[::-1].reset_index(drop=True)
            if bars.empty or pd.Timestamp(bars.date.iloc[-1]) != day:
                raise ValueError("missing decision-date history")
            if not bars.source.eq(safe.metadata["source"]).all() or not bars.basis.eq(safe.metadata["basis"]).all():
                raise ValueError("mixed historical price/volume basis")
            if not bars.shape_research_ready.all():
                raise ValueError("unsafe historical OHLCV")
            # A missing exchange session cannot be compressed into a fake
            # adjacent bar. Keep only the contiguous suffix ending at T.
            gaps = bars.session_no.diff().fillna(1).ne(1)
            if gaps.any():
                bars = bars.iloc[int(np.flatnonzero(gaps.to_numpy())[-1]):].reset_index(drop=True)
            if pd.to_datetime(bars.date).gt(day).any():
                raise ValueError("post-decision history is prohibited")
            if len(bars) < min(126, sessions):
                raise ValueError("safe history shorter than frozen 126-session window")
            result = bars[["date", "open", "high", "low", "close", "volume"]].copy()
            result["date"] = pd.to_datetime(result.date)
            result.attrs.update({"backend": MODE, "semantic_hash": self.fingerprint,
                                 "source": safe.metadata["source"], "basis": safe.metadata["basis"],
                                 "security_id": security_id, "cutoff": str(day.date())})
            self._cache[key] = result
        return self._cache[key].copy(deep=True)

    def benchmark(self, symbol: str, decision: pd.Timestamp, sessions: int = 430) -> pd.DataFrame:
        if symbol not in {"SPY", "QQQ"}:
            raise ValueError("only SPY and QQQ benchmark histories are registered")
        day = pd.Timestamp(decision).normalize()
        bars = _benchmark(self.root, day, symbol).tail(sessions).copy()
        bars.attrs.update({"source": "alpaca:sip", "basis": BASIS, "cutoff": str(day.date()),
                           "backend": "operational_benchmark_only"})
        return bars[["date", "close"]].copy()


def load_signal_frame(root: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Dated members and causal market features, without forward outcomes."""
    root = Path(root).resolve()
    with ResearchHistory(root) as host:
        if pd.Timestamp(end) >= pd.Timestamp(host.api.profile["semantics"]["fresh_start"]):
            raise ValueError("Q2 v1.3 historical Run cannot include Fresh")
        conn = host.api.core.connection
        members = conn.execute("""SELECT security_id, series_id, decision_date AS date,
            historical_ticker AS symbol, source, basis FROM universe_window_index
            WHERE length=126 AND supported_membership AND decision_date BETWEEN ? AND ?
            QUALIFY row_number() OVER (PARTITION BY security_id, decision_date ORDER BY priority, series_id)=1""",
            [pd.Timestamp(start).date(), pd.Timestamp(end).date()]).df()
        if members.empty:
            raise ValueError("Research Infrastructure v1 has no eligible historical members")
        # Confirm the public frozen API's membership on sampled boundary days.
        for day in (members.date.min(), members.date.max()):
            expected = set(host.api.universe_on(day, 126).security_id)
            observed = set(members.loc[members.date.eq(day), "security_id"])
            if expected != observed:
                raise ValueError("research membership differs from frozen public API")
        if members.duplicated(["date", "symbol"]).any():
            raise ValueError("ambiguous same-day historical symbol; no ticker fallback")
        eligible = members.loc[members.source.eq(SOURCE) & members.basis.eq(BASIS)].copy()
        if eligible.empty:
            raise ValueError("no jointly sourced SIP split historical members")
        # Read only a bounded causal warm-up. DuckDB performs the rolling work;
        # the Python result contains one row per indexed historical member-day.
        warmup = (pd.Timestamp(start) - pd.Timedelta(days=220)).date()
        conn.register("q2_series", eligible[["series_id"]].drop_duplicates())
        spy = _benchmark(root, pd.Timestamp(end))
        conn.register("q2_spy", spy[["date", "spy_return"]])
        features = conn.execute("""WITH bars AS (
            SELECT p.series_id,p.date,p.open,p.close,p.volume,p.session_no,
                   p.shape_research_ready, p.source,p.basis,
                   lag(p.close) OVER (PARTITION BY p.series_id ORDER BY p.date) AS prior_close,
                   lag(p.session_no) OVER (PARTITION BY p.series_id ORDER BY p.date) AS prior_session,
                   avg(p.close*p.volume) OVER (PARTITION BY p.series_id ORDER BY p.date
                       ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv20,
                   count(*) OVER (PARTITION BY p.series_id ORDER BY p.date
                       ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS adv_count
            FROM shape_price p JOIN q2_series q USING(series_id)
            WHERE p.date BETWEEN ? AND ? AND p.source=? AND p.basis=?
        ), pairs AS (
            SELECT b.*, CASE WHEN b.prior_session=b.session_no-1 AND b.prior_close>0
                THEN b.close/b.prior_close-1 END AS stock_return, s.spy_return
            FROM bars b LEFT JOIN q2_spy s ON b.date=s.date
        ), measures AS (
            SELECT *, CASE WHEN shape_research_ready AND abs(stock_return)<=0.5
                AND abs(spy_return)<=0.2 THEN stock_return END AS x,
                CASE WHEN shape_research_ready AND abs(stock_return)<=0.5
                AND abs(spy_return)<=0.2 THEN spy_return END AS y
            FROM pairs
        ) SELECT series_id,date,close,shape_research_ready,adv20,adv_count,
            regr_slope(x,y) OVER w AS beta_spy_126,
            count(x) OVER w AS beta_samples,
            sum(CASE WHEN stock_return IS NOT NULL AND
                (abs(stock_return)>0.5 OR abs(spy_return)>0.2) THEN 1 ELSE 0 END) OVER w AS outliers
            FROM measures WINDOW w AS (PARTITION BY series_id ORDER BY date
                ROWS BETWEEN 125 PRECEDING AND CURRENT ROW)""",
            [warmup, pd.Timestamp(end).date(), SOURCE, BASIS]).df()
        conn.unregister("q2_series")
        conn.unregister("q2_spy")
        features["date"] = pd.to_datetime(features.date)
        members["date"] = pd.to_datetime(members.date)
        frame = members.merge(features, on=["series_id", "date"], how="left", validate="one_to_one")
        other = members.loc[~members.series_id.isin(eligible.series_id), ["series_id", "date"]]
        if not other.empty:
            conn.register("q2_other", other)
            other_prices = conn.execute("""SELECT p.series_id,p.date,p.close FROM shape_price p
                JOIN q2_other q USING(series_id,date)""").df()
            conn.unregister("q2_other")
            other_prices["date"] = pd.to_datetime(other_prices.date)
            lookup = other_prices.set_index(["series_id", "date"]).close
            missing = frame.close.isna()
            frame.loc[missing, "close"] = frame.loc[missing].set_index(["series_id", "date"]).index.map(lookup)
        frame["market_input_safe"] = (frame.source.eq(SOURCE) & frame.basis.eq(BASIS)
             & frame.shape_research_ready.fillna(False)
             & frame.adv_count.ge(20) & frame.beta_samples.ge(105) & frame.outliers.eq(0)
             & frame.beta_spy_126.notna() & frame.adv20.notna())
        frame["avg_dollar_volume_20"] = frame.adv20.where(frame.market_input_safe)
        frame["beta_spy_126"] = frame.beta_spy_126.where(frame.market_input_safe)
        frame["security_name"] = frame.symbol
        frame["tradability_pass"] = frame.market_input_safe
        frame["elasticity_score"] = 0.0
        if frame.close.isna().any():
            raise ValueError("indexed historical member has no T-close bar")
        frame["source_backend"] = MODE
        return frame.set_index(["date", "symbol"], drop=False).sort_index()


def backend_receipt(root: Path) -> dict:
    with ResearchHistory(root) as host:
        return {"mode": MODE, "semantic_hash": host.fingerprint,
                "core_database_sha256": host.database_sha256,
                "source": SOURCE, "basis": BASIS,
                "benchmark": "SPY Alpaca SIP split, T-clipped; operational benchmark only"}


def load_execution_prices(root: Path, frame: pd.DataFrame, signals: list[dict],
                          start: str, end: str) -> pd.DataFrame:
    """Resolve each selected ticker to its dated security/series before execution."""
    selected = []
    for signal in signals:
        day = pd.Timestamp(signal["signal_date"])
        match = frame.loc[(frame.date.eq(day)) & frame.symbol.eq(signal["symbol"])]
        if len(match) != 1 or not bool(match.iloc[0].market_input_safe):
            raise ValueError("selected signal lacks a unique safe dated research identity")
        row = match.iloc[0]
        selected.append((signal["symbol"], row.security_id, row.series_id))
    identities = pd.DataFrame(selected, columns=["symbol", "security_id", "series_id"]).drop_duplicates()
    if not identities.empty and identities.duplicated("symbol").any():
        raise ValueError("ticker maps to multiple historical securities in one Run")
    with ResearchHistory(root) as host:
        if identities.empty:
            stock = pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])
        else:
            host.api.core.connection.register("q2_execution_ids", identities)
            stock = host.api.core.connection.execute("""SELECT p.date,i.symbol,p.open,p.high,p.low,
                p.close,p.volume,p.source,p.basis,p.shape_research_ready
                FROM shape_price p JOIN q2_execution_ids i USING(series_id)
                WHERE p.date BETWEEN ? AND ? ORDER BY p.date,i.symbol""", [start, end]).df()
            host.api.core.connection.unregister("q2_execution_ids")
            if not stock.source.eq(SOURCE).all() or not stock.basis.eq(BASIS).all() or not stock.shape_research_ready.all():
                raise ValueError("execution prices contain unsafe or mixed-source research bars")
            stock = stock[["date", "symbol", "open", "high", "low", "close", "volume"]]
    with duckdb.connect(str(root / "data/market.duckdb"), read_only=True) as conn:
        spy = conn.execute("""SELECT date,symbol,open,high,low,close,volume,provider,feed,adjustment
            FROM daily_bars WHERE symbol='SPY' AND date BETWEEN ? AND ? ORDER BY date""",
            [start, end]).df()
    if spy.empty or not spy.provider.eq("alpaca").all() or not spy.feed.eq("sip").all() or not spy.adjustment.eq(BASIS).all():
        raise ValueError("SPY execution benchmark is unavailable or has incompatible provenance")
    spy = spy[["date", "symbol", "open", "high", "low", "close", "volume"]]
    prices = pd.concat([stock, spy], ignore_index=True)
    if prices.duplicated(["date", "symbol"]).any():
        raise ValueError("ambiguous research execution prices")
    return prices
