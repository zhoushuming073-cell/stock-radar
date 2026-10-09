# Stock Radar — Quant + Vision Fusion Research Plan v1

> 日期：2026-10-08  
> 状态：**ACTIVE RESEARCH DIRECTION**  
> 取代：把“随机盲图人工审美 → 纯视觉模型”作为主线的旧方案。旧 P0/P1 基建与验收继续保留并复用。  
> 数据底座：Research Infrastructure v1（FROZEN）  
> 数据库状态：Shape Research READY；General PIT Tier 1 deep/audit；Database expansion CLOSED；maintenance ACTIVE。

## 1. 当前研究目标

### 2026-10-09 实施状态

**QVF-1 + Human labeling infrastructure READY**：冻结历史库44个session切片、290,909个安全窗口，300唯一图+30隐藏重复，五种隐藏来源层90/70/50/60/30；独立Observe / Entry / Confidence / Reasons项目可使用。正式项目7有330任务0新标签，用户先做50任务；已有旧Pair5标签完整保留。完整674项测试通过，Native LEAN实际执行；300PNG和600canonical windows重放一致，真实浏览器10独图+重复/保存/修改/跳过/刷新及smoke回收PASS。

具体合同/初值/概率语义见 [实施说明](QUANT_GUIDED_LABELING_V1.md)，[真实验收](../reports/acceptance/quant-vision-human-labeling-v1-acceptance-2026-10-09.md)。候选分布有选择偏差；295个样本跨root issuer身份仍未核验、历史missingness明确保留。高召回尚未由人工真值测量。VisionM1 / Fusion / Y /正式视觉QC仍NOT_RUN，必须等待本人真实标签与下一阶段授权。

当前目标不是让视觉模型直接在全市场“凭感觉”找股票，也不是让人工去猜下一交易日涨跌。

目标是建立一个逐步放权的研究流程：

**Quant 高召回模糊筛选 → 人工判断 → Vision 学习人工判断 → Quant + Vision + 人工过渡 → Quant + Vision 自动化**

核心分工：

- **Quant**：把“前期强势、回撤、跌势衰竭、承接、初步转强、不过度延伸”等语言模糊量化，先把全市场压缩成一个高召回候选池。
- **Human**：对 Quant 候选的图形做真正的交易式判断，定义哪些值得继续观察、哪些当前已不适合买。
- **Vision**：只看当时可见的 K 线与成交量图，学习人工难以完整写成规则的形态判断。
- **Fusion**：最终把 Quant 的数值结构和 Vision 的图形结构结合，逐步减少人工参与。
- **Future outcomes**：作为独立考试，不作为首轮人工标签的答案来源。

## 2. 为什么调整旧纯视觉路线

P0/P1 已证明盲图生成、去身份、Label Studio、本地保存、防泄漏、Train/Validation 隔离等基础设施可用。

但实际试标暴露了一个研究问题：

**随机抽取两张历史图要求人工判断“谁未来更有潜力”，标签语义过于模糊，容易产生被迫选择的噪声。**

因此不继续把“随机图审美偏好”当成主要 Ground Truth。

保留的价值：

- 盲图与 renderer
- 60/126 session 历史窗口
- Hash / provenance
- Train / Validation / Test / Fresh 隔离
- later-disappeared / acquired 样本进入能力
- Label Studio / 本地标签存储
- 防 future leakage
- 人工重复标注与一致性工具

调整的是：

- 样本来源
- 人工问题定义
- Vision 的训练目标
- Quant 与 Vision 的关系

## 3. Phase QVF-1 — Quant 高召回候选生成

### 3.1 Quant 的角色

Quant 不负责在这一阶段直接给最终买入答案。

它只负责：

**把几千只股票缩小成“值得给人/视觉模型看”的宽候选池。**

因此优先追求 recall，而不是 precision。

不应使用一个极窄的 Strategy 2 硬门槛把候选提前筛得过于相似。

### 3.2 模糊量化方向

可以继续围绕：

- prior strength
- pullback depth / quality
- downside exhaustion
- stopped making new lows
- support / absorption
- early reversal
- volume behavior
- extension / overbought distance
- close location
- distance from short-term support / moving references
- recent one-day acceleration

这些因子应尽量连续化或宽松分段，而不是全部转成硬 pass/fail。

### 3.3 样本池必须包含难例

人工训练池不能全是 Quant 高分股票。

至少要混入：

- Quant 高分
- Quant 中等分
- 边界样本
- 某些条件很好、某些条件明显失败的冲突样本
- 少量普通 eligible 市场对照

目的：

**让 Vision 有机会学习 Quant 没有表达清楚的边界，而不是成为 Quant 的复读机。**

## 4. Phase QVF-2 — 人工标注定义

人工仍然是 Vision 第一阶段的老师。

但标签从“哪张未来更有潜力”改成更贴近真实决策的问题。

### 4.1 Primary label — Observe

主标签：

- **观察**
- **不观察**
- **不确定**

问题固定为：

> 如果今天已经收盘，只看这张当时可见的 K 线与成交量，我会不会把它放进接下来几天的重点观察名单？

这不是预测明天一定涨。

### 4.2 Secondary label — Entry Readiness

为了表达“形态不错，但最后一天收盘已经不便宜”，增加独立的第二层标签：

- **当前可买**
- **等回落 / 等确认**
- **不买**
- **不确定**

问题固定为：

> 如果 T 日已经收盘，假设最早 T+1 开盘执行，我现在是否愿意进入？

这和 Observe 必须分开。

允许出现：

- Observe = 观察；Entry = 等
- Observe = 观察；Entry = 当前可买
- Observe = 不观察；Entry = 不买

### 4.3 可选理由

理由只用于分析和解释，不作为硬规则答案：

