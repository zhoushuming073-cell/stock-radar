"""Trading-day timeline shared by the three sequential Lab runs."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from radar.strategy_lab_ui import _money, _pct

STAGES = ("train", "validation", "test")
NAMES = {"train": "训练期", "validation": "验证期", "test": "测试期"}
COLORS = ("#2563eb", "#13a66a", "#a463dd")


def available_batches(runs: list[dict], strategy_ref: str) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        meta = run.get("metadata") or {}
        if f"{meta.get('strategy_id')}@{meta.get('strategy_version')}" != strategy_ref:
            continue
        if meta.get("batch_id"):
            grouped.setdefault(meta["batch_id"], []).append(run)
    return [
        {"id": batch_id, "runs": {stage: next(
            run for run in members if run["metadata"]["split"] == stage)
            for stage in STAGES}}
        for batch_id, members in grouped.items()
        if {run["metadata"]["split"] for run in members} >= set(STAGES)
    ]


def _snapshots(manager, batch: dict) -> list[dict]:
    cache = st.session_state.setdefault("lab_timeline_cache", {})
    item = cache.get(batch["id"])
    ids = [batch["runs"][stage]["run_id"] for stage in STAGES]
    if item is None or item["ids"] != ids:
        item = {"ids": ids, "frames": [[], [], []], "cursors": [0, 0, 0]}
        cache[batch["id"]] = item
    for stage_index, run_id in enumerate(ids):
        while True:
            rows = manager.store.get_daily_snapshots(
                run_id, after_event_id=item["cursors"][stage_index])
            item["frames"][stage_index].extend(rows)
            if rows:
                item["cursors"][stage_index] = rows[-1]["event_id"]
            if len(rows) < 200:
                break
    return [{**row, "stage": stage} for stage, rows in zip(STAGES, item["frames"])
            for row in rows]


def _curve(frames: list[dict], batch: dict, index: int, *, drawdown: bool) -> go.Figure:
    shown = frames[:index + 1]
    figure = go.Figure()
    for stage, color in zip(STAGES, COLORS):
        rows = [row for row in shown if row["stage"] == stage]
        capital = float(batch["runs"][stage]["metadata"]["execution_policy"]["initial_capital"])
        values = ([float(row["drawdown"]) * 100 for row in rows] if drawdown else
                  [(float(row["equity"]) / capital - 1) * 100 for row in rows])
        figure.add_trace(go.Scatter(
            x=[str(row["date"])[:10] for row in rows], y=values,
            name=NAMES[stage], mode="lines", line={"color": color, "width": 2},
        ))
    start = batch["runs"]["train"]["metadata"]["start_date"]
    end = batch["runs"]["test"]["metadata"]["evaluation_end"]
    figure.update_layout(
        height=170 if drawdown else 320, template="plotly_white",
        margin=dict(l=6, r=6, t=8, b=10), hovermode="x unified",
        showlegend=not drawdown,
        legend={"orientation": "h", "y": -0.18},
        xaxis={"range": [start, end], "gridcolor": "#edf1f6"},
        yaxis={"ticksuffix": "%", "gridcolor": "#edf1f6"},
    )
    return figure


@st.fragment(run_every="1s")
def render_timeline(manager, batch_id: str) -> None:
    manager.launch_queued()
    runs = manager.store.list_runs(limit=100)
    members = [run for run in runs if (run.get("metadata") or {}).get("batch_id") == batch_id]
    if len(members) != 3:
        st.info("正在读取三阶段运行。")
        return
    batch = {"id": batch_id, "runs": {run["metadata"]["split"]: run for run in members}}
    frames = _snapshots(manager, batch)
    terminal = all(run["status"] in {"completed", "failed", "cancelled"} for run in members)
    if not frames:
        st.info("训练期正在准备数据，等待第一个交易日。")
        return
    key = f"lab_timeline_seek_{batch_id}"
    pause_key = f"lab_timeline_paused_{batch_id}"
    if key not in st.session_state:
        st.session_state[key] = len(frames) - 1 if terminal else 0
    elif not st.session_state.get(pause_key, False):
        st.session_state[key] = min(int(st.session_state[key]) + 1, len(frames) - 1)
    index = min(int(st.session_state[key]), len(frames) - 1)
    st.session_state[key] = index
    frame = frames[index]
    stage = frame["stage"]
    metadata = batch["runs"][stage]["metadata"]
    capital = float(metadata["execution_policy"]["initial_capital"])
    st.markdown(f"### {metadata.get('strategy_name', '策略')} · 三阶段逐日时间线")
    st.caption("训练 → 验证 → 测试，按交易日计算；每阶段独立重置资金和持仓。收盘信号在次交易日开盘成交。")
    left, right = st.columns([4, 1], gap="small")
    left.markdown(f"**{NAMES[stage]}** · {str(frame['date'])[:10]} · "
                  f"第 {frame['completed_sessions']}/{frame['total_sessions']} 个交易日")
    if right.button("继续画面" if st.session_state.get(pause_key) else "暂停画面",
                    key=f"lab_timeline_pause_{batch_id}", width="stretch"):
        st.session_state[pause_key] = not st.session_state.get(pause_key, False)
        st.rerun(scope="fragment")

    if len(frames) > 1:
        st.slider("交易日（拖动可检查当日持仓）", min_value=0, max_value=len(frames) - 1,
                  key=key, on_change=lambda: st.session_state.__setitem__(pause_key, True))
        index = int(st.session_state[key])
        frame = frames[index]
        stage = frame["stage"]
        capital = float(batch["runs"][stage]["metadata"]["execution_policy"]["initial_capital"])
    selected = [row for row in frames[:index + 1] if row["stage"] == stage]
    worst = min(float(row["drawdown"]) for row in selected)
    positions = frame.get("open_positions") or []
    cards = st.columns(5, gap="small")
    cards[0].metric("当日权益", _money(frame["equity"]))
    cards[1].metric("阶段收益", _pct(float(frame["equity"]) / capital - 1))
    cards[2].metric("阶段最大回撤", _pct(worst))
    cards[3].metric("当前持仓", len(positions))
    cards[4].metric("已平仓", int(frame.get("closed_trades") or 0))
    chart_col, holdings_col = st.columns([2.4, 1], gap="small")
    with chart_col:
        st.markdown("**逐日收益曲线（各阶段从 0% 开始）**")
        st.plotly_chart(_curve(frames, batch, index, drawdown=False), width="stretch",
                        key=f"lab_timeline_equity_{batch_id}")
        st.markdown("**逐日回撤**")
        st.plotly_chart(_curve(frames, batch, index, drawdown=True), width="stretch",
                        key=f"lab_timeline_drawdown_{batch_id}")
    with holdings_col:
        st.markdown(f"**{str(frame['date'])[:10]} 收盘持仓**")
        if positions:
            st.dataframe(pd.DataFrame(positions)[[
                "symbol", "quantity", "cost_basis", "last_close", "unrealized_pnl"]],
                hide_index=True, width="stretch", height=270)
        else:
            st.caption("当日收盘无持仓。")
        st.caption("暂停仅暂停画面，后台回测继续。日线只用开盘/收盘价，不模拟盘中触价。")
