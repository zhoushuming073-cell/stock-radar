# Stock Radar Journey

> 项目研究日志。记录关键设计判断、已确认限制、未修问题和下一步研究方向。  
> 最初审计基线：`main @ aee467c3a510d5421fab6fda9bc30f9124eb28dc`
> 更新日期：2026-09-29

---

## 2026-09-28 — 插件宿主边界与未修研究正确性问题

### 当前结论

Stock Radar 当前的插件接口已经足够支持复杂的**当日横截面候选策略**，但还不是通用交易策略框架。

现有插件最适合：

```text
信号日 t 的因果特征
→ hard_filter
→ score
→ rank
→ select
→ Scanner / Backtest
```

它可以支持多因子阈值、非线性评分、横截面排名、候选子集选择、诊断分项和概率输出。

但插件本身不能：

- 任意读取历史 K 线；
- 直接查询 DuckDB / Alpaca / 文件 / 网络；
- 访问未来标签或未来行情；
- 自己训练滚动模型；
- 保存跨日内部状态；
- 读取现金、持仓、组合回撤等 portfolio state；
- 自定义仓位分配；
- 自定义成交机制；
- 自定义复杂退出；
- 扩大宿主已经给出的股票池；
- 直接使用 ES / NQ / YM，因为宿主目前尚未开放这些 causal features。

这是当前架构的核心原则：

```text
Host 保证数据边界和因果性
→ Plugin 只消费已经审核过的 causal features
```

不应通过简单开放数据库权限来扩大插件能力，否则会破坏未来准备建立的严格 As-Of 防偷看体系。

---

## 插件参数自由度

### 已经比较自由的部分

插件的 `strategy.yaml` 可以定义任意嵌套策略参数，例如：

```yaml
momentum:
  lookback: 60
  min_return: 0.20

weights:
  elasticity: 0.35
  reversal: 0.25
  market: 0.20

selection:
  max_candidates: 20
```

插件代码通过只读 `Mapping[str, Any]` 使用这些参数。

已有参数的数值可以在新 Run 中修改，并进入 resolved config、source map 和 research hash。

### 目前的限制

Run override 只能修改插件默认配置中**已经存在的 leaf**。

不能在某次 Run 中临时发明新的参数路径。

例如插件默认不存在：

```text
weights.futures
```

那么 Run 不能临时新增它。

如果策略需要新参数，应更新插件配置和版本，而不是让单次 Run 改变参数结构。

### UI 限制

当前漂亮的 Core / Advanced 参数 UI 基本只为：

```text
full_strategy2_v1
```

显式声明。

第三方 v1 插件后端可以拥有复杂参数，但 UI 没有通用 parameter schema，只能退化成配置 JSON 编辑。

后续较合理的扩展方向是让插件声明自己的参数 schema：

```text
path
label
description
type
min
max
step
nullable
core / advanced
searchable
```

---

## 插件数据边界

`StrategyContext` 当前只暴露：

```text
context.signal_date
context.frame
```

其中 frame 是信号日 t 的股票横截面，包含：

- symbol
- security_name
- close
- 插件在 manifest / required_features 中声明的 causal features

原始：

```text
open
high
low
volume
vwap
trade_count
```

不会直接开放给插件。

插件也不能访问 forward labels、entry Open、MFE、MAE、future return、数据库连接、券商客户端等。

因此，当前插件可以做：

```text
复杂横截面打分
固定 Logistic 推理
因子组合
regime-conditioned selection
```

但不能自己做：

```text
每天重新训练 Logistic / LightGBM
直接读取过去 N 根 K 线
维护 rolling model state
portfolio-aware rotation
intraday / limit-order / multi-leg logic
```

如果未来加入每日滚动 ML，更合理的设计是：

```text
Plugin 声明模型需求
→ Host 严格按 As-Of 训练
→ Host 输出当天 prediction
→ Plugin 使用 prediction
```

而不是允许插件直接读取完整历史数据集。

---

## Scanner / Execution 的当前硬边界

### Scanner

当前宿主支持：

- entry reference：仅 `next_session_open`
- horizon：1–60 sessions
- success rule：
  - `target_touch`
  - `target_before_adverse`