- 仍在下跌
- 承接明显
- 已开始转强
- 已经涨太远
- 价格位置舒服
- 价格位置偏贵
- 结构凌乱
- 看不清

不要要求每张图填写大量原因。

### 4.4 标注时隐藏 Quant 分数

用户知道这些图来自 Quant 宽筛，但标注页面默认不显示：

- Quant 总分
- 各因子分
- ticker / company
- date
- future outcome
- Strategy 2 rank

避免锚定人工判断。

## 5. Phase QVF-3 — Vision M1 初始训练

当人工积累第一批有效标签后，训练 Vision。

第一版建议：

- PyTorch / torchvision
- ResNet-18 量级
- 输入：纯图像（K 线 + volume）
- 不输入 Quant 特征
- 不输入 ticker / metadata / future outcome
- 输出至少：
  - Observe score
  - Entry readiness score（若第二标签质量足够）

第一阶段 Vision 的任务是：

**学习人的形态判断。**

不是直接承诺收益。

## 6. Phase QVF-4 — Quant + Vision + Human 过渡

Vision 有初步梯度下降和稳定参数后，不再让人工看所有 Quant 候选。

流程：

**全市场 → Quant 宽筛 → Vision 初筛/排序 → Human 只处理高价值样本**

人工优先处理：

- Vision 最不确定
- Quant 与 Vision 强烈冲突
- 模型经常出错
- Quant 高分但 Vision 低分
- Vision 高分但 Quant 认为过度延伸
- 重要边界样本

这是主动学习阶段。

人工工作量应逐渐下降。

### 6.1 过渡期允许人工最终评分

此阶段可以形成：

- Quant score
- Vision score
- Human review

但必须分别保存，不把人工判断伪装成机器信号。

目标是观察：

**机器什么时候已经足以替代大部分人工复核。**

## 7. Phase QVF-5 — Quant + Vision 自动研究系统

最终历史研究和正式验证版本中，人工退出逐笔决策链。

冻结后流程：

**全市场 → Quant 候选池 → Vision 图形评分 → Fusion → Watch / Entry 排名**

建议保留两个结果：

### Watch Score

形态是否值得继续观察。

### Entry Score

当前价格位置是否已经适合执行。

最终系统可产生：

- Watch List Top N
- Entry-ready Top N

人工只做：

- 模型审计
- 异常案例研究
- 周期性质量检查

而不是逐个历史样本决定买卖。

## 8. Future outcome 的角色

客观未来结果 Y 与人工标签 H 必须长期分开。

例如固定评估：

- T+1 open 后 1/3/5/10 session return
- MFE
- MAE
- +3/+5/+8/+10% target
- adverse threshold
- target-before-adverse
- time-to-target
- new-low / falling-knife rate

这些结果用于回答：

- Quant-only 是否有增量？
- Vision-only 是否学到了人的判断？
- 人工判断是否有真实统计价值？
- Quant + Vision 是否比 Quant-only 更好？

在进入正式 Test/Fresh 前先冻结指标。

## 9. 必做对照

同一 universe、同一时间切分、同一 future labels 下至少比较：

1. Quant-only
2. Vision-only
3. Quant + Vision Fusion
4. 过渡期 Quant + Vision + Human（仅作为开发诊断，不作为最终无人值守策略）

最终自动系统只有当 Fusion 稳定优于 Quant-only，才有保留复杂度的理由。

## 10. 数据与 OOS 纪律

沿用 Research Infrastructure v1。

开发阶段：

- Train：生成候选、人工标注、模型拟合
- Validation：模型选择、有限超参、Fusion 权重研究
- Historical Test：模型/规则冻结后少次数评估
- Fresh OOS：冻结后新积累，不能回流调参

不随机打散同一证券的高度重叠时间窗口。

已经看过的数据不能重新命名成 Fresh。

## 11. 当前实际状态

截至 2026-10-08：

### 已完成

- Research Infrastructure v1 FROZEN
- Shape Research READY
- 视觉 P0/P1 基建 PASS
- 250 unique +25 repeat +125 pair 的旧 Pilot 已完成工程验收
- Label Studio 本地链路 PASS
- 632 tests PASS（含 Native LEAN）
- 旧随机盲标正式人工 Ground Truth = 0

### 路线迁移

旧的“随机 Single/Pair → 大量人工审美标签 → 纯视觉”为主线的方案：

**PAUSED / SUPERSEDED AS PRIMARY PATH**

原因：

人工发现问题定义本身缺乏稳定意义。

### 当前下一步

**构建 Quant-guided Human Labeling v1。**

先不要训练模型。

先完成：

1. Quant 高召回候选规则/连续分数定义
2. 候选采样构成
3. 新 Observe / Entry 标签 schema
4. 在现有本地标注基础设施中生成新任务
5. 小批真实人工标注
6. 检查标签稳定性和分布
7. 再进入 Vision M1

## 12. 当前不做

本阶段不要：

- 删除旧 P0/P1 基建
- 把旧随机 Pilot 标签强行补满
- 直接用 future return 代替人工标签
- 直接跑 Historical Test / Fresh
- 直接跑 QC Vision
- 修改冻结 Strategy 2 参数
- 让 Quant 分数在标注页面给人工暗示
- 一开始就做大型 ViT
- 一开始就优化 Fusion 到回测最好看

## 13. 最终成功标准

最终目标不是：

“Vision 能模仿人工。”

而是：

**Quant 负责可解释的数值候选空间，Vision 学到人工难以手写的图形结构，两者在无人逐笔干预的冻结版本中，对未来未见时期提供稳定、可复核的候选排序增量。**

路线：

**Quant 找题 → Human 判题 → Vision 学判题 → Quant + Vision + Human 过渡 → Quant + Vision 独立运行 → Test / Fresh → QC 验证。**
