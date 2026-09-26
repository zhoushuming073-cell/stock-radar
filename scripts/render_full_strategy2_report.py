"""Render a self-contained, local-only full Strategy 2 research report."""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "research" / "full-strategy2-v1"
CAPITAL = 1_000_000
NAMES = {"train": "训练", "validation": "验证", "test": "旧历史 Test（探索性）"}
COLORS = {"train": "#b45309", "validation": "#047857", "test": "#2563eb"}


def main() -> None:
    required = [OUTPUT / "scenario_summary.csv", OUTPUT / "verification.json"]
    required += [OUTPUT / f"{split}_equity.csv" for split in NAMES]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing backtest outputs: " + ", ".join(missing))
    scenarios = pd.read_csv(OUTPUT / "scenario_summary.csv")
    curves = {split: pd.read_csv(OUTPUT / f"{split}_equity.csv", parse_dates=["date"])
              for split in NAMES}
    base = scenarios.loc[scenarios.slippage_bps_per_side.eq(10)].set_index("split")
    if set(base.index) != set(NAMES):
        raise ValueError("expected one 10 bps summary for every split")
    test = base.loc["test"]

    compare = go.Figure()
    for split, curve in curves.items():
        compare.add_trace(go.Scatter(
            x=curve.date, y=(curve.equity / CAPITAL - 1) * 100,
            mode="lines", name=NAMES[split], line=dict(color=COLORS[split], width=2.4),
            hovertemplate="%{x|%Y-%m-%d}<br>累计收益 %{y:.2f}%<extra>%{fullData.name}</extra>"))
    compare.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
    compare.update_layout(template="plotly_white", height=430,
                          margin=dict(l=50, r=25, t=30, b=45),
                          xaxis_title="日期（各阶段资金重新从 $1,000,000 开始）",
                          yaxis_title="累计收益率 (%)")

    final = curves["test"]
    drawdown = final.equity / pd.concat(
        [pd.Series([CAPITAL]), final.equity], ignore_index=True
    ).cummax().iloc[1:].to_numpy() - 1
    detail = make_subplots(rows=2, cols=1, shared_xaxes=True,
                           vertical_spacing=.08, row_heights=[.68, .32])
    detail.add_trace(go.Scatter(
        x=final.date, y=final.equity, mode="lines", name="净值",
        line=dict(color="#2563eb", width=2.4)), row=1, col=1)
    detail.add_trace(go.Scatter(
        x=final.date, y=drawdown * 100, mode="lines", name="回撤",
        fill="tozeroy", line=dict(color="#dc2626", width=1.5)), row=2, col=1)
    detail.update_layout(template="plotly_white", height=550,
                         margin=dict(l=50, r=25, t=30, b=45), showlegend=False)
    detail.update_yaxes(title_text="美元", row=1, col=1)
    detail.update_yaxes(title_text="回撤 (%)", row=2, col=1)

    table_rows = []
    for bps in (0, 5, 10, 20):
        row = [f"{bps} bps"]
        for split in NAMES:
            item = scenarios.loc[scenarios.split.eq(split) &
                                 scenarios.slippage_bps_per_side.eq(bps)]
            if len(item) != 1:
                raise ValueError(f"missing or duplicate {split}/{bps} bps scenario")
            value = float(item.iloc[0].total_return)
            class_name = "positive" if value >= 0 else "negative"
            row.append(f'<td class="{class_name}">{value:+.2%}</td>')
        table_rows.append("<tr><th>" + escape(row[0]) + "</th>" + "".join(row[1:]) + "</tr>")

    test_return = float(test.total_return)
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Stock Radar · 策略 2 完整条件回测</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{margin:0;background:#f5f7fb;color:#172033;font-family:system-ui,'Microsoft YaHei',sans-serif}}
main{{max-width:1160px;margin:30px auto;padding:0 20px 45px}}h1{{font-size:29px;margin-bottom:8px}}
p{{line-height:1.65}}.muted{{color:#64748b}}.notice{{background:#fff7ed;border:1px solid #fdba74;
padding:16px 20px;border-radius:12px;color:#9a3412}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,
minmax(190px,1fr));gap:12px;margin:18px 0}}.card,.panel{{background:white;border:1px solid #e2e8f0;
border-radius:14px;padding:18px;box-shadow:0 2px 8px #e2e8f044}}.card small{{display:block;color:#64748b}}
.card strong{{font-size:27px}}.panel{{margin:17px 0}}h2{{font-size:19px;margin:0 0 8px}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #e2e8f0}}
.positive{{color:#047857}}.negative{{color:#b91c1c}}a{{color:#1d4ed8}}</style></head><body><main>
<h1>Stock Radar · 策略 2 完整条件回测</h1>
<p class="muted">本地历史数据 · 各阶段初始资金 $1,000,000 · 示例费率 · 基准每侧滑点 10 bps</p>
<div class="notice"><strong>研究结论：</strong>训练期为负；旧历史 Test 虽为正，但该区间在上一轮
简化基线研究中已被查看。这是探索性复核，不能称为全新样本外验证或可靠交易优势。</div>
<div class="cards"><div class="card"><small>训练期</small><strong class="negative">{float(base.loc['train','total_return']):+.2%}</strong></div>
<div class="card"><small>验证期</small><strong class="positive">{float(base.loc['validation','total_return']):+.2%}</strong></div>
<div class="card"><small>旧历史 Test</small><strong class="{'positive' if test_return >= 0 else 'negative'}">{test_return:+.2%}</strong></div>
<div class="card"><small>旧历史 Test 最大回撤</small><strong class="negative">{float(test.max_drawdown):.2%}</strong></div></div>
<div class="panel"><h2>各阶段累计收益</h2>{compare.to_html(full_html=False,include_plotlyjs=True)}</div>
<div class="panel"><h2>旧历史 Test 净值与回撤</h2>{detail.to_html(full_html=False,include_plotlyjs=False)}</div>
<div class="panel"><h2>滑点敏感性</h2><table><tr><th>每侧滑点</th><th>训练</th><th>验证</th><th>旧历史 Test</th></tr>
{''.join(table_rows)}</table></div>
<div class="panel"><h2>旧历史 Test 账目</h2><table>
<tr><td>期末资金</td><td>${float(test.final_equity):,.2f}</td></tr>
<tr><td>平仓交易</td><td>{int(test.trade_count)} 笔</td></tr>
<tr><td>胜率 / 盈利因子</td><td>{float(test.win_rate):.2%} / {float(test.profit_factor):.2f}</td></tr>
<tr><td>毛损益</td><td>${float(test.gross_pnl):,.2f}</td></tr>
<tr><td>买卖费用</td><td>${float(test.fees):,.2f}</td></tr>
<tr><td>滑点成本</td><td>${float(test.slippage_cost):,.2f}</td></tr>
<tr><td>净损益</td><td>${float(test.net_pnl):,.2f}</td></tr></table></div>
<div class="panel"><h2>使用限制</h2><p>证券池来自当前存续名单，可能有幸存者偏差；
名称过滤 ETF/ETN 不完整；示例券商费用尚未核对实际账户；固定滑点不能充分代表市场冲击。
规则需在新的、未查看过的数据上验证。</p>
<p><a href="test_trades.csv">交易流水</a> · <a href="test_equity.csv">每日净值</a> ·
<a href="scenario_summary.csv">全部情景</a> · <a href="verification.json">逐笔核验</a></p></div>
</main></body></html>"""
    target = OUTPUT / "策略2完整条件回测.html"
    target.write_text(html, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
