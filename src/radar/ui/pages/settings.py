"""Read the active research configuration without changing execution defaults."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml


ROOT = Path(__file__).resolve().parents[4]
SECTIONS = ("Backtest", "Data Sources", "Fees & Slippage", "System",
            "Appearance", "Advanced")


def _load(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _field(label: str, value, key: str) -> None:
    st.text_input(label, value="—" if value is None else str(value),
                  disabled=True, key=f"settings_{key}")


def render_settings(manager=None) -> None:
    st.title("Settings")
    st.caption("当前生效的回测、数据源与本机设置。页面不会改写已运行策略的规则。")
    backtest = _load(ROOT / "config" / "backtest.yaml")
    research = _load(ROOT / "config" / "research.yaml")
    menu, body = st.columns([1, 4], gap="small")
    with menu:
        selected = st.radio("设置分类", SECTIONS, label_visibility="collapsed",
                            key="settings_section")
    with body:
        if selected == "Backtest":
            st.markdown("**Backtest**")
            fields = (
                ("初始资金", backtest.get("initial_capital"), "capital"),
                ("每天最多新开标的", backtest.get("max_new_candidates"), "max_new"),
                ("止盈", backtest.get("take_profit"), "take_profit"),
                ("止损", backtest.get("stop_loss"), "stop_loss"),
                ("最多持有交易日", backtest.get("max_holding_sessions"), "max_hold"),
                ("单标的仓位上限", backtest.get("max_position_fraction"), "max_position"),
                ("默认滑点（基点）", backtest.get("base_slippage_bps"), "slippage"),
            )
            for left, right in zip(fields[::2], fields[1::2]):
                a, b = st.columns(2)
                with a:
                    _field(*left)
                with b:
                    _field(*right)
            if len(fields) % 2:
                _field(*fields[-1])
            st.caption("训练、验证和历史测试区间由研究配置及实际交易日计算。")
        elif selected == "Data Sources":
            st.markdown("**Data Sources**")
            _field("行情提供方", "Alpaca", "provider")
            _field("本机行情数据库", ROOT / "data" / "market.duckdb", "market_db")
            _field("本机研究数据库", ROOT / "data" / "phase2-research.duckdb", "research_db")
            st.caption("页面不会显示或上传 Alpaca 密钥。")
        elif selected == "Fees & Slippage":
            st.markdown("**Fees & Slippage**")
            costs = research.get("illustrative_costs") or {}
            _field("费用配置", costs.get("profile"), "fee_profile")
            _field("默认滑点（基点，单边）", backtest.get("base_slippage_bps"), "fee_slippage")
            _field("手续费（每股）", costs.get("commission_per_share"), "commission")
            _field("平台费（每股）", costs.get("platform_per_share"), "platform")
            st.caption("费用配置为研究估算，实际交易费用可能不同。")
        elif selected == "System":
            st.markdown("**System**")
            _field("策略实验室位置", ROOT, "root")
            _field("最大并行运行数", getattr(manager, "max_workers", None), "workers")
            _field("本地结果库", ROOT / "data" / "strategy-lab" / "runs.sqlite3", "runs_db")
            st.caption("行情与运行记录均保存在这台电脑。")
        elif selected == "Appearance":
            st.markdown("**Appearance**")
            _field("主题", "浅色 · Stock Radar", "theme")
            st.caption("当前界面按照已确认的 Strategy Lab 原型呈现。")
        else:
            st.markdown("**Advanced**")
            if not backtest and not research:
                st.info("尚未找到项目配置文件。")
            else:
                with st.expander("回测配置", expanded=False):
                    st.code(yaml.safe_dump(backtest, allow_unicode=True,
                                           sort_keys=False), language="yaml")
                with st.expander("研究配置", expanded=False):
                    st.code(yaml.safe_dump(research, allow_unicode=True,
                                           sort_keys=False), language="yaml")
        st.caption("当前页面显示生效配置。修改默认执行规则需经过独立验证。")
