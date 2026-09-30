# 从主观形态识别到因果横截面筛选：Stock Radar 的研究设计与首轮路径感知验证

**From Discretionary Pattern Recognition to Causal Cross-Sectional Screening: Research Design and First Path-Aware Validation of Stock Radar**

> Research paper draft · 2026-09-27\
> Archived under `reports/personal-research/`; this is a historical research draft.

## 摘要

本文提出并评估一个面向美股横截面候选发现的本地量化研究系统 Stock Radar。其研究对象不是传统意义上的“完整交易策略收益最大化”，而是一个更基础、也更容易被严格检验的问题：能否将“前期强势、经历显著回撤、下跌动能衰竭、出现支撑或承接、开始初步转强、但尚未明显延伸”这一主观价格形态，转换为因果、可复现、可审计的候选生成过程，并验证候选是否相对于可交易股票背景集合富集了更有利的后续价格路径。

本文使用上传的 `runs.sqlite3` 研究快照，对 `full_strategy2_v1` 在 Validation 区间 2024-09-27 至 2025-09-04 的 Scanner 结果进行分析。主评价规则以信号日收盘后生成候选、下一交易日开盘价作为参考价格，在未来 10 个交易日内考察“先上涨 +5%，还是先下跌 -5%”。该路径感知标签比单纯的“未来是否曾触及 +5%”更严格，因为它显式纳入达到收益目标前的逆向价格路径。Validation 期间共有 234 个交易日进入筛选漏斗，其中 220 个交易日产生至少一个候选；共形成 1,990 个候选观察，覆盖 432 个不同证券。在 5 个交易日事件冷却规则下，这些观察被归并为 1,542 个相对独立的信号事件。

结果显示，当前硬筛选结构具有明显的候选富集能力，而现有连续评分排序的增量信息有限。记录的背景路径成功率为 34.27%；完整 Strategy 2 候选中，1,967 个具有可判定主标签的观察里有 49.52% 实现“+5% 先于 -5%”，对应条件 Lift 约 1.445。Top-5、Top-10、Top-20 的 pooled precision 分别为 50.11%、49.74% 和 49.86%；在 5 日事件冷却后，event-level precision 分别为 51.42%、51.13% 和 50.59%，对应 event Lift 为 1.500、1.492 和 1.476。按信号日聚类重采样得到的描述性 95% 区间显示，event Precision@5 约为 46.76%–56.15%，在把背景率视为当前样本固定基准时，对应 Lift 区间约为 1.36–1.64。

然而，Strategy 2 当前的 `strategy_score` 对主路径标签的区分能力接近随机：全部候选观察的 ROC-AUC 为 0.498，事件样本 ROC-AUC 为 0.506。Top-5 事件精度相对完整硬筛选候选仅高约 1.9 个百分点；按信号日聚类的描述性重采样区间包含 0。这意味着目前主要的统计增益来自“是否通过硬筛选”，而不是“通过后谁被打更高分”。此外，候选的 10 日平均 MFE 为 +11.87%，平均 MAE 为 -10.21%；False Falling-Knife Rate 达 48.94%，表明该模式虽然处于高波动、高后续运动空间区域，但风险路径仍然显著。单纯使用 target-touch 会得到更乐观的表面结果：同一候选群体的 +5% 触及率为 67.74%，而主路径成功率仅约 49.52%，说明忽略不利路径会明显高估信号质量。

本文不把上述结果解释为可交易 alpha 的正式证据。当前实验使用 `current_snapshot` universe，运行元数据明确标记 `survivorship_bias_risk = present`；此外，运行对应的 Git 基准版本为 `f1d992ff...`，但 `git_dirty = true`，说明本地研究代码存在未提交修改。因此，这组结果应被视为 Research Alpha 阶段的 Validation 证据：它支持继续研究硬筛选形态是否具有稳定的横截面富集能力，同时明确否定“当前排序分数已经足够有效”以及“当前历史结果已经无偏、可直接外推”的表述。下一步应优先完成真实 point-in-time universe、干净代码快照下的复现、全新未查看样本期验证、Human Ground Truth，以及 Quant、Vision 与 Fusion 三条研究路线的统一对照。

**关键词：** 横截面选股；价格形态；候选检索；Point-in-Time Universe；Precision@K；Lift@K；路径依赖标签；幸存者偏差；视觉金融；可复现研究

---

## 1. 引言

