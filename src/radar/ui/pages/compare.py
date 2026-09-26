"""Compare immutable research Runs without ranking or trading advice."""

from __future__ import annotations

from collections.abc import Mapping

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


METRICS = (
    ("总收益", "total_return", ".2%"),
    ("年化收益", "cagr", ".2%"),
    ("年化波动", "annual_volatility", ".2%"),
    ("夏普", "sharpe", ".2f"),
    ("最大回撤", "max_drawdown", ".2%"),
    ("胜率", "win_rate", ".2%"),
    ("盈利因子", "profit_factor", ".2f"),
    ("交易数", "trade_count", ",.0f"),
    ("手续费", "fees", ",.0f"),
    ("滑点成本", "slippage_cost", ",.0f"),
)


def _label(run: dict) -> str:
    meta = run.get("metadata") or {}
    return f"{meta.get('strategy_name') or meta.get('strategy_id') or '策略'} · {str(run['run_id'])[:8]}"


def _flat(values: Mapping, prefix: str = "") -> dict[str, object]:
    result = {}
    for key, value in values.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            result.update(_flat(value, name))
        else:
            result[name] = value
    return result


def _spy(database, start: str, end: str) -> pd.DataFrame:
    with duckdb.connect(str(database), read_only=True) as conn:
        return conn.execute(
            "SELECT date, close FROM daily_bars WHERE symbol='SPY' "
            "AND date BETWEEN ? AND ? ORDER BY date", [start, end],
        ).df()


def render_compare(manager) -> None:
    st.title("Compare")
    st.caption("比较多次独立运行的曲线、成本与参数；结果不自动评选优胜者。")
    runs = [run for run in manager.store.list_runs(limit=500)
            if run.get("status") == "completed"]
    if len(runs) < 2:
        st.info("至少需要两次已完成的回测才能比较。")
        return
    by_id = {str(run["run_id"]): run for run in runs}
    controls = st.columns([3, 1.5, 0.75])
    with controls[0]:
        selected_ids = st.multiselect(
            "选择运行", list(by_id), default=list(by_id)[:2],
            format_func=lambda run_id: _label(by_id[run_id]), key="compare_runs",
        )
    starts = [pd.to_datetime((run.get("metadata") or {}).get("start_date"), errors="coerce")
              for run in runs]
    ends = [pd.to_datetime((run.get("metadata") or {}).get("end_date"), errors="coerce")
            for run in runs]
    start = min(day.date() for day in starts if pd.notna(day))
    end = max(day.date() for day in ends if pd.notna(day))
    with controls[1]:
        date_range = st.date_input("Date Range", value=(start, end),
                                   min_value=start, max_value=end, key="compare_date_range")
    with controls[2]:
        show_spy = st.checkbox("显示 SPY", value=True, key="compare_show_spy")
    if len(selected_ids) < 2:
        st.info("请选择至少两次运行。")
        return
    selected = [by_id[run_id] for run_id in selected_ids[:6]]
    if len(date_range) != 2 or date_range[0] > date_range[1]:
        st.info("请选择有效的起止日期。")
        return
    first_day, last_day = date_range
    st.caption("日期范围只筛选图线；右侧指标仍为各次完整回测结果。")
    left, right = st.columns([1.6, 0.8], gap="small")
    figure = go.Figure()
    all_curves = []
    colors = ("#2563eb", "#13a66a", "#e59a38", "#8b67ce", "#dd6680", "#3da1bb")
    for index, run in enumerate(selected):
        curve = manager.store.get_equity(run["run_id"])
        if curve.empty or not {"date", "equity"}.issubset(curve.columns):
            continue
        curve = curve.copy()
        curve["date"] = pd.to_datetime(curve["date"])
        curve["equity"] = pd.to_numeric(curve["equity"], errors="coerce")
        curve = curve.dropna(subset=["equity"]).sort_values("date")
        curve = curve[(curve["date"].dt.date >= first_day) &
                      (curve["date"].dt.date <= last_day)]
        if curve.empty or curve["equity"].iloc[0] <= 0:
            continue
        all_curves.append(curve)
        figure.add_trace(go.Scatter(
            x=curve["date"], y=100 * (curve["equity"] / curve["equity"].iloc[0] - 1),
            name=_label(run), mode="lines", line={"color": colors[index], "width": 2},
        ))
    if show_spy and all_curves:
        start = min(curve["date"].min() for curve in all_curves)
        end = max(curve["date"].max() for curve in all_curves)
        try:
            spy = _spy(manager.database, str(start.date()), str(end.date()))
        except (OSError, duckdb.Error):
            spy = pd.DataFrame()
        if not spy.empty and spy["close"].iloc[0] > 0:
            figure.add_trace(go.Scatter(
                x=spy["date"], y=100 * (spy["close"] / spy["close"].iloc[0] - 1),
                name="SPY 参考", mode="lines", line={"color": "#aab2bf", "dash": "dot"},
            ))
    figure.update_layout(
        height=420, margin=dict(l=12, r=12, t=16, b=12),
        template="plotly_white", hovermode="x unified",
        yaxis_title="相对起点收益 (%)", legend={"orientation": "h", "y": -0.18},
        paper_bgcolor="white", plot_bgcolor="white",
    )
    figure.update_xaxes(gridcolor="#f0f2f5")
    figure.update_yaxes(gridcolor="#f0f2f5")
    with left:
        st.markdown("**Equity Curves**")
        st.plotly_chart(figure, width="stretch", key="compare_equity")
    with right:
        st.markdown("**Performance Metrics**")
        rows = []
        for title, key, fmt in METRICS:
            row = {"指标": title}
            for run in selected:
                value = (run.get("metrics") or {}).get(key)
                try:
                    row[_label(run)] = format(float(value), fmt) if value is not None else "—"
                except (ValueError, TypeError):
                    row[_label(run)] = "—"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.markdown("**Parameter Diff**")
    values = {}
    for run in selected:
        meta = run.get("metadata") or {}
        config = _flat(meta.get("config") or {}, "strategy")
        config.update(_flat(meta.get("execution_policy") or {}, "execution"))
        config["slippage_bps"] = meta.get("slippage_bps")
        values[_label(run)] = config
    keys = sorted(set().union(*(set(config) for config in values.values())))
    diff = [{"参数": key, **{label: str(config.get(key, "—")) for label, config in values.items()}}
            for key in keys if len({repr(config.get(key)) for config in values.values()}) > 1]
    if diff:
        st.dataframe(pd.DataFrame(diff), hide_index=True, width="stretch")
    else:
        st.caption("所选运行的参数相同。")
