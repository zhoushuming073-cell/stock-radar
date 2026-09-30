# Stock Radar 项目方向反思：雷达优先，回测交给成熟轮子

> **类型：个人研究思路 / 项目方向反思**
>
> 这不是 bug 日志、工程 backlog 或当前项目状态总账，而是对 Stock Radar 最终产品边界的一次重新确认。

## 1. 我真正想做的是什么

Stock Radar 的初心不是重新实现一个通用量化交易平台，也不是再造一套完整 Backtest Engine。

我真正想做的是：

> **把自己的主观选股逻辑转化成可以量化、可以历史重放、可以验证、可以每天扫描全市场的股票雷达。**

最终核心问题始终应该是：

> 在某一个真实历史时点，只使用当时能够获得的信息，Stock Radar 能不能从几千只股票里筛出少量真正值得继续研究的候选？

因此，Stock Radar 的核心产品应该是 **Candidate Retrieval Engine / Signal Generator**，而不是 Portfolio Backtester。

---

## 2. 项目职责重新划分

未来可以把系统明确拆成两层。

### Stock Radar 负责

- 数据与因果特征；
- 将主观形态语言转化为可计算特征；
- 全市场筛选；
- 横截面打分与排序；
- 产生 Top-K 候选；
- 保存每一个历史时点的候选快照；
- 验证候选是否具有统计上的富集能力；
- 输出标准化、可复现的 Signal Dataset。

### 成熟回测框架负责

- 买入时点；
- 卖出规则；
- 仓位分配；
- 资金约束；
- 同时持仓数量；
- 手续费；
- 滑点；
- 订单与成交模拟；
- Portfolio accounting；
- CAGR / Sharpe / Max Drawdown / Turnover 等组合绩效。

也就是说：

```text
Stock Radar
    ↓
历史时点的股票候选 / 信号
    ↓
标准 Signal Dataset
    ↓
成熟 Backtest Engine
    ↓
不同交易规则和组合规则下的实验结果
```

以后不再要求 Stock Radar 自己承担一个完整通用回测平台应该承担的职责。

---

## 3. 和普通量化研究方式的区别

常见研究方式是：

```text
研究策略规则 / 参数
    ↓
交给量化框架
    ↓
框架计算信号 + 模拟交易
    ↓
得到回测结果
```

我的方式可以不同：

```text
Strategy Idea
    ↓
Stock Radar
    ↓
直接产生历史股票信号
    ↓
成熟回测框架读取这些信号
    ↓
模拟不同执行 / 组合规则
```

这条路线是成立的。

关键不在于“策略是不是写在回测框架内部”，而在于：

1. 每个 signal 必须有明确的时间戳；
2. signal 只能使用当时已经存在的信息；
3. 历史候选必须可以重现；
4. 不能把未来标签、未来价格或当前快照信息泄漏进历史筛选；
5. 回测框架看到的只是已经冻结的历史信号，而不是未来信息。

因此，Stock Radar 可以被视为一个独立的 **signal-generation layer**。

---

## 4. 不应该只输出股票代码

真正用于研究和外部回测的数据不能只是：

```text
AAPL
XYZ
ABC
```

而应该至少保存：

```text
signal_timestamp
signal_date
ticker
rank
score
strategy_id
strategy_version
data_snapshot / data_version
feature values / diagnostics
```

例如：

```text
2026-01-05  ABC  rank=1  score=91.4
2026-01-05  XYZ  rank=2  score=87.2
2026-01-05  DEF  rank=3  score=83.6

2026-01-06  GHI  rank=1  score=94.1
2026-01-06  XYZ  rank=2  score=88.7
```

外部回测平台不需要理解 Strategy 2 的内部逻辑。

它只需要知道：

> 在这个历史时点，Stock Radar 当时产生了哪些股票信号。

---

## 5. 两类验证必须彻底分开

以后必须区分两个问题。

### A. Radar 是否会找股票？

这是 Stock Radar 自己必须回答的问题。

核心指标包括：

- Precision@5 / Precision@10 / Precision@20；
- Lift@K；
- 固定周期内 +3% / +5% / +8% / +10% target-hit rate；
- MFE；
- MAE；
- time-to-target；
- falling-knife / post-signal new-low rate；
- 不同年份、牛熊状态、波动率环境下的稳定性；
- Fresh OOS 表现；
- 概率校准。