大量实际交易决策并不是从一个完整的资产定价模型开始，而是从一种模式识别语言开始。交易者可能描述某只股票为“前期涨得很强，随后出现较深回撤，现在跌不动了，低位有人承接，开始有一点转强，但尚未明显追高”。这类语言对人类而言直观，却难以直接进行历史验证，因为其中包含多个模糊概念：什么叫“前期强势”？什么程度的回撤才算“充分”？如何区分真正的下跌衰竭与暂时停顿？“承接”能否仅从日线数据中近似表示？何时可以说“开始转强”而不是简单反弹？

Stock Radar 的核心目标，是把这类主观图形语言变成一个可以被机器重复执行、被统计指标检验、被版本系统追踪、被未来数据严格隔离的候选发现框架。其定位不是自动实盘交易系统，也不是以历史 CAGR 或 Sharpe Ratio 为唯一目标的组合优化器，而是整个研究链条的第一层：

```text
全市场股票池
    ↓
因果、可解释的价格特征
    ↓
硬筛选 + 评分排序
    ↓
少量候选股票
    ↓
未来路径标签与候选质量评价
    ↓
GPT 新闻 / 催化剂 / 基本面 / 盘前背景研究
    ↓
可选的分钟级确认
```

这一定位具有两个方法论含义。第一，Scanner 的质量应首先由“候选是否比背景集合更富集目标后续路径”来评估，而不是直接由模拟组合的最终净值决定。第二，候选系统必须能够区分“模式检索质量”和“交易执行质量”：前者回答“筛出来的股票是否值得进一步研究”，后者才回答“若使用特定买卖规则、仓位、费用、滑点和资金约束，组合会发生什么”。

这种分离使得 Stock Radar 可以在较早阶段回答一个更窄、更可证伪的问题：**主观形态是否包含可复现的横截面信息？** 如果答案是否定的，那么继续优化仓位、止盈止损甚至机器学习模型都缺乏基础；如果答案为正，则可以进一步研究该信息能否被更好的排序、概率模型、视觉模型和第二阶段语境信息放大。

---

## 2. 研究对象与可证伪假设

### 2.1 Strategy 2 的行为语言

当前 `full_strategy2_v1` 将目标形态拆分为七类核心概念：

1. **Prior Strength**：候选在回撤前曾表现出较强的趋势或阶段性涨幅；
2. **Pullback Quality**：价格已从近期高点产生具有研究意义的回撤，而非仅有极浅波动；
3. **Downside Exhaustion**：近期下跌速度、实体或连续性出现减弱迹象；
4. **Support / Absorption**：价格在低位出现近似支撑、收盘位置改善、下影线或量价收缩等可观察特征；
5. **New-Low Stop**：继续创新低的频率下降；
6. **Early Reversal**：出现初步转强或短期趋势恢复迹象；
7. **Not Extended**：候选尚未在信号发生前重新快速拉升，避免把已经大幅反弹的股票误判为早期机会。

Strategy 2 并不声称这些变量天然等同于真实买盘、机构吸筹或基本面改善。它们只是对“看起来开始跌不动并可能进入转折阶段”这一主观概念的日线代理变量。因而本研究的重点不是证明每个变量具有某种经济因果机制，而是验证其组合是否能够稳定提高目标未来路径的条件概率。

### 2.2 主要研究假设

本文将当前研究问题形式化为四个可证伪假设：

**H1：硬筛选富集假设。** 通过 Strategy 2 全部硬条件的股票，其目标未来路径成功率应高于同期 eligible universe 的背景成功率。

**H2：排序增量假设。** 在已经通过硬筛选的候选中，较高 `strategy_score` 应进一步提高目标路径成功概率，因此 Top-K 的 Precision 应随排名改善，且连续分数应具有高于随机的判别能力。

**H3：重复信号稳健性假设。** 候选优势不应主要来自同一证券连续多日重复出现；在事件冷却后，Precision 与 Lift 应保持相近。

**H4：路径风险约束假设。** 单纯的未来 target-touch 会高估候选质量；加入 adverse barrier 后，评价应更接近实际可交易风险结构。

这些假设中，H1–H4 均可以被现有 Validation 结果直接检验，而“能否获得稳定可交易超额收益”并不是本文要回答的问题。

---

## 3. 系统设计：因果性、配置治理与可复现性

### 3.1 Scanner 与 Host 的职责分离

Stock Radar 的策略插件只负责根据时点 *t* 及其之前可获得的数据提出候选。未来标签、未来行情、账户状态、成交模型、费用、滑点和组合资金约束均由 Host 侧管理。这样的结构把策略定义与研究基础设施分离，降低插件通过未来数据或执行细节无意“作弊”的风险。

