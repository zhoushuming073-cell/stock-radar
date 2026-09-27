"""Candidate-first Scanner Research page for the local Streamlit lab."""

from __future__ import annotations

import pandas as pd
import streamlit as st


@st.fragment(run_every="3s")
def render_scanner(manager, strategy_ref: str, draft: dict) -> None:
    st.subheader("Scanner Research · 候选股研究")
    st.caption("按交易日筛选与排序；未来结果由主程序事后标注，不创建持仓或模拟交易。")
    a, b, c = st.columns([1.4, 1.3, 1])
    split = a.selectbox("研究时段", ["validation", "train", "test"],
                        format_func=lambda x: {"validation": "验证期", "train": "训练期",
                                               "test": "历史测试期"}[x], key="scanner_split")
    maximum = b.selectbox("每日期望候选数", [5, 10, 20, None],
                          format_func=lambda x: "全部" if x is None else f"Top {x}",
                          index=2, key="scanner_maximum")
    if c.button("运行 Scanner", type="primary", width="stretch"):
        try:
            run_id = manager.queue_scanner(strategy_ref, split=split,
                                           max_candidates=maximum, config_override=draft)
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
    status = run["status"]
    progress = run.get("progress") or {}
    st.caption(f"状态：{status} · {progress.get('date', '—')} · "
               f"{progress.get('completed_sessions', 0)}/{progress.get('total_sessions', 0)} 交易日")
    if status == "failed":
        st.error(run.get("error_text") or "Scanner 运行失败")
        return
    if status != "completed":
        return
    metrics = run["metrics"] or {}
    k = st.segmented_control("Top-K", [5, 10, 20], default=10,
                             key="scanner_top_k") or 10
    boxes = st.columns(5)
    boxes[0].metric("候选快照", metrics.get("candidate_count", 0))
    boxes[1].metric(f"Precision@{k}", _pct(metrics.get(f"precision_at_{k}")))
    boxes[2].metric(f"Lift@{k}", _ratio(metrics.get(f"lift_at_{k}")))
    boxes[3].metric("平均 MFE", _pct(metrics.get("average_mfe_10")))
    boxes[4].metric("平均 MAE", _pct(metrics.get("average_mae_10")))
    st.caption(f"背景命中率 {_pct(metrics.get('base_rate'))} · "
               f"下跌延伸率 {_pct(metrics.get('false_falling_knife_rate'))} · "
               f"有效标签 {metrics.get('labeled_candidate_count', 0)} / "
               f"{metrics.get('candidate_count', 0)}；窗口末尾不足 10 日的候选不参与命中率。")
    hit_rows = [{"阈值": key.replace("_rate", ""), "命中率": _pct(value)}
                for key, value in metrics.items() if key.startswith("hit_") and key.endswith("_rate")]
    if hit_rows:
        st.dataframe(hit_rows, hide_index=True, width="stretch")
    regime = [{"市场状态": label, "候选数": metrics.get(f"{label}_candidate_count"),
               "目标命中率": _pct(metrics.get(f"{label}_hit_rate"))}
              for label in ("spy_above_ma20", "spy_below_ma20")]
    st.markdown("#### 市场状态拆分")
    st.dataframe(regime, hide_index=True, width="stretch")
    candidates = manager.store.get_scanner_candidates(chosen, max_rank=20, limit=100000)
    if candidates:
        days = sorted({item["signal_date"] for item in candidates}, reverse=True)
        day = st.selectbox("信号日", days, key="scanner_signal_day")
        rows = []
        for item in candidates:
            if item["signal_date"] == day and item["rank"] <= k:
                rows.append({"排名": item["rank"], "代码": item["symbol"],
                             "名称": item["security_name"], "策略分": item["strategy_score"],
                             "入选": item["selected"], **item["diagnostics"],
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
    st.caption(f"候选快照 SHA-256：{run['artifact_hashes']['candidates_sha256']}")


def _pct(value) -> str:
    return "—" if value is None else f"{value:.1%}"


def _ratio(value) -> str:
    return "—" if value is None else f"{value:.2f}×"