这类验证不能因为未来移除完整 Backtest 功能而删除。

它是 Radar 自己的质量检验。

### B. Radar 信号能否组成赚钱的交易系统？

这是成熟 Backtest Engine 更适合回答的问题。

需要测试：

- 次日开盘买还是其他执行方式；
- Top 5 / Top 10 / Top 20；
- 等权还是 Score weighting；
- 固定持有期；
- 止盈止损；
- 最大同时持仓；
- 手续费和滑点；
- 资金利用率；
- Portfolio drawdown；
- Sharpe；
- CAGR；
- Turnover。

一个 Radar 可以有较高的 Lift，但因为错误的执行和组合规则而回测很差。

反过来，一个 Portfolio 回测赚钱，也不能单独证明 Radar 本身具有真正的候选识别能力。

所以：

> **Candidate Quality 和 Portfolio Profitability 是两个不同研究问题。**

---

## 6. 对当前自研 Backtest 功能的处理

当前仓库中的 Backtest 功能不需要马上删除。

更合理的做法是逐步：

1. 冻结；
2. 不再继续扩展通用交易平台能力；
3. 不再把工程精力投入订单、组合、调度、通用实验平台等成熟轮子已经解决的问题；
4. 保留当前功能作为历史研究兼容层或辅助验证工具；
5. 当 Scanner 已完全独立后，再决定是否迁入 legacy 或彻底移除。

应该保留并加强的是：

- Scanner Research；
- historical replay；
- forward outcome evaluator；
- causal feature pipeline；
- Signal Export；
- Precision / Lift / MFE / MAE；
- Fresh OOS；
- provenance / reproducibility。

也就是说：

> 可以退休 Portfolio Backtester，但不能退休 Radar Evaluator。

---

## 7. 最终架构

最终希望形成这样的边界：

```text
Market Data
    ↓
Causal Feature Engine
    ↓
Strategy / Pattern Hypothesis
    ↓
STOCK RADAR
Filter → Score → Rank → Top-K
    ↓
Historical Signal Dataset
    ├──────────────→ Radar Research Evaluator
    │                 Precision / Lift
    │                 MFE / MAE
    │                 Calibration
    │                 Regime
    │                 Fresh OOS
    │
    └──────────────→ Mature Backtest Engine
                      Entry / Exit
                      Position Sizing
                      Costs / Slippage
                      Portfolio
                      CAGR / Sharpe / DD
```

实际每日使用路径则是：

```text
Latest Market Data
    ↓
Daily Stock Radar
    ↓
Top 5 / 10 / 20 Candidates
    ↓
GPT / 人工二次研究
新闻 · 财报 · 催化剂 · 盘前 · 行业 · 风险
    ↓
最终交易判断
```

---

## 8. 以后判断一个功能值不值得做

以后新增功能前，优先问：

> **这个功能能不能提高“从全市场找出真正值得研究的少量股票”的能力，或者提高这种能力的可验证性？**

如果不能，只是让 Stock Radar 更像一个“完整量化平台”，则默认低优先级。

高优先级应该是：

- Latest-session Daily Scanner；
- 更好的 Pattern Features；
- 人工标注形态数据；
- Precision / Lift 研究；
- target-hit probability；
- probability calibration；
- Fresh OOS；
- regime conditioning；
- Quant / Vision / Fusion；
- 标准 Signal Export；
- GPT 二阶段研究接口。

低优先级应该是：

- 自研更复杂的 Portfolio Backtester；
- 自研交易撮合；
- 自研完整订单系统；
- 为了平台完整性继续扩展 Experiment Manager；
- 与“找股票”没有直接关系的基础设施雕琢。

---

## 9. 一句话重新定义 Stock Radar

> **Stock Radar 不是一个量化交易平台。它是一个把个人选股逻辑转化为可验证历史信号，并从全市场持续检索高质量候选股票的个人研究雷达。**

进一步说：

> **Stock Radar 负责回答“买什么值得研究”，成熟回测框架负责回答“这些信号怎样交易以及组合后表现如何”。**

这是后续项目演进应长期保持的边界。