对于 Scanner，信号在交易日 *t* 收盘后形成，主评价参考价设为下一交易日开盘价。由此，信号生成与未来评价之间存在明确的时间边界。该设计不能保证所有数据源本身都是完美 point-in-time，但它为特征层和标签层建立了清晰的因果接口。

### 3.2 Canonical Run Configuration

当前运行配置被分为五个命名空间：

- `strategy.*`：定义候选逻辑和参数；
- `evaluation.*`：定义未来标签、目标、时域、Top-K 和事件冷却等；
- `execution.*`：定义可选回测中的成交与退出假设；
- `dataset.*`：定义 split、日期、数据快照、特征版本和 universe 模式；
- `view.*`：仅影响显示，不进入研究哈希。

每个运行生成 `ResolvedRunConfig`，记录最终值、来源和哈希。这种设计的核心意义不是“配置更漂亮”，而是让研究问题具备可审计性：同一个结果必须能够回答“当时到底用了哪个阈值、哪一个标签版本、哪一种 universe 和哪一份数据快照”。

### 3.3 运行快照与当前复现状态

本文主分析运行的 Git 基准 revision 为：

```text
f1d992ff24f0da3cf1c0f0036369c98ba725846d
```

但运行元数据记录：

```text
git_dirty = true
```

这意味着运行时工作区包含尚未提交的代码变化。虽然系统同时保存了 Host 关键源文件的 SHA-256 哈希和数据快照哈希，这仍然不是最理想的正式论文级复现状态。后续正式实验应要求：

```text
clean git tree
+ frozen strategy version
+ frozen resolved config
+ frozen data snapshot
+ frozen PIT universe fingerprint
```

只有这样，实验结果才能被视为具有完整的软件版本可追溯性。

---

## 4. 数据与评价设计

### 4.1 样本区间与 Universe

本文使用 `runs.sqlite3` 中的 Validation Scanner 运行：

```text
Run ID: 50fb0556-ddd4-4332-985d-f6f905c28746
Strategy: full_strategy2_v1@1.0.0
Split: validation
Signal period: 2024-09-27 — 2025-09-04
Evaluation end: 2025-09-18
Feature version: phase2a_f_v2
Label version: scanner-forward-v2
Market feature version: causal-market-v1
Universe mode: current_snapshot
Survivorship bias risk: present
```

当前 universe 并非真实历史 point-in-time security master。虽然项目已经建立 PIT Provider、stable `security_id`、dated symbol mapping、listing/delisting interval 与 fingerprint 等接口，但本次结果仍使用 `current_snapshot`。因此，已经退市、破产、被并购或在当前快照中缺失的证券可能未被正确纳入历史横截面。经典研究表明，幸存者截断本身可以制造或放大看似存在的可预测性，因此该问题不是次要实现细节，而是正式历史推断的核心有效性威胁。

### 4.2 候选规模

Validation 区间共有 234 个交易日进入 Filter Funnel，其中 14 日没有最终候选，220 日至少产生一个候选。总计：

| 统计量 | 数值 |
|---|---:|
| Candidate observations | 1,990 |
| Unique symbols | 432 |
| Signal dates with candidates | 220 |
| Mean candidates per candidate-day | 9.05 |
| Median candidates per candidate-day | 6 |
| Maximum candidates in one day | 45 |
| Unique signal events, 5-session cooldown | 1,542 |
| Unique signal events, 3-session cooldown | 1,637 |

重复候选并非由极少数股票完全主导：出现次数最多的单一证券为 15 次，Top-10 最常出现证券合计约占全部候选观察的 7.0%。尽管如此，序列相关性仍然存在，因此本文同时报告 observation-level 与 event-level 指标。

### 4.3 路径感知主标签

设下一交易日开盘价为参考价 \(P_0\)。在随后 \(H=10\) 个交易日内，定义上涨阈值 \(+u\) 和下跌阈值 \(-d\)。记：

\[
\tau_+(u)=\min\{h\in[1,H]: P_h/P_0-1\ge u\},
\]

\[
\tau_-(d)=\min\{h\in[1,H]: P_h/P_0-1\le -d\}.
\]

本文主标签取 \(u=d=5\%\)，成功事件定义为：

\[
Y=1\quad \text{iff}\quad \tau_+(5\%) < \tau_-(5\%).
\]

若日线数据无法确定同一交易日内两个阈值谁先发生，则相关路径标签可以被标记为不可判定，而不是人为假设最有利或最不利的盘中顺序。

