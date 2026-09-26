"""Local market coverage and update status, using the existing DuckDB store."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[4]
DB = ROOT / "data" / "market.duckdb"
VALIDATION = ROOT / "data" / "validation-summary.json"
UPDATE_STATUS = ROOT / "data" / "daily-update-status.json"


@st.cache_data(ttl=60, show_spinner=False)
def _coverage(db_path: str, stamp: int) -> tuple[dict, pd.DataFrame]:
    with duckdb.connect(db_path, read_only=True) as conn:
        count, symbols, latest = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT symbol), MAX(date) FROM daily_bars"
        ).fetchone()
        tradable = conn.execute(
            "SELECT COUNT(*) FROM assets WHERE status='active' AND tradable"
        ).fetchone()[0]
        by_exchange = conn.execute("""
            SELECT a.exchange AS exchange, COUNT(*) AS total,
                   COUNT(b.symbol) AS daily,
                   MAX(b.last_date) AS last_update
            FROM assets a
            LEFT JOIN (SELECT symbol, MAX(date) AS last_date FROM daily_bars GROUP BY symbol) b
              ON a.symbol=b.symbol
            WHERE a.status='active' AND a.tradable
            GROUP BY a.exchange ORDER BY total DESC
        """).df()
    return {"bars": count, "symbols": symbols, "tradable": tradable,
            "latest": str(latest) if latest else None}, by_exchange


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def render_data(manager=None) -> None:
    st.title("Data")
    st.caption("行情覆盖、同步状态和研究数据质量；数据只保存在本机。")
    actions = st.columns([1, 1, 5])
    with actions[0]:
        if st.button("刷新", key="data_refresh", width="stretch"):
            _coverage.clear()
            st.rerun()
    with actions[1]:
        if st.button("从 Alpaca 同步", key="data_sync", width="stretch"):
            try:
                if __import__("os").name != "nt":
                    raise RuntimeError("本机后台任务仅配置在 Windows 上")
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Start-ScheduledTask -TaskName 'StockRadar-DailyUpdate'"],
                    capture_output=True, text=True, timeout=15, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or "无法启动后台同步任务")
                st.success("已启动本机后台同步。完成后点击刷新查看结果。")
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                st.error(f"同步未启动：{exc}")
    if not DB.is_file():
        st.info("本机尚无行情数据库。先完成数据同步后即可查看覆盖情况。")
        return
    try:
        summary, coverage = _coverage(str(DB), DB.stat().st_mtime_ns)
    except (OSError, duckdb.Error) as exc:
        st.error(f"无法读取本机行情数据库：{exc}")
        return
    status = _read_json(UPDATE_STATUS)
    values = st.columns(4)
    values[0].metric("Daily Bars", f"{summary['bars']:,}")
    values[1].metric("Intraday Bars", "暂无")
    values[2].metric("Tradable Symbols", f"{summary['tradable']:,}")
    values[3].metric("Last Sync", status.get("target_date") or summary["latest"] or "暂无")
    coverage_tab, quality_tab, sync_tab, classes_tab = st.tabs(
        ["Coverage", "Data Quality", "Alpaca Sync", "Security Classification"]
    )
    with coverage_tab:
        if coverage.empty:
            st.info("暂无可用股票覆盖数据。")
        else:
            shown = coverage.rename(columns={"exchange": "交易所", "total": "标的数",
                                             "daily": "已有日线", "last_update": "最近更新"})
            shown["最近更新"] = shown["最近更新"].map(
                lambda value: str(value)[:10] if pd.notna(value) else "—"
            )
            shown["日线覆盖"] = 100 * shown["已有日线"].div(
                shown["标的数"].replace(0, pd.NA))
            st.dataframe(shown, hide_index=True, width="stretch",
                         column_config={"日线覆盖": st.column_config.ProgressColumn(
                             "日线覆盖", min_value=0, max_value=100, format="%.1f%%")})
            st.caption(f"有日线的不同代码：{summary['symbols']:,}。日内数据尚未接入。")
    with quality_tab:
        report = _read_json(VALIDATION)
        issues = report.get("issues") if isinstance(report.get("issues"), list) else []
        if not report:
            st.info("暂无校验报告。数据同步后运行校验即可查看。")
        else:
            errors = sum(item.get("severity") == "error" for item in issues)
            warnings = sum(item.get("severity") == "warning" for item in issues)
            a, b = st.columns(2)
            a.metric("错误", errors)
            b.metric("研究警告", warnings)
            if issues:
                st.dataframe(pd.DataFrame(issues), hide_index=True, width="stretch")
            else:
                st.success("当前报告没有问题记录。")
    with sync_tab:
        if not status:
            st.info("暂无后台同步记录。")
        else:
            state = status.get("state", "未知")
            st.success("最近同步已完成。") if state == "succeeded" else st.warning(f"最近同步状态：{state}")
            st.write("目标交易日：", status.get("target_date") or "—")
            st.write("结束时间：", status.get("finished_at") or "—")
            if status.get("error"):
                st.caption(f"原因：{status['error']}")
    with classes_tab:
        st.info("详细证券分类尚未接入；当前页按交易所展示覆盖情况。")
