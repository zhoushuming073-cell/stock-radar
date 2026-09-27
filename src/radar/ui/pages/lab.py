"""Primary Strategy Lab view; all research runs use the existing manager."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import streamlit as st
import yaml

from radar.backtest.runner import split_dates
from radar.strategy_lab_ui import _plain, _progress_fraction
from radar.ui.pages.lab_timeline import available_batches, render_timeline


def _import_strategy(manager, key: str) -> None:
    uploaded = st.file_uploader("策略插件 ZIP", type=["zip"], key=key)
    if uploaded is None or not st.button("验证并导入", key=f"{key}_button"):
        return
    try:
        with TemporaryDirectory(prefix="stock-radar-import-") as directory:
            path = Path(directory) / "strategy.zip"
            path.write_bytes(uploaded.getvalue())
            registration = manager.import_zip(path)
        st.success(f"已导入 {registration.manifest.name} {registration.manifest.version}")
        st.rerun()
    except Exception as exc:
        st.error(f"导入失败：{exc}")


@st.cache_data(ttl=3600, show_spinner=False)
def _window_labels(database: str, research_path: str, database_stamp: int) -> dict[str, str]:
    try:
        windows = split_dates(Path(database), Path(research_path))
        return {split: f"{windows[split][0].date()} → {windows[split][1].date()}"
                for split in ("train", "validation", "test")}
    except Exception:
        return {"train": "训练期", "validation": "验证期", "test": "历史测试期"}


def _toolbar(manager, selected: str | None) -> None:
    research_path = manager.root / "config" / "research.yaml"
    labels = _window_labels(str(manager.database), str(research_path),
                            manager.database.stat().st_mtime_ns)
    a, b, c, d, pace, timeline, e = st.columns(
        [1.2, 1.8, 1.1, 1.0, 0.9, 1.4, 1.1], gap="small")
    with a:
        with st.popover("＋ Import Strategy", width="stretch"):
            _import_strategy(manager, "lab_import")
    with b:
        st.selectbox(
            "Date Range", ["validation", "train", "test"],
            format_func=lambda split: labels[split], key="lab_split",
        )
    with c:
        research = yaml.safe_load(
            research_path.read_text(encoding="utf-8")
        ) or {}
        profile = (research.get("illustrative_costs") or {}).get("profile") or "当前配置"
        st.selectbox("Fee Profile", [profile], disabled=True, key="lab_fee_profile")
    with d:
        st.number_input("Slippage (bps)", min_value=0.0, max_value=100.0,
                        value=10.0, step=1.0, key="lab_slippage")
    with pace:
        st.selectbox("逐日间隔", [1000, 2000],
                     format_func=lambda value: f"{value / 1000:g} 秒", key="lab_timeline_pace")
    with timeline:
        st.write("")
        if st.button("▷ 三阶段逐日回测", type="primary", disabled=not selected,
                     width="stretch", key="lab_start_timeline"):
            draft = st.session_state.get("lab_drafts", {}).get(selected)
            configs = {selected: _plain(draft)} if draft is not None else None
            try:
                batch_id = str(uuid4())
                predecessor = None
                for split in ("train", "validation", "test"):
                    predecessor = manager.queue_runs(
                        [selected], split=split,
                        slippage_bps=float(st.session_state["lab_slippage"]),
                        configs_by_strategy=configs, batch_id=batch_id,
                        after_run_id=predecessor,
                        pace_ms=int(st.session_state["lab_timeline_pace"]),
                    )[0]
                manager.launch_queued()
                st.session_state["lab_timeline_batch"] = batch_id
                st.session_state["lab_view"] = "三阶段时间线"
                st.rerun()
            except Exception as exc:
                st.error(f"无法启动三阶段回测：{exc}")
    with e:
        st.write("")
        if st.button("单阶段运行", disabled=not selected,
                     width="stretch", key="lab_run_selected"):
            draft = st.session_state.get("lab_drafts", {}).get(selected)
            configs = {selected: _plain(draft)} if draft is not None else None
            try:
                created = manager.queue_runs(
                    [selected], split=st.session_state["lab_split"],
                    slippage_bps=float(st.session_state["lab_slippage"]),
                    configs_by_strategy=configs,
                )
                manager.launch_queued()
                st.session_state["lab_run_choice"] = created[0]
                st.success("回测已在后台启动。")
                st.rerun()
            except Exception as exc:
                st.error(f"无法启动回测：{exc}")


def _status(manager, run: dict, runs: list[dict]) -> None:
    status = str(run.get("status") or "queued")
    labels = {
        "queued": "QUEUED", "running": "RUNNING",
        "cancel_requested": "STOPPING", "completed": "COMPLETED",
        "failed": "FAILED", "cancelled": "CANCELLED",
    }
    progress = run.get("progress") or {}
    metadata = run.get("metadata") or {}
    name = metadata.get("strategy_name") or metadata.get("strategy_id") or "Strategy"
    heading, state, session, stop = st.columns([2.4, 1.2, 1.3, 0.9], gap="small")
    title, history = heading.columns([3, 1], gap="small")
    title.markdown(f"### {name}")
    with history:
        with st.popover("Runs", width="stretch"):
            ids = [item["run_id"] for item in runs]
            st.selectbox(
                "历史运行", ids, key="lab_run_choice",
                format_func=lambda run_id: next(
                    f"{item['created_at']} · {item['status']} · {run_id[:8]}"
                    for item in runs if item["run_id"] == run_id
                ),
            )
    fraction = _progress_fraction(run)
    state.markdown(f"**{labels.get(status, status.upper())} · {fraction:.0%}**")
    current_date = progress.get("date") or run.get("current_date") or "—"
    done = progress.get("completed_sessions") or 0
    total = progress.get("total_sessions") or 0
    session.caption(f"{str(current_date)[:10]} · Day {done}/{total}")
    if status in {"running", "queued"}:
        if stop.button("Stop", key=f"lab_stop_{run['run_id']}", width="stretch"):
            manager.cancel(run["run_id"])
            st.rerun()
    st.progress(fraction)
    if status == "failed":
        st.error("本次回测失败。")
        with st.expander("技术详情"):
            st.code(run.get("error_text") or "未记录错误详情")


def _run_content(manager, selected: str) -> None:
    from radar.ui.pages.lab_panels import render_run_panels

    manager.launch_queued()
    runs = [
        run for run in manager.store.list_runs(limit=100)
        if f"{(run.get('metadata') or {}).get('strategy_id')}@"
        f"{(run.get('metadata') or {}).get('strategy_version')}" == selected
    ]
    if not runs:
        st.info("还没有这个策略的回测。选择时段与滑点后点击 Run Selected。")
        return
    ids = [run["run_id"] for run in runs]
    if st.session_state.get("lab_run_choice") not in ids:
        st.session_state["lab_run_choice"] = ids[0]
    chosen = st.session_state["lab_run_choice"]
    record = next(run for run in runs if run["run_id"] == chosen)
    _status(manager, record, runs)
    exits = (record.get("metadata") or {}).get("execution_policy") or {}
    st.caption("本策略退出规则 · 止盈：{} · 止损：{} · 最长持有：{}".format(
        _exit_value(exits.get("take_profit"), percent=True),
        _exit_value(exits.get("stop_loss"), percent=True),
        _exit_value(exits.get("max_holding_sessions"))))
    render_run_panels(manager, record)


def _exit_value(value, *, percent: bool = False) -> str:
    if value is None:
        return "Off"
    return f"{value:+.0%}" if percent else f"{value} 个交易日"


@st.fragment(run_every="2s")
def _live_content(manager, selected: str) -> None:
    _run_content(manager, selected)


def render_lab(manager) -> None:
    st.title("Strategy Lab")
    registrations = sorted(
        manager.list_strategies(),
        key=lambda item: (item.manifest.id != "full_strategy2_v1", item.manifest.name),
    )
    by_ref = {
        f"{item.manifest.id}@{item.manifest.version}": item
        for item in registrations
    }
    references = list(by_ref)
    if references and st.session_state.get("lab_active_strategy") not in by_ref:
        st.session_state["lab_active_strategy"] = references[0]
    selected = st.session_state.get("lab_active_strategy") if references else None
    if not references:
        st.info("尚未加载策略。点击 Import Strategy 导入插件后开始。")
        return
    tabs, add = st.columns([7, 1], gap="small")
    with tabs:
        selected = st.segmented_control(
            "Strategy Tabs", references, key="lab_active_strategy",
            format_func=lambda ref: by_ref[ref].manifest.name,
            label_visibility="collapsed", width="stretch",
        )
    with add:
        with st.popover("＋", width="stretch"):
            _import_strategy(manager, "lab_add_import")
    if selected is None:
        st.info("请选择策略。")
        return
    registration = by_ref[selected]
    if st.session_state.get("lab_previous_strategy") != selected:
        st.session_state.pop("lab_run_choice", None)
        st.session_state["lab_previous_strategy"] = selected
    drafts = st.session_state.setdefault("lab_drafts", {})
    drafts.setdefault(selected, _plain(registration.config))
    mode = st.segmented_control("研究模式", ["Scanner Research", "Strategy Backtest"],
                                default="Scanner Research", key="lab_research_mode",
                                width="stretch")
    if mode == "Scanner Research":
        from radar.ui.pages.lab_scanner import render_scanner
        render_scanner(manager, selected, drafts[selected])
        return
    _toolbar(manager, selected)
    all_runs = manager.store.list_runs(limit=100)
    batches = available_batches(all_runs, selected)
    view = st.segmented_control(
        "视图", ["三阶段时间线", "单阶段运行"],
        key="lab_view", default="三阶段时间线" if batches else "单阶段运行",
        width="stretch",
    )
    if view == "三阶段时间线":
        if not batches:
            st.info("此策略还没有三阶段运行，点击上方“三阶段逐日回测”启动。")
            return
        ids = [batch["id"] for batch in batches]
        if st.session_state.get("lab_timeline_batch") not in ids:
            st.session_state["lab_timeline_batch"] = ids[0]
        chosen_batch = st.selectbox(
            "三阶段运行记录", ids, key="lab_timeline_batch",
            format_func=lambda value: next(
                f"{item['runs']['train']['created_at'][:10]} · "
                f"{item['runs']['train']['metadata']['strategy_name']} · {value[:8]}"
                for item in batches if item["id"] == value),
        )
        render_timeline(manager, chosen_batch)
        return
    if any(
        run["status"] in {"running", "queued", "cancel_requested"}
        for run in manager.store.list_runs(limit=100)
        if f"{(run.get('metadata') or {}).get('strategy_id')}@"
        f"{(run.get('metadata') or {}).get('strategy_version')}" == selected
    ):
        _live_content(manager, selected)
    else:
        _run_content(manager, selected)