这一标签与传统 target-touch 的差别十分重要。target-touch 只回答“未来十天内是否曾经达到 +5%”，而 target-before-adverse 回答“在先承受 -5% 之前，是否先达到 +5%”。后者更接近候选排序所关心的实际路径质量。

### 4.4 Precision 与 Lift

对每个交易日的候选按 `strategy_score` 排名。对给定 \(K\)，定义 pooled Precision@K：

\[
\mathrm{Precision@K}=
\frac{\sum_{t,i}Y_{t,i}\mathbf{1}(rank_{t,i}\le K)}
{\sum_{t,i}\mathbf{1}(rank_{t,i}\le K)}.
\]

定义同期 eligible universe 上相同标签的背景率为 \(p_0\)。则：

\[
\mathrm{Lift@K}=\frac{\mathrm{Precision@K}}{p_0}.
\]

Lift 的含义是“候选成功率相对背景成功率提升了多少倍”，它比单独报告高低不明的命中率更适合跨市场阶段比较。

### 4.5 MFE、MAE 与 False Falling Knife

最大有利波动 MFE 与最大不利波动 MAE 分别刻画信号后的最大上行空间与最大逆向运动：

\[
\mathrm{MFE}_H=\max_{1\le h\le H}(P_h/P_0-1),
\]

\[
\mathrm{MAE}_H=\min_{1\le h\le H}(P_h/P_0-1).
\]

False Falling-Knife 用于识别“看似止跌但随后仍出现深度下探”的候选。当前阈值设为未来窗口内最大回撤不超过 -8% 才不被视为该类失败。

---

## 5. Filter Funnel：候选稀释发生在哪里

Strategy 2 的漏斗不是一次性黑箱评分，而是逐层缩小横截面。234 个 Validation 交易日的平均日度数量如下：

| 阶段 | 平均日度数量 | 相对前一主要阶段保留率 |
|---|---:|---:|
| Eligible universe | 1,908.9 | — |
| Tradable / feature complete | 1,857.7 | 97.3% |
| Elasticity | 363.5 | 19.6% |
| Prior strength | 271.6 | 74.7% |
| Pullback | 151.5 | 55.8% |
| Downside exhaustion | 62.7 | 41.4% |
| Support / absorption | 36.0 | 57.4% |
| New-low stop | 25.7 | 71.6% |
| Early reversal | 11.3 | 44.0% |
| Not extended | 9.44 | 83.3% |
| Explicit fund filter / final ranked | 8.50 | 90.1% |

从 446,674 个日度 eligible-security observations 到 1,990 个最终候选，整体保留率约为 0.446%。因此当前系统本质上是一个高度稀疏的候选检索器，而非覆盖大部分股票的连续预测器。

从漏斗强度看，最显著的收缩发生在 Elasticity、Pullback、Downside Exhaustion 和 Early Reversal。这个结构提供了两个未来研究方向。其一，应检验这些硬门槛是否真正贡献增量信息，而不是仅仅减少样本；其二，如果硬门槛已经承担大部分预测能力，那么后续连续评分应该专注于候选内部的二次排序，而不应简单重复同一组筛选逻辑。

---

## 6. 实证结果

### 6.1 硬筛选候选相对背景集合存在明显富集

主运行记录的背景路径成功率为：

\[
p_0 = 34.27\%.
\]

1,990 个 Strategy 2 候选观察中，1,967 个具有可判定的主路径标签，其中 974 个成功，因此：

\[
P(Y=1\mid \text{Strategy2 candidate}) = 49.52\%.
\]

相对记录的背景率，对应：

\[
\mathrm{Lift}\approx 1.445.
\]

按信号日聚类重采样得到的候选成功率描述性 95% 区间约为 45.05%–54.15%。该区间并非严格的时间序列多重检验校正置信区间，但它表明当前候选富集并非仅由个别日期的极端结果决定。

因此，在当前 Validation/current-snapshot 条件下，H1 得到初步支持：**通过完整硬筛选的候选群体确实比背景集合更集中于目标路径。** 但该结论目前只能描述当前样本，不能直接推广为无偏历史 alpha 证据。

### 6.2 Top-K 排序几乎没有进一步提高 pooled precision

主运行的 Top-K 结果如下：

| 指标 | K=5 | K=10 | K=20 |
|---|---:|---:|---:|
| Pooled Precision | 50.11% | 49.74% | 49.86% |
| Pooled Lift | 1.462 | 1.451 | 1.455 |
| Event Precision, cooldown=5 | 51.42% | 51.13% | 50.59% |
| Event Lift, cooldown=5 | 1.500 | 1.492 | 1.476 |
| Event sample size | 669 | 1,021 | 1,348 |

