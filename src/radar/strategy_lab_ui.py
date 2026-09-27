"""Local Streamlit controller and viewer for immutable Strategy Lab Runs.

Launch with: python -m streamlit run src/radar/strategy_lab_ui.py
The UI never executes a backtest in the Streamlit process.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml


ROOT = Path(__file__).resolve().parents[2]
ACTIVE = {"queued", "running", "cancel_requested"}
STATUS_LABELS = {
    "queued": "等待中", "running": "运行中", "cancel_requested": "正在取消",
    "completed": "已完成", "failed": "失败", "cancelled": "已取消",
}


def _plain(value: Any) -> Any:
    """Turn a read-only registration config into editable YAML-safe values."""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _contains_complex(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_complex(item) for item in value.values())
    return isinstance(value, (list, tuple)) or value is None


def _config_controls(config: Mapping[str, Any], reference: str,
                     path: tuple[str, ...] = ()) -> dict[str, Any]:
    """Render declared strategy controls; unknown v1 plugins use a raw draft."""
    from radar.lab.schema import parameter_schema

    result = _plain(config)
    strategy_id = reference.split("@", 1)[0]
    schema = [item for item in parameter_schema(strategy_id, config, {}, {})
              if item["namespace"] == "strategy"]
    if not schema:
        raw = st.text_area("Run draft YAML", yaml.safe_dump(result, sort_keys=False),
                           key=f"raw_draft_{reference}", height=180,
                           help="No semantic control schema is declared for this v1 plugin.")
        try:
            parsed = yaml.safe_load(raw)
            if not isinstance(parsed, dict):
                raise ValueError("Run draft must be a mapping")
            return parsed
        except (yaml.YAMLError, ValueError) as error:
            st.error(f"Invalid run draft: {error}")
            return result

    def render_item(item: dict) -> None:
        parts = item["path"].split(".")[1:]
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        value = current.get(parts[-1])
        key = f"param__{reference}__{'__'.join(parts)}"
        label = item["label"]
        if item["type"] == "boolean":
            updated = st.checkbox(label, value=bool(value), key=key,
                                  help=item["description"])
        elif item["nullable"]:
            raw = st.text_input(label, value="" if value is None else str(value),
                                key=key, help=item["description"] + " Blank disables it.")
            try:
                updated = None if not raw.strip() else int(raw)
            except ValueError:
                st.error(f"{label} must be an integer or blank")
                updated = value
        else:
            integer = item["type"] == "integer"
            updated = st.number_input(
                label, value=int(value) if integer else float(value),
                min_value=(int(item["min"]) if integer else float(item["min"]))
                if item["min"] is not None else None,
                max_value=(int(item["max"]) if integer else float(item["max"]))
                if item["max"] is not None else None,
                step=1 if integer else float(item["step"] or .01), key=key,
                help=item["description"],
            )
        current[parts[-1]] = updated

    for item in schema:
        if item["level"] == "core":
            render_item(item)
    with st.expander("Advanced Research", expanded=False):
        for item in schema:
            if item["level"] == "advanced":
                render_item(item)
    return result


def _frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, (list, tuple)):
        return pd.DataFrame(value)
    if isinstance(value, Mapping):
        return pd.DataFrame([value])
    return pd.DataFrame()


def _progress_events(events: Any) -> pd.DataFrame:
    rows = [event.get("payload", {}) for event in _frame(events).to_dict("records")
            if event.get("kind") == "progress" and isinstance(event.get("payload"), dict)]
    return pd.DataFrame(rows)


def equity_curve(equity: Any, events: Any = None, initial_capital: float = 1_000_000) -> pd.DataFrame:
    """Use persisted result rows, or progress events while a Run is active."""
    frame = _frame(equity)
    if frame.empty:
        frame = _progress_events(events)
    if frame.empty or not {"date", "equity"}.issubset(frame.columns):
        return pd.DataFrame(columns=["date", "equity", "cash", "drawdown"])
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["equity"] = pd.to_numeric(frame["equity"], errors="coerce")
    frame = frame.dropna(subset=["date", "equity"])
    frame = frame.sort_values("date").drop_duplicates("date", keep="last")
    if "cash" not in frame:
        frame["cash"] = float("nan")
    else:
        frame["cash"] = pd.to_numeric(frame["cash"], errors="coerce")
    if "drawdown" not in frame:
        peak = frame["equity"].cummax().clip(lower=initial_capital)
        frame["drawdown"] = frame["equity"] / peak - 1
    else:
        frame["drawdown"] = pd.to_numeric(frame["drawdown"], errors="coerce")
    return frame[["date", "equity", "cash", "drawdown"]].reset_index(drop=True)


def _flatten_config(config: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in sorted(config.items()):
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            out.update(_flatten_config(value, name))
        else:
            out[name] = value
    return out


def parameter_diff(runs: list[dict[str, Any]]) -> pd.DataFrame:
    """Display only parameters whose values differ across selected Runs."""
    configs = {}
    for run in runs:
        metadata = run.get("metadata") or {}
        values = _flatten_config(metadata.get("config") or {}, "strategy")
        values.update(_flatten_config(metadata.get("execution_policy") or {}, "execution"))
        values["slippage_bps"] = metadata.get("slippage_bps")
        configs[str(run["run_id"])] = values
    names = sorted({name for config in configs.values() for name in config})
    rows = []
    for name in names:
        values = {run_id: config.get(name) for run_id, config in configs.items()}
        if len({repr(value) for value in values.values()}) > 1:
            rows.append({"参数": name, **values})
    return pd.DataFrame(rows)


def _metric(record: dict, key: str, default: Any = None) -> Any:
    progress = record.get("progress") or {}
    metrics = record.get("metrics") or {}
    return progress.get(key, metrics.get(key, default))


def _initial_capital(record: dict) -> float:
    metrics = record.get("metrics") or {}
    execution = (record.get("metadata") or {}).get("execution_policy") or {}
    return float(metrics.get("initial_capital") or execution.get("initial_capital") or 1_000_000)


def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.2%}"
    except (TypeError, ValueError):
        return "—"


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _day(value: Any) -> str:
    if not value:
        return "—"
    parsed = pd.to_datetime(value, errors="coerce")
    return str(parsed.date()) if pd.notna(parsed) else str(value)


def _progress_fraction(record: dict) -> float:
    if record.get("status") == "completed":
        return 1.0
    progress = record.get("progress") or {}
    total = progress.get("total_sessions")
    done = progress.get("completed_sessions")
    try:
        return min(1.0, max(0.0, float(done) / float(total))) if float(total) > 0 else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _run_label(record: dict) -> str:
    meta = record.get("metadata") or {}
    name = meta.get("strategy_name") or meta.get("strategy_id") or "Strategy"
    return f"{name} · {str(record['run_id'])[:8]}"


def _run_events(store: Any, run_id: str) -> pd.DataFrame:
    return _frame(store.get_events(run_id))


def _run_curve(store: Any, record: dict, events: pd.DataFrame | None = None) -> pd.DataFrame:
    run_id = str(record["run_id"])
    stored = store.get_equity(run_id)
    if events is None and _frame(stored).empty:
        events = _run_events(store, run_id)
    return equity_curve(stored, events, _initial_capital(record))


def _live_trades(stored: Any, events: pd.DataFrame) -> pd.DataFrame:
    trades = _frame(stored)
    if not trades.empty:
        return trades
    rows: list[dict[str, Any]] = []
    for payload in _progress_events(events).to_dict("records"):
        new = payload.get("new_trades")
        if isinstance(new, list):
            rows.extend(row for row in new if isinstance(row, dict))
    return pd.DataFrame(rows)


def _table(value: Any, *, empty: str, height: int = 260) -> None:
    frame = _frame(value)
    if frame.empty:
        st.caption(empty)
    else:
        st.dataframe(frame, width="stretch", height=height, hide_index=True)


def _chart(curve: pd.DataFrame, column: str, label: str, color: str, percent: bool = False) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=curve["date"], y=curve[column],
                                mode="lines", name=label,
                                line={"color": color, "width": 2}))
    figure.update_layout(height=310, margin=dict(l=10, r=10, t=20, b=10),
                         template="plotly_white", hovermode="x unified",
                         xaxis_title=None, yaxis_title=label,
                         showlegend=False)
    if percent:
        figure.update_yaxes(tickformat=".0%")
    return figure


def _render_run(manager: Any, record: dict) -> None:
    store = manager.store
    run_id = str(record["run_id"])
    status = str(record.get("status", "queued"))
    metadata = record.get("metadata") or {}
    progress = record.get("progress") or {}
    events = _run_events(store, run_id)
    curve = _run_curve(store, record, events)
    trades = _live_trades(store.get_trades(run_id), events)

    st.subheader(_run_label(record))
    st.caption(f"{STATUS_LABELS.get(status, status)} · {metadata.get('split', '—')} · "
               f"{metadata.get('start_date', '—')} 至 {metadata.get('evaluation_end', metadata.get('end_date', '—'))}")
    st.progress(_progress_fraction(record), text=f"{_progress_fraction(record):.0%} · 当前交易日 {_day(record.get('current_date'))}")
    if status in {"running", "queued"} and st.button("取消本次运行", key=f"cancel_{run_id}"):
        manager.cancel(run_id)
        st.rerun()
    if status == "failed":
        st.error(record.get("error_text") or "回测失败。请展开事件查看详情。")
    if status == "cancelled":
        st.info("本次运行已取消。")

    latest = curve.iloc[-1] if not curve.empty else None
    capital = _initial_capital(record)
    equity = float(latest["equity"]) if latest is not None else _metric(record, "equity", capital)
    cash = float(latest["cash"]) if latest is not None and pd.notna(latest["cash"]) else _metric(record, "cash")
    drawdown = float(latest["drawdown"]) if latest is not None else _metric(record, "drawdown")
    exposure = _metric(record, "gross_exposure")
    if exposure is None and equity is not None and cash is not None:
        exposure = float(equity) - float(cash)
    positions = record.get("positions")
    if positions is None:
        positions = (record.get("result") or {}).get("open_positions") or []
    closed = _metric(record, "closed_trades", len(trades))
    a, b, c, d = st.columns(4)
    a.metric("当前权益", _money(equity), _pct(float(equity) / capital - 1) if equity is not None else None)
    b.metric("当前回撤", _pct(drawdown))
    c.metric("现金占比", _pct(float(cash) / float(equity)) if cash is not None and equity else "—")
    d.metric("持仓 / 已平仓", f"{len(positions) if isinstance(positions, list) else positions} / {closed}")
    e, f = st.columns(2)
    e.metric("持仓市值", _money(exposure))
    f.metric("已用仓位", _pct(float(exposure) / float(equity)) if exposure is not None and equity else "—")

    if curve.empty:
        st.info("等待首个交易日的权益数据。")
    else:
        st.plotly_chart(_chart(curve, "equity", "权益（美元）", "#2563eb"), width="stretch", key=f"equity_{run_id}")
        st.plotly_chart(_chart(curve, "drawdown", "回撤", "#dc2626", percent=True), width="stretch", key=f"dd_{run_id}")

    left, right = st.columns(2)
    with left:
        st.markdown("#### 当前持仓")
        _table(positions, empty="当前无持仓。")
        st.markdown("#### 最近信号")
        _table(record.get("latest_signals") or [], empty="当前没有新信号。")
    with right:
        st.markdown("#### 交易记录")
        _table(trades.tail(100), empty="尚无已平仓交易。", height=360)
        fees = (record.get("metrics") or {}).get("fees")
        slip = (record.get("metrics") or {}).get("slippage_cost")
        if fees is None and not trades.empty:
            buy = pd.to_numeric(trades.get("buy_fee_total", pd.Series(dtype=float)), errors="coerce").sum()
            sell = pd.to_numeric(trades.get("sell_fee_total", pd.Series(dtype=float)), errors="coerce").sum()
            fees = buy + sell
            slip = pd.to_numeric(trades.get("slippage_cost", pd.Series(dtype=float)), errors="coerce").sum()
        st.markdown("#### 成本")
        st.write(f"已平仓交易手续费：{_money(fees)} · 已平仓交易滑点：{_money(slip)}")

    with st.expander("参数与运行来源"):
        st.json({key: value for key, value in metadata.items() if key != "data_snapshot"})
        if metadata.get("data_snapshot"):
            st.caption(f"数据快照 SHA256：{metadata['data_snapshot']}")
    with st.expander("事件日志"):
        if events.empty:
            st.caption("暂无事件。")
        else:
            log = events.tail(100).copy()
            if "payload" in log:
                log["payload"] = log["payload"].map(lambda item: str(item)[:500])
            st.dataframe(log, width="stretch", hide_index=True)


@st.cache_data(ttl=60, show_spinner=False)
def _spy_closes(database: str, start: str, end: str) -> pd.DataFrame:
    path = Path(database)
    if not path.exists():
        return pd.DataFrame(columns=["date", "close"])
    connection = duckdb.connect(str(path), read_only=True)
    try:
        frame = connection.execute(
            "SELECT date, close FROM daily_bars WHERE symbol='SPY' "
            "AND date BETWEEN ? AND ? ORDER BY date", [start, end],
        ).df()
    finally:
        connection.close()
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def _comparison_metrics(record: dict, curve: pd.DataFrame, trades: pd.DataFrame) -> dict[str, Any]:
    metrics = record.get("metrics") or {}
    capital = _initial_capital(record)
    equity = float(curve["equity"].iloc[-1]) if not curve.empty else capital
    return {
        "Run": _run_label(record),
        "状态": STATUS_LABELS.get(record.get("status"), record.get("status")),
        "净收益": metrics.get("total_return", equity / capital - 1),
        "CAGR": metrics.get("cagr"),
        "最大回撤": metrics.get("max_drawdown", curve["drawdown"].min() if not curve.empty else None),
        "Sharpe": metrics.get("sharpe"),
        "盈亏比": metrics.get("profit_factor"),
        "胜率": metrics.get("win_rate"),
        "交易数": metrics.get("trade_count", len(trades)),
        "平均持有日": metrics.get("avg_holding_sessions"),
        "平均仓位": metrics.get("avg_position_utilization"),
        "手续费": metrics.get("fees"),
        "滑点成本": metrics.get("slippage_cost"),
    }


def _render_comparison(manager: Any, runs: list[dict]) -> None:
    if not runs:
        st.info("先创建回测 Run，再选择多个 Run 对比。")
        return
    ids = st.multiselect("选择对比 Run", [str(run["run_id"]) for run in runs],
                         default=[str(run["run_id"]) for run in runs[:min(3, len(runs))]],
                         format_func=lambda run_id: _run_label(next(run for run in runs if run["run_id"] == run_id)),
                         key="comparison_ids")
    chosen = [run for run in runs if run["run_id"] in ids]
    if not chosen:
        return
    equity_fig = go.Figure()
    dd_fig = go.Figure()
    metrics_rows = []
    all_dates: list[pd.Timestamp] = []
    for run in chosen:
        run_id = str(run["run_id"])
        events = _run_events(manager.store, run_id)
        curve = _run_curve(manager.store, run, events)
        trades = _live_trades(manager.store.get_trades(run_id), events)
        metrics_rows.append(_comparison_metrics(run, curve, trades))
        if curve.empty:
            continue
        all_dates.extend(curve["date"].tolist())
        name = _run_label(run)
        equity_fig.add_trace(go.Scatter(x=curve["date"], y=curve["equity"] / _initial_capital(run) * 100,
                                        mode="lines", name=name))
        dd_fig.add_trace(go.Scatter(x=curve["date"], y=curve["drawdown"],
                                    mode="lines", name=name))
    if all_dates:
        first, last = min(all_dates), max(all_dates)
        starts = {str((run.get("metadata") or {}).get("start_date")) for run in chosen}
        if len(starts) > 1:
            st.warning("所选 Run 的开始日期不同；曲线各自从其首日归一化，对比时请留意时段差异。")
        spy = _spy_closes(str(manager.database), str(first.date()), str(last.date()))
        if not spy.empty and float(spy["close"].iloc[0]) > 0:
            equity_fig.add_trace(go.Scatter(x=spy["date"],
                                            y=spy["close"] / float(spy["close"].iloc[0]) * 100,
                                            mode="lines", name="SPY 收盘价基准（未计成本）",
                                            line={"dash": "dot", "color": "#64748b"}))
        equity_fig.add_trace(go.Scatter(x=[first, last], y=[100, 100], mode="lines",
                                        name="现金基准", line={"dash": "dash", "color": "#94a3b8"}))
        for fig, title in ((equity_fig, "权益对比（初始 = 100）"), (dd_fig, "回撤对比")):
            fig.update_layout(title=title, height=370, template="plotly_white",
                              hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10))
        dd_fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(equity_fig, width="stretch", key="comparison_equity")
        st.plotly_chart(dd_fig, width="stretch", key="comparison_drawdown")
    table = pd.DataFrame(metrics_rows)
    styled = table.style.format({
        "净收益": "{:+.2%}", "CAGR": "{:+.2%}", "最大回撤": "{:.2%}",
        "胜率": "{:.2%}", "平均仓位": "{:.2%}",
        "手续费": "${:,.0f}", "滑点成本": "${:,.0f}",
    }, na_rep="—")
    st.dataframe(styled, width="stretch", hide_index=True)
    st.caption("运行中指标为暂估值；已完成指标取保存的回测结果。SPY 为同期收盘价变化，未计交易成本。")


def _render_parameter_diff(runs: list[dict]) -> None:
    if len(runs) < 2:
        st.info("至少需要两个 Run 才能比较参数。")
        return
    ids = st.multiselect("选择要比较的 Run", [str(run["run_id"]) for run in runs],
                         default=[str(run["run_id"]) for run in runs[:2]],
                         format_func=lambda run_id: _run_label(next(run for run in runs if run["run_id"] == run_id)),
                         key="diff_ids")
    selected = [run for run in runs if run["run_id"] in ids]
    if len(selected) < 2:
        st.caption("请选择至少两个 Run。")
        return
    diff = parameter_diff(selected)
    if diff.empty:
        st.info("这些 Run 的策略参数相同。")
    else:
        diff = diff.rename(columns={str(run["run_id"]): _run_label(run) for run in selected})
        for column in diff.columns.drop("参数"):
            diff[column] = diff[column].map(lambda value: "—" if value is None else str(value))
        st.dataframe(diff, width="stretch", hide_index=True)


@st.fragment(run_every="1s")
def _live_area(manager: Any) -> None:
    manager.refresh()
    manager.launch_queued()
    runs = manager.store.list_runs(limit=100)
    run_tab, compare_tab, diff_tab = st.tabs(["运行看板", "策略对比", "参数对比"])
    with run_tab:
        if not runs:
            st.info("还没有回测。请在左侧选择策略并启动。")
        else:
            tabs = st.tabs([_run_label(run) for run in runs])
            for tab, run in zip(tabs, runs):
                with tab:
                    _render_run(manager, run)
    with compare_tab:
        _render_comparison(manager, runs)
    with diff_tab:
        _render_parameter_diff(runs)


def _clone_controls(manager: Any, registrations: dict[str, Any]) -> None:
    runs = manager.store.list_runs(limit=100)
    if not runs:
        return
    with st.sidebar.expander("克隆已有参数", expanded=False):
        selected = st.selectbox("来源 Run", runs,
                                format_func=_run_label, key="clone_source")
        if st.button("复制为可编辑草稿", key="clone_button"):
            metadata = selected.get("metadata") or {}
            strategy_id = metadata.get("strategy_id")
            version = metadata.get("strategy_version")
            reference = f"{strategy_id}@{version}"
            if reference not in registrations:
                st.error("该 Run 的策略版本当前未安装，无法复制参数。")
                return
            draft = _plain(metadata.get("config") or {})
            st.session_state.setdefault("draft_configs", {})[reference] = draft
            for key in list(st.session_state):
                if key.startswith(f"param__{reference}__"):
                    del st.session_state[key]
            st.session_state.pop(f"config_yaml_{reference}", None)
            chosen = list(st.session_state.get("strategy_selection", []))
            if reference not in chosen:
                chosen.append(reference)
                st.session_state["strategy_selection"] = chosen
            st.rerun()


def _sidebar(manager: Any) -> None:
    st.sidebar.header("策略与运行")
    upload = st.sidebar.file_uploader("导入策略 ZIP", type=["zip"], key="plugin_zip")
    if upload is not None and st.sidebar.button("验证并导入", key="import_button"):
        try:
            with TemporaryDirectory(prefix="stock-radar-ui-import-") as directory:
                path = Path(directory) / "strategy.zip"
                path.write_bytes(upload.getvalue())
                registration = manager.import_zip(path)
            st.sidebar.success(f"已导入：{registration.manifest.name} {registration.manifest.version}")
            st.rerun()
        except Exception as exc:
            st.sidebar.error(f"导入失败：{exc}")
            with st.sidebar.expander("技术详情"):
                st.exception(exc)

    registrations = {
        f"{item.manifest.id}@{item.manifest.version}": item
        for item in manager.list_strategies()
    }
    if not registrations:
        st.sidebar.info("尚无策略。请先导入策略 ZIP。")
        return
    _clone_controls(manager, registrations)
    selected = st.sidebar.multiselect(
        "选择一个或多个策略", list(registrations),
        format_func=lambda reference: f"{registrations[reference].manifest.name} · {reference}",
        key="strategy_selection",
    )
    split = st.sidebar.selectbox("回测时段", ["train", "validation", "test"],
                                 index=1, format_func=lambda item: {
                                     "train": "训练期", "validation": "验证期", "test": "历史测试期"
                                 }[item], key="run_split")
    st.sidebar.caption("历史测试期已被先前研究查看；这里的结果只作探索。")
    fee_profile = yaml.safe_load((ROOT / "config" / "research.yaml").read_text(encoding="utf-8"))
    st.sidebar.caption(f"费用配置：{fee_profile.get('illustrative_costs', {}).get('profile', '—')}")
    slippage = st.sidebar.number_input("滑点（基点，单边）", min_value=0.0,
                                       max_value=100.0, value=10.0, step=1.0,
                                       key="run_slippage")

    for reference in selected:
        registration = registrations[reference]
        with st.sidebar.expander(f"{registration.manifest.name} 参数", expanded=False):
            st.caption(registration.manifest.description)
            st.caption("修改阈值会生成新 Run，历史结果不会覆盖。")
            drafts = st.session_state.setdefault("draft_configs", {})
            if reference not in drafts:
                drafts[reference] = _plain(registration.config)
            config = drafts[reference]
            advanced = st.checkbox("高级 YAML 编辑", value=_contains_complex(config),
                                   key=f"advanced_{reference}")
            if advanced:
                key = f"config_yaml_{reference}"
                if key not in st.session_state:
                    st.session_state[key] = yaml.safe_dump(
                        config, allow_unicode=True, sort_keys=False)
                st.text_area("完整策略配置", key=key, height=260)
            else:
                drafts[reference] = _config_controls(config, reference)

    if st.sidebar.button("运行所选策略", type="primary", disabled=not selected,
                         key="start_runs"):
        try:
            configs: dict[str, dict] = {}
            for reference in selected:
                if st.session_state.get(f"advanced_{reference}"):
                    parsed = yaml.safe_load(st.session_state[f"config_yaml_{reference}"])
                else:
                    parsed = _plain(st.session_state["draft_configs"][reference])
                if not isinstance(parsed, dict):
                    raise ValueError(f"{reference} 的参数必须是 YAML 字典")
                configs[reference] = parsed
            run_ids = manager.queue_runs(selected, split=split,
                                         slippage_bps=float(slippage),
                                         configs_by_strategy=configs)
            manager.launch_queued()
            st.sidebar.success(f"已创建 {len(run_ids)} 个新 Run。")
            st.rerun()
        except Exception as exc:
            st.sidebar.error(f"无法启动回测：{exc}")
            with st.sidebar.expander("技术详情"):
                st.exception(exc)


@st.cache_resource(show_spinner=False)
def _manager(root: str) -> Any:
    from radar.lab.manager import RunManager
    return RunManager(Path(root))


def main() -> None:
    st.set_page_config(page_title="Stock Radar Strategy Lab", layout="wide",
                       initial_sidebar_state="expanded")
    from radar.ui.navigation import render as render_navigation
    from radar.ui.theme import apply_theme

    apply_theme()
    page = render_navigation()
    try:
        manager = _manager(str(ROOT))
    except Exception as exc:
        st.error(f"策略实验室尚未就绪：{exc}")
        with st.expander("技术详情"):
            st.exception(exc)
        return
    if page == "Lab":
        from radar.ui.pages.lab import render_lab

        render_lab(manager)
    elif page == "Strategies":
        from radar.ui.pages.strategies import render_strategies

        render_strategies(manager)
    elif page == "Experiments":
        from radar.ui.pages.experiments import render_experiments

        render_experiments(manager)
    elif page == "Compare":
        from radar.ui.pages.compare import render_compare

        render_compare(manager)
    elif page == "Data":
        from radar.ui.pages.data import render_data

        render_data(manager)
    elif page == "Settings":
        from radar.ui.pages.settings import render_settings

        render_settings(manager)


if __name__ == "__main__":
    main()
