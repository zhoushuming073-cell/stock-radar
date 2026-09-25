"""Read-only local dashboard for the Phase 1 market-data foundation."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DATABASE = DATA / "market.duckdb"
UNIVERSE = DATA / "universe.csv"
VALIDATION = DATA / "validation-summary.json"

LABELS = {
    "abnormal_price_jump": "价格大幅跳变",
    "missing_trading_session": "缺失交易日",
    "no_bars": "无日线数据",
    "stale_ticker": "近期无更新",
}
MESSAGES = {
    "abnormal_price_jump": "相邻日收盘价变化较大，需核对公司行动",
    "missing_trading_session": "中间交易日没有日线记录",
    "no_bars": "所选时段无日线数据",
    "stale_ticker": "最近多个交易日无日线",
}


@st.cache_data(ttl=60)
def load_overview(db_path: str, stamp: int) -> dict[str, object]:
    """Aggregate in DuckDB; never load the full bar table into Python."""
    del stamp
    connection = duckdb.connect(db_path, read_only=True)
    try:
        bars, symbols, first, last = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(date), MAX(date) FROM daily_bars"
        ).fetchone()
        latest_assets = connection.execute(
            "SELECT COUNT(*) FROM assets WHERE last_seen = (SELECT MAX(last_seen) FROM assets)"
        ).fetchone()[0]
    finally:
        connection.close()
    return {
        "bars": bars,
        "symbols_with_bars": symbols,
        "latest_assets": latest_assets,
        "first": first,
        "last": last,
    }


@st.cache_data(ttl=60)
def load_universe(csv_path: str, stamp: int) -> list[dict[str, str]]:
    del stamp
    with open(csv_path, encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


@st.cache_data(ttl=60)
def load_validation(json_path: str, stamp: int) -> dict[str, object]:
    del stamp
    with open(json_path, encoding="utf-8") as stream:
        return json.load(stream)


@st.cache_data(ttl=60)
def load_symbol(db_path: str, stamp: int, symbol: str) -> tuple[dict[str, object] | None, pd.DataFrame]:
    del stamp
    connection = duckdb.connect(db_path, read_only=True)
    try:
        result = connection.execute(
            """SELECT name, exchange, asset_class, status, tradable, last_seen
               FROM assets WHERE symbol = ? ORDER BY last_seen DESC LIMIT 1""",
            [symbol],
        ).fetchone()
        asset = None if result is None else dict(
            zip(("name", "exchange", "asset_class", "status", "tradable", "last_seen"), result)
        )
        bars = connection.execute(
            """SELECT date, open, high, low, close, volume
               FROM daily_bars WHERE symbol = ? ORDER BY date""",
            [symbol],
        ).df()
    finally:
        connection.close()
    return asset, bars


def price_chart(bars: pd.DataFrame) -> go.Figure:
    chart = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.76, 0.24],
        vertical_spacing=0.025,
    )
    chart.add_trace(
        go.Candlestick(
            x=bars["date"],
            open=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            increasing_line_color="#0b9c91",
            decreasing_line_color="#e25e67",
            name="日线",
        ),
        row=1,
        col=1,
    )
    colors = ["#0b9c91" if close >= opening else "#e25e67" for opening, close in zip(bars["open"], bars["close"])]
    chart.add_trace(
        go.Bar(x=bars["date"], y=bars["volume"], marker_color=colors, name="成交量", opacity=0.8),
        row=2,
        col=1,
    )
    chart.update_layout(
        height=510,
        margin=dict(l=8, r=8, t=12, b=24),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color="#354761", size=12),
        showlegend=False,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
    )
    chart.update_xaxes(showgrid=True, gridcolor="#edf1f6", tickformat="%Y-%m")
    chart.update_yaxes(showgrid=True, gridcolor="#edf1f6", zeroline=False, row=1, col=1)
    chart.update_yaxes(showgrid=True, gridcolor="#edf1f6", zeroline=False, row=2, col=1)
    return chart


def main() -> None:
    st.set_page_config(page_title="Stock Radar 数据总览", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(
        """
        <style>
        .stApp { background: #f7f9fc; color: #142a47; }
        header[data-testid="stHeader"] { display: none; }
        .block-container { max-width: 1540px; padding-top: 1.3rem; padding-bottom: 2.5rem; }
        h1, h2, h3 { color: #142a47; letter-spacing: -0.025em; }
        h1 { font-size: 2rem !important; }
        div[data-testid="stMetric"] { background: white; border: 1px solid #e2e9f2; border-radius: 10px; padding: 1rem 1.1rem; }
        div[data-testid="stMetricLabel"] { color: #64758d; font-size: 0.9rem; }
        div[data-testid="stMetricValue"] { color: #142a47; font-size: 1.8rem; }
        div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"] { background: white; border: 1px solid #e2e9f2; border-radius: 10px; padding: 0.45rem; }
        .muted { color: #64758d; font-size: 0.9rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not DATABASE.is_file() or not UNIVERSE.is_file() or not VALIDATION.is_file():
        st.error("尚未找到完整的 Phase 1 数据。请先运行 sync 和 validate。")
        st.stop()

    try:
        overview = load_overview(str(DATABASE), DATABASE.stat().st_mtime_ns)
        universe = load_universe(str(UNIVERSE), UNIVERSE.stat().st_mtime_ns)
        report = load_validation(str(VALIDATION), VALIDATION.stat().st_mtime_ns)
    except (OSError, duckdb.Error, ValueError, json.JSONDecodeError) as error:
        st.error(f"读取本地数据失败：{error}")
        st.stop()
    if not universe:
        st.info("当前股票池为空，请先运行 sync。")
        st.stop()
    report_is_stale = VALIDATION.stat().st_mtime_ns < DATABASE.stat().st_mtime_ns

    title, action = st.columns([5, 1])
    with title:
        st.title("Stock Radar 数据总览")
        st.caption(f"历史日线 · 截至 {overview['last']} · 本地只读")
    with action:
        if st.button("刷新数据", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    issue_counts = Counter(issue["code"] for issue in report.get("issues", []))
    errors = sum(issue.get("severity") == "error" for issue in report.get("issues", []))
    warnings = sum(issue.get("severity") == "warning" for issue in report.get("issues", []))
    metrics = st.columns(4)
    metrics[0].metric("股票池", f"{len(universe):,}")
    metrics[1].metric("日线数据", f"{overview['bars']:,}")
    metrics[2].metric("校验错误", f"{errors:,}")
    metrics[3].metric("研究警告", f"{warnings:,}")
    if report_is_stale:
        st.warning("数据库比验证报告更新。请运行 validate，再刷新看板。")

    st.write("")
    names = {row["symbol"]: row["name"] for row in universe}
    symbols = sorted(names)
    preferred = "AAPL" if "AAPL" in names else symbols[0]
    selection, period = st.columns([4, 2])
    with selection:
        symbol = st.selectbox(
            "选择股票代码（可输入代码搜索）",
            symbols,
            index=symbols.index(preferred),
        )
    with period:
        span = st.selectbox("图表范围", ["3个月", "6个月", "1年", "全部"], index=1)
    days = {"3个月": 65, "6个月": 130, "1年": 260, "全部": None}[span]

    try:
        asset, all_bars = load_symbol(str(DATABASE), DATABASE.stat().st_mtime_ns, symbol)
    except duckdb.Error as error:
        st.error(f"读取 {symbol} 日线失败：{error}")
        st.stop()
    visible = all_bars.tail(days) if days else all_bars
    symbol_issues = [issue for issue in report.get("issues", []) if issue.get("symbol") == symbol]

    chart_col, detail_col = st.columns([3.25, 1.1], gap="medium")
    with chart_col:
        st.subheader(f"{symbol} · {names[symbol]}")
        if visible.empty:
            st.info("这个标的在当前数据库中没有日线数据。")
        else:
            st.plotly_chart(price_chart(visible), width="stretch", config={"displaylogo": False})
    with detail_col:
        st.subheader("标的信息")
        if asset:
            st.write(f"**公司名称**　{asset['name']}")
            st.write(f"**交易所**　{asset['exchange']}")
            st.write(f"**资产类型**　{'美股权益' if asset['asset_class'] == 'us_equity' else asset['asset_class']}")
            st.write(f"**交易状态**　{'活跃' if asset['status'] == 'active' else asset['status']}")
        st.divider()
        st.subheader("数据覆盖")
        st.write(f"**日线记录**　{len(all_bars):,}")
        if not all_bars.empty:
            st.write(f"**最早日期**　{all_bars.iloc[0]['date'].date()}")
            st.write(f"**最近日期**　{all_bars.iloc[-1]['date'].date()}")
        st.write(f"**研究警告**　{len(symbol_issues):,}")
        st.caption("历史行情仅供研究，不代表实时价格。")

    st.divider()
    left, right = st.columns([1.1, 2.9], gap="medium")
    with left:
        st.subheader("研究警告统计")
        codes = ("abnormal_price_jump", "missing_trading_session", "no_bars", "stale_ticker")
        for offset in (0, 2):
            pair = st.columns(2)
            for column, code in zip(pair, codes[offset : offset + 2]):
                column.metric(LABELS[code], f"{issue_counts[code]:,}")
    with right:
        st.subheader("研究警告明细")
        filter_type, filter_scope = st.columns(2)
        with filter_type:
            chosen_code = st.selectbox("警告类型", ["全部", *LABELS], format_func=lambda code: LABELS.get(code, code))
        with filter_scope:
            scope = st.selectbox("标的范围", ["全部标的", f"仅 {symbol}"])
        rows = [
            {
                "代码": issue.get("symbol") or "",
                "日期": issue.get("date") or "",
                "类型": LABELS.get(issue["code"], issue["code"]),
                "说明": MESSAGES.get(issue["code"], issue.get("message") or ""),
            }
            for issue in report.get("issues", [])
            if (chosen_code == "全部" or issue["code"] == chosen_code)
            and (scope == "全部标的" or issue.get("symbol") == symbol)
        ]
        st.dataframe(pd.DataFrame(rows, columns=["代码", "日期", "类型", "说明"]), width="stretch", height=310, hide_index=True)
        st.caption(f"显示 {len(rows):,} 条 · 来源：data/validation-summary.json")


if __name__ == "__main__":
    main()