Top-5 event precision 的按信号日聚类重采样 95% 区间约为 46.76%–56.15%；在把当前背景率视为固定基准的条件下，对应 Lift 区间约为 1.36–1.64。

真正值得注意的不是 Precision@5 大约 51%，而是 **K 从 20 缩小到 5 并没有产生明显、单调的质量提升**。这意味着当前排名并未明显把“最好的候选”推到顶部。

进一步地，`strategy_score` 对主标签的 ROC-AUC 为：

```text
All candidate observations: 0.498
Event-only observations:    0.506
```

这与随机排序几乎无异。按全样本 score decile 划分，成功率也没有呈现稳定单调关系；最高 score decile 的路径成功率甚至低于若干中间分位。Top-5 事件精度相对完整硬筛选候选成功率仅高约 1.9 个百分点，按信号日聚类的描述性重采样区间约为 -1.9 至 +5.7 个百分点，包含 0。

因此，H2 在当前版本下**没有得到支持**。当前证据更符合如下解释：

> Strategy 2 的主要信息增量来自“硬条件是否全部通过”，而不是当前加权分数在候选内部的精细排序。

这不是系统失败，而是一个具有明确工程含义的研究结果：下一阶段不应优先继续微调硬筛选阈值以追求更漂亮的 Validation 结果，而应研究一个真正具有增量排序能力的二阶模型，例如简单 Logistic Regression、单调约束模型或后续 LightGBM，并要求其在冻结候选集合上证明对 path-aware label 的独立判别力。

### 6.3 Target-touch 会显著高估表面成功率

同一批 1,990 个候选的 10 日 target-touch 统计为：

| 未来 10 日目标 | 候选触及率 |
|---|---:|
| +3% | 78.94% |
| +5% | 67.74% |
| +8% | 51.01% |
| +10% | 41.41% |

如果只看“十日内是否触及 +5%”，Strategy 2 看起来有接近 68% 的命中率。然而，同一候选在考虑 -5% adverse barrier 后，主路径成功率降至约 49.52%。

两者差异不是统计口径上的小调整，而是研究问题本身发生了改变。一个候选完全可能先跌 -8%，随后反弹 +5%；target-touch 会把它记为成功，而路径感知标签会把它视为失败或至少不属于优质早期入场路径。

这支持 H4：**路径信息是 Scanner 评价不可省略的组成部分。** 对“回撤后止跌转强”类策略尤其如此，因为错误信号本身往往仍然具有高波动和高 MFE，只是到达有利空间前可能先经历不可接受的下行。

### 6.4 MFE 很高，但 MAE 同样高

候选在 10 日窗口中的运动幅度如下：

| 指标 | 平均值 | 中位数 |
|---|---:|---:|
| MFE | +11.87% | +8.15% |
| MAE | -10.21% | -7.97% |

False Falling-Knife Rate 为 48.94%。这意味着当前硬筛选确实集中在“未来会大幅运动”的区域，但它并没有天然解决方向质量问题。

进一步按主路径结果分组：

| 主路径结果 | 样本数 | 平均 MFE | 平均 MAE | False Falling-Knife |
|---|---:|---:|---:|---:|
| 成功 | 974 | +16.57% | -6.77% | 28.54% |
| 失败 | 993 | +7.11% | -13.45% | 68.38% |

成功与失败候选在 MAE 和 False Falling-Knife 上存在明显结构差异。这提示后续二阶模型不应只学习“谁未来能涨”，还应尝试直接预测 adverse path，例如：

```text
P(+5% before -5%)
P(false falling knife)
Expected MAE
Expected MFE
```

最终的候选优先级可以建立在多任务风险表征上，而不是单一综合分数。

### 6.5 事件冷却规则的结果较稳定

为减少同一证券连续信号带来的伪样本膨胀，系统将相近信号合并为事件。主运行使用 5 个交易日冷却，另一个 Scanner grid run 将冷却改为 3 个交易日：

| 指标 | 5-session cooldown | 3-session cooldown |
|---|---:|---:|
| Unique signal events | 1,542 | 1,637 |
| Event Precision@5 | 51.42% | 51.47% |
| Event Precision@10 | 51.13% | 50.92% |
| Event Precision@20 | 50.59% | 50.52% |
| Event Lift@5 | 1.500 | 1.502 |
| Event Lift@10 | 1.492 | 1.486 |
| Event Lift@20 | 1.476 | 1.474 |

