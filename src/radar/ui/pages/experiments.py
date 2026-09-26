"""Systematic experiments backed by the existing run manager."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import pandas as pd
import streamlit as st

from radar.lab.experiments import queue_experiment, summarize_experiments

KINDS = {"Grid Search": "grid", "Ablation": "ablation", "Walk-forward": "walk_forward"}


def _example_grid(config: Mapping) -> str:
    for name, value in config.items():
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            return json.dumps({name: [value]}, ensure_ascii=False, indent=2)
    return "{}"


def _new_experiment(manager, registrations: list) -> None:
    with st.expander("New Experiment", expanded=False):
        if not registrations:
            st.info("请先导入策略，再创建实验。")
            return
        by_id = {item.manifest.id: item for item in registrations}
        with st.form("experiment_create"):
            kind_label = st.selectbox("实验类型", list(KINDS))
            strategy_id = st.selectbox(
                "策略", list(by_id), format_func=lambda key: by_id[key].manifest.name,
            )
            split = st.selectbox(
                "研究时段", ["validation", "train"],
                format_func=lambda key: "验证期" if key == "validation" else "训练期",
            )
            slippage = st.number_input(
                "单边滑点（基点）", min_value=0.0, max_value=100.0,
                value=10.0, step=1.0,
            )
            grid_text = st.text_area(
                "参数网格（JSON，仅 Grid Search 使用）",
                value=_example_grid(by_id[strategy_id].config), height=100,
            )
            submitted = st.form_submit_button("Queue Experiment", type="primary")
        if not submitted:
            return
        kind = KINDS[kind_label]
        grid = None
        if kind == "grid":
            try:
                grid = json.loads(grid_text)
                if not isinstance(grid, dict) or not grid or not all(
                    isinstance(values, list) and values for values in grid.values()
                ):
                    raise ValueError("请输入参数名到非空列表的 JSON 对象。")
            except ValueError as exc:
                st.error(f"参数网格无效：{exc}")
                return
        try:
            result = queue_experiment(
                manager, kind=kind, strategy_id=strategy_id, split=split,
                grid=grid, slippage_bps=float(slippage),
            )
        except Exception as exc:
            st.error(f"无法创建实验：{exc}")
        else:
            st.success(f"已创建 {result['count']} 个运行。")
            st.rerun()


def _duration(group: list[dict]) -> str:
    starts = [run.get("created_at") for run in group if run.get("created_at")]
    ends = [run.get("finished_at") or run.get("updated_at") for run in group
            if run.get("finished_at") or run.get("updated_at")]
    if not starts or not ends:
        return "—"
    try:
        start = datetime.fromisoformat(min(starts).replace("Z", "+00:00"))
        end = datetime.fromisoformat(max(ends).replace("Z", "+00:00"))
        return str(end - start).split(".")[0]
    except ValueError:
        return "—"


def render_experiments(manager) -> None:
    st.title("Experiments")
    st.caption("系统化运行参数网格、阶段消融和滚动验证。")
    registrations = manager.list_strategies()
    _new_experiment(manager, registrations)
    names = {item.manifest.id: item.manifest.name for item in registrations}
    runs = manager.store.list_runs(limit=1000)
    summaries = summarize_experiments(runs)
    if not summaries:
        st.info("还没有实验。可使用上方 New Experiment 创建。")
        return
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        experiment = (run.get("metadata") or {}).get("experiment") or {}
        if experiment.get("id"):
            grouped.setdefault(experiment["id"], []).append(run)
    rows = []
    for summary in summaries:
        group = grouped.get(summary["id"], [])
        statuses = {run["status"] for run in group}
        if statuses & {"running", "queued", "cancel_requested"}:
            status = "Running"
        elif statuses == {"completed"}:
            status = "Completed"
        elif "failed" in statuses:
            status = "Failed"
        else:
            status = "Cancelled"
        starts = [run.get("created_at") for run in group if run.get("created_at")]
        rows.append({
            "Name": summary["id"][:8],
            "Type": next((label for label, kind in KINDS.items()
                          if kind == summary["kind"]), summary["kind"]),
            "Strategy": names.get(summary["strategy_id"], summary["strategy_id"]),
            "Status": status,
            "Variants": summary["total"],
            "Completed": f"{summary['completed']} / {summary['total']}",
            "Start Time": min(starts).replace("T", " ")[:16] + " UTC" if starts else "—",
            "Duration": _duration(group),
            "Actions": "View ↓",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    by_id = {summary["id"]: summary for summary in summaries}
    chosen = st.selectbox("查看实验", list(by_id), format_func=lambda key: key[:8])
    st.caption("每个变体均由正式回测引擎独立执行；测试期不用于参数实验。")
    details = pd.DataFrame(by_id[chosen]["runs"])
    if not details.empty:
        details["run_id"] = details["run_id"].str[:8]
        for column in ("total_return", "max_drawdown"):
            if column in details:
                details[column] = details[column].map(
                    lambda value: f"{float(value):+.2%}" if value is not None else "—"
                )
    st.dataframe(details, hide_index=True, width="stretch")
