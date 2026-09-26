"""Reusable real-data panels for the primary Strategy Lab page."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from radar.strategy_lab_ui import (
    _config_controls, _initial_capital, _money, _pct, _plain,
    _spy_closes, equity_curve,
)


def _positions(run: dict) -> list[dict]:
    value = run.get("positions")
    if value is None:
        value = (run.get("result") or {}).get("open_positions")
    return value if isinstance(value, list) else []


def _latest_values(run: dict, curve: pd.DataFrame, trades: pd.DataFrame) -> tuple:
    progress = run.get("progress") or {}
    metrics = run.get("metrics") or {}
    capital = _initial_capital(run)
    last = curve.iloc[-1] if not curve.empty else None
    equity = (
        float(last["equity"]) if last is not None
        else progress.get("equity", metrics.get("final_equity", capital))
    )
    cash = (
        float(last["cash"]) if last is not None and pd.notna(last["cash"])
        else progress.get("cash")
    )
    drawdown = (
        float(last["drawdown"]) if last is not None and pd.notna(last["drawdown"])
        else progress.get("drawdown", metrics.get("max_drawdown"))
    )
    closed = progress.get("closed_trades")
    if closed is None:
        closed = metrics.get("trade_count", len(trades))
    return capital, equity, cash, drawdown, closed


def _equity_chart(manager, curve: pd.DataFrame, capital: float) -> go.Figure:
    figure = go.Figure()
    series = [pd.to_numeric(curve["equity"], errors="coerce")]
    figure.add_trace(go.Scatter(
        x=curve["date"], y=curve["equity"], name="Strategy Equity",
        mode="lines", line={"color": "#2563eb", "width": 2},
        fill="tozeroy", fillcolor="rgba(37,99,235,0.08)",
    ))
    if not curve.empty:
        spy = _spy_closes(
            str(manager.database), str(curve["date"].iloc[0].date()),
            str(curve["date"].iloc[-1].date()),
        )
        if not spy.empty and float(spy["close"].iloc[0]) > 0:
            spy_equity = capital * spy["close"] / float(spy["close"].iloc[0])
            series.append(spy_equity)
            figure.add_trace(go.Scatter(
                x=spy["date"], y=spy_equity,
                name="SPY (price only)", mode="lines",
                line={"color": "#aeb7c5", "width": 1.5, "dash": "dot"},
            ))
    figure.update_layout(
        height=315, margin=dict(l=6, r=6, t=12, b=10),
        template="plotly_white", hovermode="x unified",
        legend={"orientation": "h", "y": 1.08},
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        yaxis_title="USD",
    )
    figure.update_xaxes(gridcolor="#f2f4f7")
    minimum = min(float(values.min()) for values in series)
    maximum = max(float(values.max()) for values in series)
    figure.update_yaxes(gridcolor="#f2f4f7", tickformat=",.0f",
                        range=[minimum * 0.92, maximum * 1.04])
    return figure


def _drawdown_chart(curve: pd.DataFrame) -> go.Figure:
    figure = go.Figure(go.Scatter(
        x=curve["date"], y=curve["drawdown"], name="Drawdown",
        mode="lines", line={"color": "#e34b4b", "width": 1.5},
        fill="tozeroy", fillcolor="rgba(227,75,75,0.08)",
    ))
    figure.add_hline(y=0, line_color="#e7ebf0", line_width=1)
    figure.update_layout(
        height=170, margin=dict(l=6, r=6, t=8, b=8),
        template="plotly_white", showlegend=False,
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
    )
    figure.update_yaxes(tickformat=".0%", gridcolor="#f2f4f7")
    figure.update_xaxes(gridcolor="#f2f4f7")
    return figure


def _recent_trades(trades: pd.DataFrame) -> None:
    if trades.empty:
        st.caption("尚无已平仓交易。")
        return
    visible = pd.DataFrame({
        "Date": pd.to_datetime(trades.get("exit_date"), errors="coerce").dt.strftime("%Y-%m-%d"),
        "Symbol": trades.get("symbol"),
        "Action": "SELL",
        "Price": pd.to_numeric(trades.get("exit_execution"), errors="coerce").map(
            lambda value: f"{value:.2f}" if pd.notna(value) else "—"),
        "Return": pd.to_numeric(trades.get("net_return"), errors="coerce").map(
            lambda value: f"{value:+.2%}" if pd.notna(value) else "—"),
        "Exit Reason": trades.get("exit_reason"),
    })
    st.dataframe(visible.tail(8).iloc[::-1], hide_index=True, width="stretch",
                 height=238)


def _event_message(row: dict) -> str:
    kind = row.get("kind") or ""
    payload = row.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    if kind == "created":
        return "已创建回测"
    if kind == "started":
        return "回测开始"
    if kind == "completed":
        return "回测完成"
    if kind == "progress":
        date = str(payload.get("date") or "")[:10]
        done = payload.get("completed_sessions")
        total = payload.get("total_sessions")
        return f"回测进度 {done}/{total} · {date}"
    if kind == "order":
        symbol = payload.get("symbol") or "—"
        state = payload.get("status") or "订单"
        return f"{symbol} · {state}"
    if kind == "failed":
        return "回测失败；详情见运行状态"
    if kind == "cancelled":
        return "回测已取消"
    return str(kind).replace("_", " ").title()


def _activity(events: pd.DataFrame) -> None:
    if events.empty:
        st.caption("暂无运行活动。")
        return
    visible = events.tail(7).iloc[::-1]
    for row in visible.to_dict("records"):
        st.caption(f"{str(row.get('at') or '')[11:19]}  {_event_message(row)}")


def _preview(manager, current_id: str) -> None:
    runs = [
        run for run in manager.store.list_runs(limit=30)
        if run.get("status") == "completed" and run.get("run_id") != current_id
    ][:3]
    if not runs:
        st.caption("还没有可对比的已完成运行。")
    else:
        for run in runs:
            meta = run.get("metadata") or {}
            name = meta.get("strategy_name") or meta.get("strategy_id") or "Strategy"
            value = (run.get("metrics") or {}).get("total_return")
            st.markdown(f"**{name} · {str(run['run_id'])[:8]}** &nbsp; {_pct(value)}")
    if st.button("Open Compare", key=f"lab_compare_{current_id}", width="stretch"):
        st.session_state["radar_lab_page"] = "Compare"
        st.rerun()


def render_run_panels(manager, run: dict) -> None:
    run_id = str(run["run_id"])
    events = manager.store.get_events(run_id)
    stored = manager.store.get_equity(run_id)
    capital = _initial_capital(run)
    curve = equity_curve(stored, events, capital)
    trades = manager.store.get_trades(run_id)
    positions = _positions(run)
    capital, equity, cash, drawdown, closed = _latest_values(run, curve, trades)
    cards = st.columns(6, gap="small")
    cards[0].metric("Current Equity", _money(equity))
    cards[1].metric("Return", _pct(float(equity) / capital - 1)
                    if equity is not None and capital else "—")
    cards[2].metric("Drawdown", f"{float(drawdown):.2%}" if drawdown is not None else "—")
    cards[3].metric("Cash %", f"{float(cash) / float(equity):.2%}"
                    if cash is not None and equity else "—")
    cards[4].metric("Open Positions", len(positions))
    cards[5].metric("Closed Trades", closed)

    left, right = st.columns([2.4, 1], gap="small")
    with left:
        st.markdown("**Equity Curve**")
        if curve.empty:
            st.info("等待首个交易日权益数据。")
        else:
            st.plotly_chart(_equity_chart(manager, curve, capital),
                            width="stretch", key=f"lab_equity_{run_id}")
        st.markdown("**Drawdown Curve**")
        if curve.empty:
            st.caption("暂无回撤数据。")
        else:
            st.plotly_chart(_drawdown_chart(curve), width="stretch",
                            key=f"lab_drawdown_{run_id}")
    with right:
        st.markdown("**Current Positions**")
        if positions:
            st.dataframe(pd.DataFrame(positions), hide_index=True,
                         width="stretch", height=215)
        else:
            st.caption("当前无持仓。")
        heading, edit = st.columns([2, 1])
        heading.markdown("**Parameters**")
        meta = run.get("metadata") or {}
        config = meta.get("config") or {}
        reference = f"{meta.get('strategy_id')}@{meta.get('strategy_version')}"
        with edit:
            with st.popover("Edit"):
                st.caption("用于下一次运行，不改写本次结果。")
                draft = st.session_state.setdefault("lab_drafts", {}).setdefault(
                    reference, _plain(config)
                )
                st.session_state["lab_drafts"][reference] = _config_controls(
                    draft, reference
                )
        if config:
            items = list(config.items())[:8]
            for name, value in items:
                display = str(value)
                if isinstance(value, Mapping):
                    display = "…"
                st.caption(f"{name.replace('_', ' ').title()}   {display}")
        else:
            st.caption("此运行未记录策略参数。")

    a, b, c = st.columns(3, gap="small")
    with a:
        st.markdown("**Recent Trades**")
        _recent_trades(trades)
    with b:
        st.markdown("**Logs / Activity**")
        _activity(events)
    with c:
        st.markdown("**Compare Preview**")
        _preview(manager, run_id)