- Top-K：1–1000
- cooldown：0–60 sessions
- primary target 必须属于 upside targets
- primary adverse target 必须属于 downside targets

插件不能自己定义新的 forward outcome 语义。

### Backtest

插件的候选产生与执行层是分开的。

宿主拥有：

- initial capital
- 每日最多新开仓数量
- gap gate
- position sizing
- ADV participation
- slippage
- fees
- market guard
- take profit
- stop loss
- max holding sessions
- execution timing

当前 allocator 只有：

```text
equal_cash
strategy_score
strategy_times_elasticity
```

插件不能直接指定：

```text
AAA 50%
BBB 30%
CCC 20%
```

也不能自定义 trailing stop、ATR stop、MA exit、portfolio drawdown guard、盘中触发逻辑等。

当前核心定位仍然是：

> candidate strategy plugin，而不是 general execution plugin。

---

## 一个容易忽略的 select / rank 语义

插件的 `select()` 可以决定保留哪些候选。

但是 Scanner 的正式 `rank` 会由宿主重新按：

```text
strategy_score descending
symbol ascending
```

计算。

因此：

> 插件可以决定“选谁”，但正式排名必须通过 `score()` 表达。

如果插件认为 AAA 应该排在 BBB 前面，就必须满足：

```text
score(AAA) > score(BBB)
```

不能只依赖 `select()` 返回顺序。

---

# 未修研究正确性问题

下面这些问题与真正 PIT 历史 Security Master 不完全相同。

PIT 数据采购 / 历史 universe 还原暂时不作为当前重点。

---

## 1. 当前历史研究仍存在 future-conditioned universe selection

已经确认存在：

```text
用数据集末端最近约 35 日成交额
→ 决定哪些股票进入整段历史研究
```

这意味着：

```text
未来/样本末端流动性
→ 影响过去日期是否有资格被研究
```

这属于明确的未来条件选择。

即使暂时接受“当前存活股票 cohort”带来的幸存者偏差，也不应该继续叠加：

```text
future liquidity selection bias
```

### 计划解决方式

改为严格历史日 t 的 eligible universe：

```text
当前可用 cohort
→ 截断到 t
→ 用 t 当时的历史长度 / price / ADV20 / bar availability
→ 得到 U_t
```

---

## 2. 当前 tradable / exchange 状态可能被回灌到整段历史

历史 feature pipeline 当前仍可能使用今天的 asset snapshot：

```text
tradable
exchange
```

去影响过去日期的 `tradability_pass`。

这属于 current-state backfill。

### 计划解决方式

在非 PIT 模式下，历史日 `tradability_pass(t)` 尽量只依赖历史行情可验证条件：

```text
price(t)
ADV20(t)
history length(t)
bar available(t)
```

当前 snapshot 只用于定义“我们正在研究的 survivor cohort”，不继续作为过去每一天的状态变量。

---

## 3. Elasticity 横截面 percentile 会继承 universe 污染

`groupby(date).rank(pct=True)` 本身不是 future leak。

问题是参与排名的股票集合如果已经被未来筛选，就会产生：

```text
survivor-normalized percentile
```

### 正确顺序

```text
U_t
→ 每只股票的 Raw Elasticity(t)
→ 只在 U_t 内做当天 percentile rank
```

而不是先在未来筛出来的全历史 cohort 上计算 percentile。

---

## 4. Market Breadth 会继承同样的 universe 污染

正确的 breadth 应为：

```text
Breadth_t =
站上 MA20 的 U_t 成员数
/
当天 U_t 总数
```

因此必须先构造当天的因果 universe，再计算 breadth。

不能用今天的 survivor sample 预先生成整条历史 breadth。

---

# 统一解决方案：Strict As-Of Daily Causal Replay

当前最重要的研究正确性改造不是继续加零散补丁，而是建立统一规则：

> 历史日期 t 运行时，系统只能看到 t 当天收盘及以前的信息。

记信息集为：

```text
F_t
```

当天输出必须满足：

```text
Candidate_t = f(F_t)
```

而不能是：

```text
Candidate_t = f(F_T), T > t
```

每天重建：

```text
U_t
stock features(t)
Elasticity(t)
cross-sectional percentile(t)
Market Breadth(t)
SPY / QQQ context(t)
未来 ES / NQ / YM context(t)
```

