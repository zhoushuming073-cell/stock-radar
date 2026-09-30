# 策略 2 七阶段与现有日线特征的对应

> Historical pre-v3 research artifact. Its split dates and name-based ETF/ETN filters are not the current Strategy Lab contract. See `config/research.yaml` and `docs/RESEARCH_PARAMETER_CONTRACT.md`. Numeric results below were not regenerated.

本表记录 `config/full_strategy2.yaml` / `src/radar/strategy/full_strategy2.py`
这一版**首次量化实现**。所有特征仅取信号日 `t` 收盘及之前的数据，买入在下一交易日
Open；`forward_labels` 只用于事后研究，不参与选股。

| 生命周期 | 使用的本地特征 | 当前硬条件与排序作用 |
|---|---|---|
| 先前强势 | `ret_60`, `drawdown_60` | 以 `(1+ret_60)/(1+drawdown_60)-1` 推断 60 日窗口起点至窗口高点的涨幅，至少 13.23%；分数随涨幅增加。它是历史峰值强度的代理，不等于完整趋势结构。 |
| 有意义回撤 | `drawdown_20`, `pullback_days_20` | 从 20 日高点回撤 8%–40%，高点至少早于今天 2 个交易日；排序偏好约 18% 的中等回撤。 |
| 跌势减弱 | `decline_speed_prev_3`, `decline_acceleration`, `red_body_avg_3/5`, `range_contraction` | 前 3 日仍在下跌、最近下跌速度改善；红实体及振幅收缩辅助排序。 |
| 支撑或吸收 | `failed_breakdown`, `support_reclaim`, `lower_wick_ratio`, `close_location`, `volume_contraction` | 至少有一个：假跌破、收回支撑、下影线加上较高收盘位置、或成交量收缩。各证据共同加分。 |
| 有效新低停止 | `new_low_frequency_5`, `higher_low_proxy` | 最近 5 日的有效破位频率不超过 20%；较高低点辅助排序。 |
| 早期转强 | `ret_1`, `body_pct`, `close_location`, `reclaim_ma_5` | 当日相对前收上涨、阳线且收在当日区间上半部；均线收回或较高低点辅助排序。 |
| 尚未过度反弹 | `rebound_from_low_5`, `ret_1`, `dist_ma_5` | 距 5 日低点反弹不超过 15%，当日涨幅不超过 10%，高于 MA5 不超过 15%；接近初始反弹者优先。 |

另外先通过 `tradability_pass`，Elasticity 分数至少 76.21（训练期前 20%）且
证券名称不明显标为 ETF/ETN；持仓标的不重复买入，每日最多 3 个新候选。
13.23% 的先前峰值涨幅来自训练期前 40% 分位。其余幅度阈值是把用户自然语言
转成可审计条件的初始设定，未证明为最优；实际券商费用也尚未确认。

## GitHub 参考

- [pinkfish 的 AC countertrend 示例](https://github.com/fja05680/pinkfish/blob/master/examples/strategies/ac-countertrend/strategy.py)（MIT）展示了“先有趋势，再等回撤”的可运行规则；源码和许可证已下载到本机 `data/references/pinkfish/`。该示例针对少量固定标的、同日收盘买入，不能直接替代本项目每天变化的股票池和次日 Open 成交约束，因此借鉴的是结构，没有复制其交易引擎或收益数字。
- [VCP 美股筛选器](https://github.com/carlamHS/vcp_screener)（CC0）提供趋势、振幅收缩和量能收缩研究的参考。它侧重高位整理，本版深回撤策略未直接复用其代码。