冷却从 5 日缩短到 3 日使事件数增加约 6.2%，但 Precision/Lift 几乎不变。这为 H3 提供了初步支持：当前候选富集并不是简单由某些股票连续数日重复进入候选池造成的。

当然，这仍不等同于严格的独立样本，因为不同股票可能受同一市场冲击、行业主题或宏观事件驱动。后续正式推断应考虑日期聚类、行业聚类或 block bootstrap，而不能把每个 candidate event 直接视为 iid Bernoulli 试验。

### 6.6 市场状态结果具有反直觉特征，但尚不足以推断 regime alpha

当前主运行按 SPY 相对 MA20 的状态报告：

| Regime | Labeled candidates | Primary success rate |
|---|---:|---:|
| SPY above MA20 | 1,440 | 47.22% |
| SPY below MA20 | 527 | 55.79% |

表面上看，Strategy 2 在较弱市场环境中反而有更高路径成功率。这可能符合“强势股回撤后反转”在市场调整期产生更多可交易反弹的直觉，也可能只是样本期结构、行业暴露、候选选择或 market-state 定义造成的结果。

因此本文不把该差异解释为稳定的 market-regime advantage。更严谨的下一步应在多个互不重叠时期重复估计，并同时控制波动率、市场 breadth 和行业集中度。当前 regime breakdown 更适合作为“发现待检验现象”的诊断，而不是一个可以直接加入策略的乘数。

---

## 7. 结果解释：系统真正证明了什么，尚未证明什么

当前 Validation 证据支持一个相对具体的结论：

> **Strategy 2 的硬筛选定义在当前样本中能够把大约 1,900 只日度 eligible securities 压缩到平均约 8.5 个候选，同时把“未来 10 日内 +5% 先于 -5%”的记录背景率从约 34% 提高到约 50%。**

但这一结论与“当前 Strategy 2 已经形成成熟预测模型”之间还有明显距离。

首先，硬筛选之后的 `strategy_score` 没有展示出有效的二次排序能力。换言之，系统目前更像一个 **pattern gate**，而不是一个 **well-calibrated ranker**。这实际上为后续模型路线提供了清楚方向：保持当前硬筛选作为解释性 baseline，然后训练独立的概率模型去估计：

\[
P(Y=1\mid X_t, \text{candidate}=1).
\]

其次，候选本身属于高波动集合。平均 MFE 与 MAE 同时很大，近一半候选仍满足 False Falling-Knife 定义。因此，提高 Scanner 质量的核心不应是进一步放大“能动起来”的特征，而是更有效地区分“向上扩张前先守住风险阈值”与“继续向下破位”两类路径。

第三，当前所有结论都来自 Validation/current-snapshot 研究快照。它们可以用于设计下一轮实验，但不应该被转化为对真实未来收益的确定性陈述。

---

## 8. 内部有效性与外部有效性威胁

### 8.1 幸存者偏差

这是当前最重要的数据层限制。本次 universe 明确标记为 `current_snapshot`。经典研究表明，若样本因存续状态被截断，观察到的收益或可预测关系可能被系统性扭曲。Stock Radar 已经实现 PIT universe 的软件边界，但真实 historical security master 与退市证券完整历史行情尚未成为本次实验的数据基础。

因此，本报告所有历史结果都必须附带：

```text
Survivorship Bias Risk: Present
```

在真实 PIT 数据接入前，本文不使用“survivorship-bias-free”“unbiased historical validation”等表述。

### 8.2 Data snooping 与 Test 污染

金融时间序列只有一条真实历史。重复查看同一段数据并根据结果修改规则，会逐步把样本内偶然性编码进研究决策。White（2000）以及后续关于 backtest overfitting 的研究都强调了反复模型搜索对统计推断的破坏。

因此，Stock Radar 后续应采用严格研究纪律：

```text
Train → 特征与模型开发
Validation → 模型选择与参数冻结
Fresh OOS / untouched Test → 最终一次性验证
```

已经被查看、比较和用于设计决策的历史 Test 区间不应再次被称为“全新样本外证据”。

### 8.3 运行代码并非 clean commit

本次主运行记录 `git_dirty=true`。虽然保存了代码哈希，这种状态仍不适合作为最终论文的正式 reproducibility package。下一轮正式实验必须在 clean commit 上重新运行。

### 8.4 日线无法完全确定盘中路径

如果同一天 High 同时越过上涨目标、Low 同时越过下跌目标，日线 OHLC 无法知道谁先发生。当前系统对相关情况使用 ambiguity 逻辑，而不是默认最优成交顺序，这是较保守的处理；但真正解决该问题需要候选级分钟数据，而非继续从日线中推断不存在的信息。