只有最后的 Host-owned evaluation layer 可以读取 t 之后的数据生成 forward labels。

---

## Strict Replay 与快速引擎

未来建议保留两个实现：

### Strict Causal Replay

最慢、最直接、用于作为正确性基准。

对于日期 t：

```text
物理截断所有数据到 t
→ 从头计算当天 universe / feature / score / rank
```

### Fast Vectorized Engine

用于正式大规模实验。

但必须定期随机抽历史日期验证：

```text
Feature_fast(t) == Feature_strict(t)
Score_fast(t)   == Score_strict(t)
Rank_fast(t)    == Rank_strict(t)
```

如果不同，Fast engine 存在潜在因果性问题。

运行速度本身不是研究正确性的证据。

UI 中的最短播放时间可以保留，但不能用“算得慢/快”判断是否偷看未来。

---

# Future Mutation Test

建议把下面这个不变量升级成长期 contract test。

选历史日期 t，第一次正常计算：

```text
U_t
X_t
Score_t
Rank_t
```

然后任意修改 t 之后：

```text
股票价格
成交量
SPY / QQQ
未来 ES / NQ / YM
future asset metadata
corporate actions
```

再次计算 t。

必须满足：

```text
U'_t     = U_t
X'_t     = X_t
Score'_t = Score_t
Rank'_t  = Rank_t
```

即：

```text
F(D_<=t, D_>t) = F(D_<=t, modified(D_>t))
```

这是未来新增因子时最重要的防偷看保险丝。

---

# 未来 ML 额外约束：Label Maturity

仅仅“训练时不能看 t 之后行情”还不够。

如果 forward label 的 horizon 是 10 sessions，那么靠近训练日的最近信号，其标签在训练日仍未成熟。

未来滚动训练需要满足：

```text
label_available_at <= training_as_of
```

也就是只有已经完整发生过 outcome window 的历史样本才能进入训练。

同样，任何需要 fit 的对象：

```text
scaler
imputer
winsorization threshold
PCA
feature selection
calibration
hyperparameter selection
```

都只能使用当时可用历史。

---

# 更棘手、不能靠每日重算自动解决的问题

## A. 旧 Test 已被查看

之前的 Test slice 已经被研究者看过。

因此它不能继续充当最终 untouched OOS。

即使程序实现 100% 因果：

```text
看 Test
→ 改策略
→ 再跑同一个 Test
```

仍属于 researcher-level data leakage。

未来需要：

```text
Train
→ Validation
→ Freeze
→ Fresh untouched OOS
```

Fresh OOS 可以直接等待未来真实行情自然产生，不一定需要购买数据。

---

## B. 多重实验 / researcher degrees of freedom

即使全部实验都没有时间泄漏：

```text
测试大量参数组合
→ 只挑最好的一组
```

也会因为随机噪声得到“看起来很强”的策略。

因此应长期记录：

```text
Experiment ID
改了什么
为什么改
预期方向
Train 结果
Validation 结果
是否保留
```

不要只保存最终最好看的结果。

---

## C. Historical data vintage / revision

今天重新下载的历史数据，不一定等于当年实时可见的数据版本。

可能受到：

```text
split adjustment
ticker mapping
corporate-action back adjustment
provider correction
future continuous-futures roll adjustment
```

影响。

严格表示：

```text
D_2023^(2026 vintage)
可能不等于
D_2023^(2023 vintage)
```

个人项目当前不准备保存每个日期的数据 vintage，因此暂时把它列为已知残余限制。

特别需要谨慎的，是绝对价格门槛、未来加入的连续期货序列和 provider 自动 ticker 映射。

---

# PIT 暂缓

当前 `current_snapshot` 模式仍然存在经典幸存者偏差：

```text
过去已经退市 / 消失 / 破产的股票
可能不在今天的研究 cohort
```

这件事目前接受为已知限制。

未来可能研究两条路线：

1. 购买可信的 PIT Security Master / terminal event data；
2. 用历史交易记录、交易所/SEC资料、ticker changes、IPO/delisting/corporate actions 等做逆向历史还原。

逆向工程不是当前优先事项，也不能因为“还原出名单”就自动宣称得到完整 PIT 数据。

---

