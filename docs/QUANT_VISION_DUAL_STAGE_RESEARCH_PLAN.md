> **MASTER-GUIDE STATUS UPDATE · 2026-10-09:** This document is now a **shared Vision/Human/Y subsystem specification**, not the sole project roadmap. The authoritative project taxonomy is [Research Master Guide](RESEARCH_MASTER_GUIDE.md): Quant-only / Quant + Vision / Vision-only. Engineering acceptance remains valid; the human trial is currently paused and no model training/backtest is implied.

# Stock Radar — Quant + Vision 双阶段标注与结果监督研究计划 v3

> 决策日期：2026-10-09  
> 状态：**SHARED INFRASTRUCTURE — D1/D2 ENGINEERING PASS; D3 DATA/UI READY; HUMAN TRIAL PAUSED**。2026-10-09 已完成真实本地工程验收；模型与收益验证尚未开始。
> **历史演进**：v3 当时整合了 Human-first v1 与 Outcome-only v2；现在 v1/v2/v3 均由 [Research Master Guide](RESEARCH_MASTER_GUIDE.md) 重新归类。v3 只负责共享 Vision/Human/Y 基础设施与方法合同。  
> **关键实施资产**：v3 真实本地工程已通过 PR [#9](https://github.com/zhoushuming073-cell/stock-radar/pull/9) 合并到 main；PR #7 只保留为历史 Draft / 源码来源。研究基建 Research Infrastructure v1 仍然 FROZEN、Shape READY、General PIT Tier 1。

## 0. 核心研究问题与新决定

最终问题：在 T 日收盘时，仅用 T 及此前当时可得的历史量价结构，能否通过 Quant + 数值时序 / Vision 找出更有利的未来数日交易候选，并让人工的形态直觉提供有增量的训练监督？

**本子系统原始流程（现作为三路径计划的共享能力）**：

```text
已知历史 eligible universe（带 PIT/缺价不确定性）
→ Quant 宽召回连续形态筛选 + 边界/冲突/普通对照
→ 决策左区 X(T) = OHLCV 原始/规范化时序 + 冻结的仅左区 SVG 表现
→ 人工仅看左区 → 保存并锁定 H_blind（观察 / 入场 / 置信度）
→ 服务端才允许揭示右区（T+1 ... T+H） → H_review 事后复盘
→ 独立程序根据真实未来行情计算 Y_future
→ Vision-H（模仿盲态人类）、Vision-Y（预测客观结果）和 Quant/时序基准
→ Quant + Vision + 少量 Human 主动学习复核
→ 冻结、无人逐笔干预的 Quant + Vision
→ 有效样本外 / LEAN / QC 按独立门禁验证
```

**禁令**：绝不把事后复盘 H_review 当作 T 日可见信息或盲态人类真值；人盲态决策与未来客观结果必须分开。模型预测时只允许 X_left 与当时已知的 Quant 特征 Q_left；绝不能接收右图、未来窗元数据或未来自适应坐标尺度。

## 1. 时间线：分界线是决策截止，不是已成交价

- 左侧最后一根蜡烛为决策日 **T 收盘**；这是信息集截止时刻和左右**数据边界**。
- 分界线右侧第一交易日为 **T+1**。最早假设在 T+1 **可成交的开盘价**建仓，不能假设看到 T 收盘以后又按 T 收盘价成交。
- 右侧显式标注“假设建仓 T+1 open”；若停牌、缺开盘价、公司行动/退市、开盘跳空等使成交有歧义，标记 unavailable/ambiguous，不用错误替代价。
- 首轮建议固定 H = **10 个交易日**作为主要未来验证窗；可保存 1/3/5/10 日辅指标。+5% 先于 -3% 的客观触达任务仅为 v2 预注册的**初始研究假设**，不是已验证最优值。正式训练之前审阅并冻结参数/费用/缺价和跨日触发细则。
- 同根未来日线 High/Low 同时触及目标与风险，不能声称知道先后，标记 ambiguous 并报告保守敏感性；跳空、停牌、无法成交及退出价格必须单列。

## 2. 左右矢量图：同一研究视图，严格双区数据边界

### 左区：T 时点可见

- 人工看 SVG（矢量）蜡烛+成交量，能够无损放大；不要求把纯 PNG 当作唯一输入。
- 复用已冻结研究接口的 canonical OHLCV、normalized tensor 和 **现有 SVG renderer（radar.pit.shape.render_svg）**的可重用部分；该 renderer/契约受冻结哈希保护，**不得原地修改**。为标注页另建版本化 wrapper/component/renderer。
- 左区视口、比例尺、宽度、颜色、蜡烛密度、成交量归一化、时间轴、裁剪/极值规则必须只由 X_left + 固定绘图配置决定，并记录 hash；同一个 left window 对应任意两个不同右区，左区 SVG/geometry/hash 应逐字节（规范化后）相同。
- 左区不显示 ticker、公司名、未来日期、Quant 分数、未来 Y 或市场结局；背景、URL/任务字段、文件名、DOM/网络预取也不透露未来。

### 右区：未来结果，仅用于解锁后复盘

- 右区是同一屏幕**视觉上相邻**的未来 K 线+成交量视图，含预定义 10-session 窗口、T+1 实际/假设可成交价标识、必要的涨跌百分比参考线；若缺价，忠实呈现缺失/歧义。
- 建议右区以 T 收盘价为**标注清楚的百分比参考**，并将 T+1 开盘成交价作为独立入场参考线；右区可使用明确标注的**独立纵轴/尺度**，不以其极值重新缩放左区。
- **禁止把左右数据合在一个 Matplotlib/SVG 自动缩放对象里重新计算左区 y 轴**。右区暴涨/暴跌时左区任何坐标、路径、体积、颜色、图幅均不能变化。即使要求左右视觉连续，也只能从冻结的左区显示参数出发，并单独绘制未来层，禁止反向影响左边。
- 揭示前，服务器不下发右区 SVG、右侧 OHLCV、未来结果统计或可推断未来的请求 URL；仅在 H_blind 成功持久化后由经授权的独立 endpoint 加载右区。**CSS 隐藏未来数据不是防泄漏**。
- 首次解锁、保存、编辑、复看有可审计 event 和 schema 状态；盲态标签在解锁后不可静默覆盖。后续修改只能带显式版本/原因与“post-reveal revision”标识，不能冒充原始盲态答案。

### 数据与表现形式分开

- `X_left_num`：规范化且带 hash 的 OHLCV 数值序列，便于 1D CNN/TCN、Quant 和审计。
- `X_left_svg`：**仅左区**冻结的矢量 SVG/几何路径，服务人工放大复盘和研究视觉信息。
- 2D CNN 一般不能直接输入 XML/SVG 文本：如果需要视觉 CNN，请对 SVG 进行**只使用左区的确定性 rasterization**并版本化，或单独研究矢量几何编码；不能把“SVG 清晰”错误等同于 CNN 不存在感知误差。
- 模型应公平比较数值序列、左侧确定性图像、Quant 与 Fusion；不得因为用户偏好 SVG 而强制所有机器模型只读图片。左侧 SVG 必须与数值窗口一一映射、能重播。

## 3. 人工标签：先盲态，后揭示，双层永久隔离

### H_blind（人工不知道右侧时）

主标签 **Observe**：观察 / 不观察 / 不确定。

独立标签 **Entry**：当前可买 / 等回落或进一步确认 / 不买 / 不确定。

再记录 Confidence 高 / 中 / 低，可选理由，如“仍下跌、初步转强、承接代理、最后一天已过度延伸、当前价位偏贵、形态凌乱”。

问题限定：“如果今天已是 T 日收盘，我会不会关注它？我能否接受最早 T+1 开盘尝试入场？”这不是要求人预测单日必涨。用户先保存 H_blind、记录时间与任务哈希，才能解锁右区。Skip / 不确定不是负样本；若跳过，不能自动解锁并冒称已做盲态判断。重复左图在揭示后的记忆污染须防范：重复一致性指标只在**首次揭示之前**且标注者未看过该样本右区的独立盲评之间计算；若此前已揭示，应标记 contaminated_retest，不纳入纯盲态一致性结论。

### H_review（右区已揭示后）

只做 **事后解释和错误归因**，不改写 H_blind：
- 当初判断是否合理、结构假突破/继续杀跌/回踩再涨/跳空风险；
- 形态质量与实际入场时机问题分开；
- 可选归因理由及“无法归因”，不鼓励事后编故事；
- 与 H_blind、Y_future 的偏差可用于诊断与主动学习审查，但 H_review 天然含事后知识，不能当成独立的实时决策标签或使用它来宣称策略盲测性能。

保存两个独立的 label version / event stream / origin。后续研究“学习 hindsight 解释”必须作为与直接 Y 监督不同的辅助实验预注册，绝不混同。

## 4. Y_future：程序生成的客观监督，不让人工猜

- 基于官方指定、可信历史数据和预先冻结的 T+1 入场约定，自动计算 forward returns、MFE/MAE、target-before-adverse、time-to-event、再创新低/跳空/退出/缺价。
- Y 与右图可以共享经过审计的未来价来源，但两者都不许进入左区、Q 候选选择、左视图缩放和 H_blind 提交前请求。
- Y 所属目标期限、交易费/滑点、盘中先后歧义、停牌退市、价格口径全部记录；Y 不可用则保留 missing/ambiguous，而不是删去导致困难样本全部消失。
- 禁止用查看后的 Y 调参 Quant 采样阈值，或把收益表现好坏当 H_blind 的正确答案。
- H_blind 教 Vision 对形态/入场直觉的表达；Y 教模型预测经济结果；这是**两种不同研究问题**。

## 5. Quant 样本来源、规模与选择偏差

- Quant 继续高召回模糊筛选，覆盖前期强势、回撤、跌势衰竭、承接代理、初步转强、收盘位置不过度延伸；保留高/中/边界/冲突/普通控制样本。
- PR #7 的 Quant-guided 代码后来已通过 PR #9 **选择性移植并与 main 协调**；原 PR #7 继续保留 Draft 作为历史 provenance。v3 当前 main 已有 300 unique +30 repeats 的工程资产，但这只证明数据/UI 可复用，不证明 Q1 或 Vision 有收益预测力。
- Pilot 样本只是选中且有缺口的历史集合，不是完整美股市场；已知别名/发行主体关系和退市/缺价覆盖仍需审计。必须保留抽样层、概率、被排除比例、发行人歧义；正式结果分别报告候选域与 eligible market 的基率、漏检、分年分环境。
- 原计划建议先做 10–20 张真盲态试用；**当前该人工阶段已由用户暂停**。暂停不撤销工程验收，也不自动授权继续到 50 张或模型训练。

## 6. 训练路线：先检查标签质量，再学人和预测结果

0. **研究前的对照**：Quant-only / random candidate / 轻量 LightGBM，禁止复刻现有冻结 Strategy 2 然后声称新研究已超越它。
1. **Vision-H**：X_left 图像/几何或数值序列 → H_blind 的 Observe 与 Entry；测人机一致性/校准/难例，不宣称它天然预测收益。
2. **Vision-Y**：X_left 的时序/图像 → Y_future 的客观事件/收益；报概率校准、选股 Lift 与风险。
3. **联合目标/蒸馏（可选，且受单独授权）**：当 H 足够稳定且 Y 可用时，先做清楚标注的有限多任务/表示学习试验，比较是否比两条单线有额外价值。不能把 H_review 混成盲态标签。
4. **过渡**：Quant + Vision 初步学会后，人工只复查 Vision 不确定、Quant/Vision 强冲突、疑似追高样本；H_blind 仍必须先于右区揭示。
5. **最终**：无逐笔人工裁决的冻结 Quant+Vision。比较 Quant-only、Vision-H、Vision-Y、sequence-only、Fusion；以未来真实 Y 的 OOS 增量和费用后执行风险决定是否保留复杂模型。人工准确率不是最终成功标准。

首轮不大规模训练、不自动搜索大量超参、不预设 Vision 一定比纯数值序列好。

## 7. 时间切分、审计和冻结约束

- 沿用仓库已冻结 Train/Validation/Historical Test/Fresh 定义；Historical Test 历史上已被查看，不能冒充首次真正 OOS。
- T+H 跨 split 必须 purge/embargo；同一股票/发行主体重叠窗口和相同图片不得被随机分入训练/验证两边，重复图不增加独立观测数。
- Fresh 数据准备与正式模型冻结后新时间段的验证严格分离。仅在合法/可复核的真正模型冻结证据和独立后续时间窗成立时，才谈新的 Fresh OOS。
- 研究基础设施、数据、Strategy 2 冻结代码、LEAN/QC 生产契约保持不变。
- 本计划不授权购买付费服务、运行正式 QC 视觉回测、实盘交易或改动冻结基础设施。

## 8. 分阶段交付和真实状态

| 阶段 | 应交付 | 进入下一阶段的门槛 |
| --- | --- | --- |
| V3-D0 文档与冲突决策 | 本计划、Codex 工作任务、总账、v1/v2 历史化，PR #7 保留审计 | 路线唯一、旧证据不变 |
| V3-D1 数据合同 | X_left_num / X_left_svg / H_blind / H_review / Y_future 的 schema 与 hash；T/T+1 约定 | 静态合同和负向测试通过 |
| V3-D2 双区 UI | 先左 SVG + 盲态提交，服务端之后才给右 SVG + 复盘页 | 真浏览器持久化/刷新/撤销和未来隔离 PASS |
| V3-D3 结果标签与质量 | 客观 Y、右区缺价/先后歧义；分层样本审计与首次真实人工反馈 | 真数据核验、人工认为标签有意义 |
| V3-D4 小模型基准（单独授权） | Quant、Sequence、Vision-H、Vision-Y 基准 | 先完成标签/时间分区审查 |
| V3-D5 Fusion/验证（单独授权） | 主动学习、冻结、正式 Test/Fresh 和 QC | 用户单独授权，按正式数据与执行门禁 |

**2026-10-09 实施验收：D1/D2 工程 PASS；D3 真实数据/交互 READY，用户反馈 PENDING。** 300 唯一图 +30 重复、728 Native-inclusive pytest、10 不同图真浏览器/11 次左右像素不变、2,623 保护哈希不变；原 PR #7 选择性移植且保留 Draft。仅经新实施 PR 发布验收后的源码，不把旧报告改写成新成果。[真实验收](../reports/acceptance/quant-vision-dual-stage-v3-acceptance-2026-10-09.md)，[本机操作](QUANT_VISION_DUAL_STAGE_LABELING_V3.md)。

## 9. 当前状态 / 下一任务

工程 D1/D2 与浏览器验收已经完成。当前人工试标被用户暂停；[Codex ACTIVE](../codex/tasks/ACTIVE.md) 也处于 PAUSED。未来若三路径总计划需要 Vision-H / Vision-Y 或 Fusion 数据，再单独授权继续。**未授权前不训练神经网络、不跑正式 Test/Fresh 或 QC。**