### 8.5 多重研究自由度

Strategy 2 包含多个门槛、子分数和固定权重。即使每个单独实验都是因果的，大量参数尝试也会形成 specification search。未来参数实验必须记录完整 trial ledger，并区分：

- 事前假设；
- 探索性改动；
- Validation 上的模型选择；
- 冻结后 OOS 检验。

这比只保存“最后表现最好的一组参数”更重要。

---

## 9. 下一阶段方法路线

### 9.1 从规则排序转向校准概率

当前结果表明，硬筛选有信息，但 score 排序几乎没有增量。因此推荐的模型路线不是立即引入高度复杂的深度网络，而是：

```text
Rule-based gate
    ↓
Logistic Regression
    ↓
LightGBM
    ↓
Probability Calibration
```

Logistic Regression 可以作为最透明的二阶基线，验证子特征是否提供稳定、方向一致的条件信息；LightGBM 再测试非线性和交互项；最终输出应是经过校准的概率，而不是任意 0–100 分。概率校准在需要将模型分数用于风险决策时尤其重要，因为分类排序性能并不自动意味着概率具有正确的频率解释。

### 9.2 Human Ground Truth

当前机器标签回答的是“未来走势是否有利”，但还没有回答另一个关键问题：机器认为的“支撑、衰竭、初步转强”是否真的与人类看图时认定的目标形态一致。

因此，应构建不展示未来数据的人工快照集，对以下维度分别评分：

```text
Prior strength        0–3
Pullback quality      0–3
Downside exhaustion   0–3
Support / absorption  0–3
Early reversal        0–3
Overall pattern match 0–3
```

随后研究 Human Score 与 Quant Score 的关系。如果 Quant Score 连人工目标形态都无法稳定匹配，那么即使某个未来标签暂时有效，也可能说明模型在捕捉与原始交易语言不同的东西。

### 9.3 纯视觉路线与 Fusion

视觉研究应作为独立研究路线，而不是 Strategy 2 的装饰性附加模块。Jiang、Kelly 与 Xiu（2023）展示了将股票价格图直接作为图像输入、由机器学习提取预测性价格结构的研究范式。Stock Radar 可以在严格避免未来泄漏的前提下建立类似但更聚焦于“候选形态检索”的 Vision baseline。

建议统一生成：

```text
固定历史长度
固定图像尺寸
价格 K 线
成交量
统一缩放规则
不显示 ticker
不显示未来
不显示未来日期信息
```

随后比较四种对象：

```text
Quant-only
Vision-only
Quant ∩ Vision consensus
Quant + Vision Fusion
```

所有路线必须使用同一套 forward labels、同一 universe、同一 Train/Validation/Fresh-OOS 切分和同一 Precision/Lift/MFE/MAE 评价体系。这样才能回答真正有研究意义的问题：

1. Vision 是否学到了手工特征没有表达出来的价格结构？
2. Vision 与 Quant 的错误是否互补？
3. 两者共识是否提高路径质量而不仅仅减少候选数量？
4. Fusion 的增益在新时期是否仍然存在？

### 9.4 GPT Context Layer

GPT 应位于 Quant/Vision 候选生成之后，而不是参与历史价格标签构造。其作用可以是读取候选当时可获得的新闻、催化剂、财报、基本面和盘前信息，并验证第二阶段语境是否提供增量价值。理想实验应保存 point-in-time context log，以比较：

\[
\Delta \mathrm{Precision}
= \mathrm{Precision}_{\text{Quant+Context}}
- \mathrm{Precision}_{\text{Quant only}}.
\]

否则 GPT 的作用容易停留在事后解释层面，而难以被严格评价。

---

## 10. 结论

Stock Radar 当前最重要的研究进展，不是得到了一条漂亮的回测净值曲线，而是把一个原本模糊的主观选股语言转化为可逐层审计的候选系统，并开始用与候选发现任务本身匹配的指标进行评价。

首轮路径感知 Validation 结果提供了一个清晰而不应被过度包装的结论：**硬筛选有效地富集了目标路径，但当前连续评分尚未证明具有候选内部的增量排序能力。** 记录的背景路径成功率约为 34.27%，完整候选约为 49.52%，事件级 Top-K Precision 约为 50%–51%，对应 Lift 约为 1.48–1.50；与此同时，平均 MAE 超过 10%，False Falling-Knife 接近 49%，显示错误候选的下行风险仍然很高。Target-touch 与 path-aware label 之间的巨大差异进一步说明，仅凭“未来最终涨到过目标”会系统性美化这类反转候选。