# ES / NQ / YM 的计划边界

未来准备给宿主增加三大美股股指期货的因果上下文：

```text
ES
NQ
YM
```

原则仍然是：

```text
Raw futures data
→ Host causal feature builder
→ as_of timestamp gate
→ causal futures features
→ StrategyContext
```

不允许插件自己直接查询期货数据库。

需要特别防：

- continuous contract back-adjustment leakage；
- roll rule look-ahead；
- 同一自然日但晚于 signal timestamp 的期货数据泄漏。

以后信号时点应明确到 timestamp，而不只是 date。

---

# 当前建议优先级

1. **实现 Strict As-Of Daily Causal Replay**
2. **清掉末端 35D 流动性选历史股票的问题**
3. **去掉 current tradable / exchange 对历史日状态的回灌**
4. **让 Elasticity percentile / Breadth 严格基于 U_t**
5. **加入 Future Mutation Test**
6. **建立 Strict Replay vs Fast Engine 对照测试**
7. **再接 ES / NQ / YM Host-owned causal features**
8. **未来 ML 时强制 label maturity**
9. **用实验日志控制 parameter snooping / Test contamination**
10. **PIT 与历史 universe 逆向恢复后续单独处理**

---

## 当前研究状态

```text
探索性 Train / Validation Scanner：
可继续

正式无偏 PIT 历史验证：
仍不可宣称完成

当前下一阶段重点：
程序级因果回放与未来信息隔离
```

---

## 2026-09-29 — As-Of 因果重放落地与真实数据验收

已完成上面优先级 1–6 的程序与数据层改动：

- `strict_asof_day` 只读取信号日 `t` 及以前的股票、SPY、QQQ 行情，并独立重算当日特征、可交易状态、Elasticity、市场宽度及策略排名。
- 历史研究 cohort 不再由样本末端 35 个交易日的成交额筛选；当前 `active US_EQUITY` 幸存者集合中的每只股票，只要有历史 K 线就参与构建。
- 历史可交易门槛仅取当日价格、截至当日的 ADV20 和已观察交易日数；当前资产快照的 `tradable`、`exchange` 不再回灌到历史日。
- Elasticity 分位数和市场宽度按当日合格集合 `U_t` 计算。旧版 `phase2a_f_v2` 与新版 `phase2a_f_v3_asof` 保持版本隔离，Compare 会提示版本差异。
- 自动化测试会改变 `t` 之后的股票、SPY、QQQ 行情及当前可变交易元数据，确认 `t` 的候选、分数和排名不变；同时逐字段对照慢速严格重放与批量引擎。

真实数据源来自 Alpaca SIP、split adjustment，覆盖 2021-09-01 至 2026-09-28：12,151,417 条日 K 线，OHLCV 无空值或非法价格/成交量。57 条成交量为正的记录缺 VWAP，已保留为质量提示；本次特征计算不依赖 VWAP。全量研究库包含 13,562 只当前幸存者股票、12,148,871 条 v3 特征、5,838,633 条已评分特征。

三个真实交易日的严格重放与批量结果逐字段一致，且成员集合、可交易状态、Elasticity 排名和市场宽度一致：

| 日期 | 区段 | 当日有数据 | 合格 | 已排名 |
| --- | --- | ---: | ---: | ---: |
| 2024-05-14 | Train | 9,235 | 4,670 | 4,670 |
| 2025-01-03 | Validation | 9,948 | 5,417 | 5,417 |
| 2026-05-18 | Test 计算一致性抽检 | 12,315 | 6,144 | 6,143 |

Test 抽检只核对特征计算，没有查看策略收益或用于调参。完整 pytest：230 项通过。旧 v2 研究库冻结在本机 `data/phase2-research-v2-frozen.duckdb`，v3 成为默认研究库。

**仍未解决的研究限制：**当前资产快照仍有幸存者偏差，供应商历史行情可能经事后修订，旧 Test 结果已被研究者看过；因此不能宣称获得了正式无偏 PIT 回测。每日自动更新 `market.duckdb`，研究库更新仍是独立、带版本记录的回填与构建流程，不会自动并入每日行情。ES/NQ/YM 因果特征、ML label maturity、实验日志防多重试验和可信 PIT Security Master 均保留为后续工作。
