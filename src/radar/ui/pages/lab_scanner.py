"""Candidate-first Scanner Research page for the local Streamlit lab."""

from __future__ import annotations

import pandas as pd
import streamlit as st


@st.fragment(run_every="3s")
def render_scanner(manager, strategy_ref: str, draft: dict) -> None:
    st.subheader("Scanner Research · 候选股研究")
    st.caption("按交易日筛选与排序；未来结果由主程序事后标注，不创建持仓或模拟交易。")
    a, c = st.columns([1.4, 1])
    split = a.selectbox("研究时段", ["validation", "train", "test"],
                        format_func=lambda x: {"validation": "验证期", "train": "训练期",
                                               "test": "历史测试期"}[x], key="scanner_split")
    if c.button("运行 Scanner", type="primary", width="stretch"):
        try:
            run_id = manager.queue_scanner(strategy_ref, split=split,
                                           config_override=draft)
            manager.launch_queued_scanners()
            st.session_state["scanner_run_choice"] = run_id
            st.rerun()
        except Exception as error:
            st.error(f"无法启动 Scanner：{error}")
    manager.launch_queued_scanners()
    runs = [run for run in manager.store.list_scanner_runs(limit=100)
            if f"{run['metadata']['strategy_id']}@{run['metadata']['strategy_version']}" == strategy_ref]
    if not runs:
        st.info("暂无候选股研究记录。")
        return
    ids = [run["run_id"] for run in runs]
    if st.session_state.get("scanner_run_choice") not in ids:
        st.session_state["scanner_run_choice"] = ids[0]
    chosen = st.selectbox("Scanner 运行记录", ids, key="scanner_run_choice",
                          format_func=lambda run_id: next(
                              f"{item['created_at'][:16]} · {item['status']} · {run_id[:8]}"
                              for item in runs if item["run_id"] == run_id))
    run = manager.store.get_scanner_run(chosen)
    top_k_values = run["metadata"].get("evaluation", {}).get("top_k_values", [5, 10, 20])
    display_k = st.selectbox("显示候选数（仅视图）", top_k_values,
                             index=top_k_values.index(10) if 10 in top_k_values else 0,
                             key=f"scanner_display_k_{chosen}")
    status = run["status"]
    progress = run.get("progress") or {}
    if run["metadata"].get("universe_mode") != "point_in_time":
        st.warning("Universe: Current Snapshot · Survivorship Bias Risk: Present")
    st.caption(f"状态：{status} · {progress.get('date', '—')} · "
               f"{progress.get('completed_sessions', 0)}/{progress.get('total_sessions', 0)} 交易日")
    if status == "failed":
        st.error(run.get("error_text") or "Scanner 运行失败")
        return
    if status != "completed":
        return
    metrics = run["metrics"] or {}
    k = display_k
    horizon = run["metadata"].get("evaluation", {}).get("horizon_sessions", 10)
    boxes = st.columns(6)
    boxes[0].metric("候选快照", metrics.get("candidate_count", 0))
    boxes[1].metric("独立信号事件", metrics.get("unique_signal_event_count", "—"))
    boxes[2].metric(f"Precision@{k}", _pct(metrics.get(f"pooled_precision_at_{k}", metrics.get(f"precision_at_{k}"))))
    boxes[3].metric(f"Lift@{k}", _ratio(metrics.get(f"lift_at_{k}")))
    boxes[4].metric("平均 MFE", _pct(metrics.get(f"average_mfe_{horizon}")))
    boxes[5].metric("平均 MAE", _pct(metrics.get(f"average_mae_{horizon}")))
    event_boxes = st.columns(3)
    event_boxes[0].metric(f"有效事件@{k}", metrics.get(f"event_top_{k}_count", "—"))
    event_boxes[1].metric(f"Event Precision@{k}", _pct(metrics.get(f"event_precision_at_{k}")))
    event_boxes[2].metric(f"Event Lift@{k}", _ratio(metrics.get(f"event_lift_at_{k}")))
    st.caption(f"主要结果 {metrics.get('primary_outcome', '—')} · "
               f"背景命中率 {_pct(metrics.get('base_rate'))} · "
               f"下跌延伸率 {_pct(metrics.get('false_falling_knife_rate'))} · "
               f"有效标签 {metrics.get('labeled_candidate_count', 0)} / "
               f"{metrics.get('candidate_count', 0)}；窗口末尾不足 {horizon} 日的候选不参与命中率。")
    if metrics.get("funnel_by_day"):
        with st.expander("Filter Funnel · 每日筛选漏斗"):
            st.dataframe(pd.DataFrame(metrics["funnel_by_day"]), hide_index=True,
                         width="stretch")
            if metrics.get("near_misses"):
                st.dataframe(pd.DataFrame(metrics["near_misses"]), hide_index=True,
                             width="stretch")
    hit_rows = [{"阈值": key.replace("_rate", ""), "命中率": _pct(value)}
                for key, value in metrics.items() if key.startswith("hit_") and key.endswith("_rate")]
    if hit_rows:
        st.dataframe(hit_rows, hide_index=True, width="stretch")
    regime = [{"市场状态": label, "候选数": metrics.get(f"{label}_candidate_count"),
               "有效标签": metrics.get(f"{label}_labeled_count"),
               "主要结果成功率": _pct(metrics.get(f"{label}_success_rate",
                                         metrics.get(f"{label}_hit_rate")))}
              for label in ("spy_above_ma20", "spy_below_ma20")]
    st.markdown("#### 市场状态拆分")
    st.dataframe(regime, hide_index=True, width="stretch")
    candidates = manager.store.get_scanner_candidates(
        chosen, max_rank=max(top_k_values), limit=100000)
    if candidates:
        days = sorted({item["signal_date"] for item in candidates}, reverse=True)
        day = st.selectbox("信号日", days, key="scanner_signal_day")
        rows = []
        for item in candidates:
            if item["signal_date"] == day and item["rank"] <= k:
                rows.append({"排名": item["rank"], "代码": item["symbol"],
                             "名称": item["security_name"], "策略分": item["strategy_score"],
                             "入选": item["selected"],
                             "独立信号事件": item.get("signal_event"),
                             **item["diagnostics"],
                             **item["probabilities"], **(item["label"] or {})})
        st.markdown("#### 每日 Top-K 候选与事后标签")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        visible = [item for item in candidates if item["signal_date"] == day and item["rank"] <= k]
        if visible:
            with st.expander("查看候选当日输入特征"):
                symbols = [item["symbol"] for item in visible]
                chosen_symbol = st.selectbox("候选", symbols, key="scanner_inspect_symbol")
                chosen_row = next(item for item in visible if item["symbol"] == chosen_symbol)
                st.json({"causal_features": chosen_row["features"],
                         "diagnostic_scores": chosen_row["diagnostics"],
                         "market_context": chosen_row["market_context"]})
    with st.expander("Audit"):
        st.caption(f"Universe: {run['metadata'].get('universe_mode', 'current_snapshot')}")
        st.caption(f"候选快照 SHA-256：{run['artifact_hashes']['candidates_sha256']}")


def _pct(value) -> str:
    return "—" if value is None else f"{value:.1%}"


def _ratio(value) -> str:
    return "—" if value is None else f"{value:.2f}×"
