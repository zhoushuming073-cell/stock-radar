> **HISTORICAL DECISION / SUPERSEDED 2026-10-09：** 此 2026-10-08 决策记录完整保留供追溯。当前正式研究分类已统一到 [Research Master Guide](../../docs/RESEARCH_MASTER_GUIDE.md) 和 [三路径方向记录](research-direction-three-paths-2026-10-09.md)。双阶段 v3 仅保留为共享子系统。下方的 ACTIVE 仅描述当时状态。

# Quant + Vision Fusion — Current Research Direction · 2026-10-08

状态：**ACTIVE**

本文件记录 2026-10-08 人工实际试标后形成的研究路线迁移。旧视觉 P0/P1 验收报告继续作为工程事实保存，不因后续路线变化而重写。

## 决策

停止把“随机历史盲图的大规模人工审美标注”作为主要训练路线。

不是因为视觉模型被放弃，而是因为人工试标发现：

- 随机 A/B 图之间常常只是一个上涨、一个下跌；
- 在没有候选上下文时，“谁未来更有潜力”不是稳定、自然的人类问题；
- 强迫给出偏好会制造标签噪声。

视觉路线继续，且仍然需要人工监督训练。

新的主路线是：

**Quant 高召回候选 → Human 标签 → Vision M1 → Quant + Vision + Human → Quant + Vision**

## 当前阶段

下一阶段不是模型训练。

先建设：

**Quant-guided Human Labeling v1**

要做的事情：

1. 用宽松、连续、模糊的 Quant 因子从历史 eligible universe 产生候选图池；
2. 样本覆盖高分、中分、边界、冲突和普通对照；
3. 人工主标签改成 Observe / Do not observe / Uncertain；
4. 独立增加 Entry readiness：Buy now / Wait / Do not buy / Uncertain；
5. 标注页面隐藏 Quant 分数、股票身份、日期和未来结果；
6. 小批标注后检查稳定性，再训练 Vision M1。

## 人工的长期角色

早期：

**Human = teacher**

中期：

**Human = active-learning adjudicator**

优先判断 Quant/Vision 冲突和 Vision 不确定样本。

最终：

**Human leaves per-sample historical decision loop**

冻结系统只保留 Quant + Vision。

## 旧 P0/P1 资产

继续复用：

- Research Infrastructure v1
- normalized historical windows
- mplfinance renderer
- Label Studio local deployment
- task/image hashing
- leakage verifier
- Train/Validation/Test/Fresh isolation
- disappeared/acquired historical support
- private local manifests

旧随机 Pilot：

- 工程验收 PASS
- 正式人工 Ground Truth 0
- 不需要补完 50 Single +25 Pair
- 保留为基建验收证据，不作为当前主要训练 dataset

## 验证原则

未来必须比较：

- Quant-only
- Vision-only
- Quant + Vision

Fusion 必须在同一 universe / split / objective outcome 上证明增量。

Quant + Vision + Human 只属于训练/过渡阶段，不作为最终自动策略的公平历史考试版本。

详细计划见：

[Quant + Vision Fusion Research Plan v1](../../docs/QUANT_VISION_FUSION_RESEARCH_PLAN.md)