从研究设计角度，这组结果具有积极意义，因为它把下一步问题缩小到了几个可以直接验证的方向：真实 PIT universe 是否保留同样的富集；独立二阶模型能否在硬筛选后产生真正的排序能力；Human Ground Truth 是否确认量化系统确实在寻找目标图形；Vision-only 是否捕捉到结构化因子遗漏的信息；以及这些改进能否在全新未查看时期保持稳定。

在完成这些工作之前，Stock Radar 应被定义为 **Experimental Candidate-Discovery Research System**，而不是已经验证的交易 alpha。对于一个希望长期积累可信研究证据的系统而言，这种克制不是缺点，而是方法论本身的一部分。

---

## 附录 A：主运行研究参数

```yaml
strategy: full_strategy2_v1@1.0.0
split: validation
signal_start: 2024-09-27
signal_end: 2025-09-04
evaluation_end: 2025-09-18
universe_mode: current_snapshot
survivorship_bias_risk: present
entry_reference: next_session_open
horizon_sessions: 10
primary_target: 0.05
success_rule: target_before_adverse
downside_targets: [-0.03, -0.05, -0.08, -0.10]
upside_targets: [0.03, 0.05, 0.08, 0.10]
event_cooldown_sessions: 5
top_k_values: [5, 10, 20]
false_falling_knife_threshold: -0.08
label_version: scanner-forward-v2
feature_version: phase2a_f_v2
market_feature_version: causal-market-v1
git_revision: f1d992ff24f0da3cf1c0f0036369c98ba725846d
git_dirty: true
```

主策略阈值包括：`min_elasticity=76.2143`、`min_pullback=0.08`、`max_pullback=0.40`、`min_prior_peak_gain=0.1323`、`min_wick_ratio=0.25`、`min_close_location=0.50`、`max_new_low_frequency_5=0.20`、`max_distance_from_ma5=0.15`、`max_rebound_from_5d_low=0.15`、`max_volume_contraction=0.80`，并开启明确基金名称过滤。

---

## 附录 B：建议的正式复现实验清单

在把当前研究升级为正式历史验证前，建议要求以下条件同时满足：

- [ ] Git working tree clean；
- [ ] Strategy version 与参数完全冻结；
- [ ] `ResolvedRunConfig` hash 保存；
- [ ] 数据快照 hash 保存；
- [ ] 真实 PIT Security Master 已导入；
- [ ] 退市/改名证券存在对应历史行情；
- [ ] Universe fingerprint 与覆盖区间记录；
- [ ] Train / Validation / Fresh OOS 日期在运行前确定；
- [ ] Fresh OOS 不参与任何参数选择；
- [ ] observation-level 与 event-level 指标同时报告；
- [ ] 重要比较使用日期或时间块聚类的重采样；
- [ ] 所有失败实验保留 trial ledger，而非只保存最佳结果；
- [ ] Scanner 与 Backtest 结论分开陈述；
- [ ] Vision、Quant、Fusion 使用完全一致的数据切分和 forward label。

---

## 参考文献

1. Brown, S. J., Goetzmann, W., Ibbotson, R. G., & Ross, S. A. (1992). **Survivorship Bias in Performance Studies.** *The Review of Financial Studies*, 5(4), 553–580. DOI: 10.1093/rfs/5.4.553.
2. White, H. (2000). **A Reality Check for Data Snooping.** *Econometrica*, 68(5), 1097–1126. DOI: 10.1111/1468-0262.00152.
3. Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2017). **The Probability of Backtest Overfitting.** *Journal of Computational Finance*. DOI: 10.21314/JCF.2016.322.
4. Niculescu-Mizil, A., & Caruana, R. (2005). **Predicting Good Probabilities with Supervised Learning.** *Proceedings of the 22nd International Conference on Machine Learning*, 625–632. DOI: 10.1145/1102351.1102430.
5. Jiang, J., Kelly, B., & Xiu, D. (2023). **(Re-)Imag(in)ing Price Trends.** *The Journal of Finance*, 78(6), 3193–3249. DOI: 10.1111/jofi.13268.

---

### 数据来源说明

本文中的 Stock Radar 项目状态、运行参数和实证数字来自本次对话中提供的项目背景以及用户上传的 `runs.sqlite3` 快照。本文未编造未出现在该快照中的收益率、Precision、Lift、样本数或模型结果。外部文献仅用于解释幸存者偏差、数据窥探、概率校准与视觉金融研究的方法论背景，不代表 Stock Radar 已经实现相同方法或达到相同实证结论。
