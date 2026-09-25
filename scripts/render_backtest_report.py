"""Render a self-contained local equity report; no market data is uploaded."""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "research"
TEST_DIR = SOURCE / "final-test-v1"


def main() -> None:
    summary = json.loads((TEST_DIR / "backtest_summary.json").read_text(encoding="utf-8"))
    test = summary["test"]
    curves = {
        "训练期": pd.read_csv(SOURCE / "backtest-v1" / "train_baseline_equity.csv", parse_dates=["date"]),
        "验证期": pd.read_csv(SOURCE / "backtest-v1" / "validation_baseline_equity.csv", parse_dates=["date"]),
        "最终测试期": pd.read_csv(TEST_DIR / "backtest_daily_equity.csv", parse_dates=["date"]),
    }
    comparison = go.Figure()
    palette = {"训练期": "#9a3412", "验证期": "#047857", "最终测试期": "#2563eb"}
    for name, curve in curves.items():
        comparison.add_trace(go.Scatter(
            x=list(range(len(curve))), y=(curve.equity / 1_000_000 - 1) * 100,
            mode="lines", name=name, line=dict(color=palette[name], width=2.5),
            customdata=curve.date.dt.strftime("%Y-%m-%d"),
            hovertemplate="%{customdata}<br>累计收益 %{y:.1f}%<extra>%{fullData.name}</extra>"))
    comparison.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
    comparison.update_layout(template="plotly_white", height=420,
                             margin=dict(l=45, r=20, t=35, b=45),
                             xaxis_title="各阶段交易日序号", yaxis_title="累计收益率 (%)",
                             legend=dict(orientation="h", y=1.14))
    final = curves["最终测试期"].copy()
    drawdown = final.equity / final.equity.cummax().clip(lower=1_000_000) - 1
    detail = make_subplots(rows=2, cols=1, shared_xaxes=True,
                           vertical_spacing=.10, row_heights=[.7, .3])
    detail.add_trace(go.Scatter(x=final.date, y=final.equity, mode="lines",
                                name="组合净值", line=dict(color="#2563eb", width=2.5)), row=1, col=1)
    detail.add_trace(go.Scatter(x=final.date, y=drawdown * 100, mode="lines",
                                name="回撤", fill="tozeroy",
                                line=dict(color="#dc2626", width=1.5)), row=2, col=1)
    detail.update_layout(template="plotly_white", height=570,
                         margin=dict(l=45, r=20, t=35, b=45), showlegend=False)
    detail.update_yaxes(title_text="美元", row=1, col=1)
    detail.update_yaxes(title_text="回撤 (%)", row=2, col=1)
    monthly = final.set_index("date").equity.resample("ME").last()
    monthly_return = monthly.pct_change()
    if len(monthly_return):
        monthly_return.iloc[0] = monthly.iloc[0] / 1_000_000 - 1
    month_chart = go.Figure(go.Bar(
        x=monthly_return.index.strftime("%Y-%m"), y=monthly_return * 100,
        marker_color=["#047857" if value >= 0 else "#dc2626" for value in monthly_return]))
    month_chart.update_layout(template="plotly_white", height=300,
                              margin=dict(l=45, r=20, t=35, b=45),
                              xaxis_title="月份", yaxis_title="月收益率 (%)")
    fmt_pct = lambda value: f"{value * 100:+.2f}%"
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Stock Radar 策略 2 回测报告</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font-family:system-ui,'Microsoft YaHei',sans-serif;background:#f5f7fb;color:#172033;margin:0}}
main{{max-width:1160px;margin:32px auto;padding:0 22px 50px}}h1{{font-size:30px;margin-bottom:8px}}
.sub{{color:#64748b;line-height:1.65}}.alert{{background:#fef2f2;border:1px solid #fecaca;padding:16px 20px;border-radius:12px;color:#991b1b;font-weight:650}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:20px 0}}
.card,.panel{{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:18px;box-shadow:0 2px 8px #e2e8f044}}
.card small{{display:block;color:#64748b;margin-bottom:8px}}.card strong{{font-size:27px}}
.negative{{color:#b91c1c}}.positive{{color:#047857}}.panel{{margin:18px 0}}h2{{margin:0 0 8px;font-size:19px}}
table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;border-bottom:1px solid #e2e8f0;padding:10px}}th{{color:#475569}}
a{{color:#1d4ed8}}.notes{{line-height:1.7;color:#475569}}</style></head><body><main>
<h1>Stock Radar · 策略 2 回测</h1>
<p class="sub">最终测试期：2025-09-19 至 2026-09-24 · 初始资金 $1,000,000 · 每侧 10 bps 滑点 · 示例费率方案</p>
<div class="alert">结论：该策略未通过训练期与验证期的稳定性检查；最终测试期亏损。当前决策为 CASH，不建议实盘部署。</div>
<div class="cards">
<div class="card"><small>最终测试期净收益</small><strong class="negative">{fmt_pct(test['total_return'])}</strong></div>
<div class="card"><small>期末资金</small><strong>${test['final_equity']:,.0f}</strong></div>
<div class="card"><small>最大回撤</small><strong class="negative">{fmt_pct(test['max_drawdown'])}</strong></div>
<div class="card"><small>交易笔数</small><strong>{test['trade_count']}</strong></div>
</div>
<div class="panel"><h2>三个独立阶段的累计收益</h2>{comparison.to_html(full_html=False, include_plotlyjs=True)}</div>
<div class="panel"><h2>最终测试期净值与回撤</h2>{detail.to_html(full_html=False, include_plotlyjs=False)}</div>
<div class="panel"><h2>最终测试期每月收益</h2>{month_chart.to_html(full_html=False, include_plotlyjs=False)}</div>
<div class="panel"><h2>关键指标</h2><table><tr><th>指标</th><th>结果</th></tr>
<tr><td>年化收益率 CAGR</td><td>{fmt_pct(test['cagr'])}</td></tr>
<tr><td>年化波动率</td><td>{test['annual_volatility'] * 100:.2f}%</td></tr>
<tr><td>夏普比率（无风险利率按 0）</td><td>{test['sharpe']:.2f}</td></tr>
<tr><td>胜率</td><td>{test['win_rate'] * 100:.1f}%</td></tr>
<tr><td>盈利因子</td><td>{test['profit_factor']:.2f}</td></tr>
<tr><td>平均资金使用率</td><td>{test['avg_position_utilization'] * 100:.1f}%</td></tr>
<tr><td>交易毛损益</td><td>${test['gross_pnl']:,.0f}</td></tr>
<tr><td>买卖费用</td><td>${test['fees']:,.0f}</td></tr>
<tr><td>滑点成本</td><td>${test['slippage_cost']:,.0f}</td></tr>
<tr><td>净损益</td><td>${test['net_pnl']:,.0f}</td></tr></table></div>
<div class="panel notes"><h2>如何解读</h2><p>训练期 -81.14%，验证期 +4.49%，最终测试期 {fmt_pct(test['total_return'])}。
三个阶段各自从 $1,000,000 开始，曲线不连续复利。同期 SPY 收盘至收盘涨幅 {fmt_pct(summary['spy_close_to_close_return_before_costs'])}（未计成本），现金基准 0%。
胜率高于 50% 仍亏损，因为亏损单和跳空损失大于盈利单收益，加上频繁交易成本。</p>
<p>历史标的池来自当前存续证券，存在幸存者偏差；仅用名称过滤显式 ETF/ETN，仍可能混入其他基金；费率尚未按你的实际账户确认；固定滑点未覆盖市场冲击。该报告是研究诊断，不是投资建议。</p>
<p><a href="backtest_trades.csv">交易流水 CSV</a> · <a href="backtest_daily_equity.csv">每日净值 CSV</a> · <a href="backtest_summary.json">完整摘要 JSON</a> · <a href="verification.json">独立核对结果</a></p></div>
</main></body></html>"""
    target = TEST_DIR / "回测报告.html"
    target.write_text(html, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
