# Vision P0/P1 基建进度 — 2026-10-08

> 历史分支骨架报告，保留原始阶段证据。当前实际验收已完成，见 [真实 Pilot 验收](vision-p0-p1-pilot-acceptance-2026-10-08.md)；不要把下列旧的“尚未完成”当作当前状态。

状态：**IMPLEMENTED ON BRANCH / LOCAL PILOT NOT YET BUILT**

分支：`vision-p0-p1-infrastructure`

目标来自 `docs/VISION_DEEP_LEARNING_RESEARCH_PLAN.md`。本轮只实施 P0/P1，不训练模型、不运行正式 Test/Fresh、不修改 Strategy 2。

## 已落地

- 新增独立 `radar.vision` 包。
- 使用 mplfinance/Matplotlib 生成去身份 K 线 + 成交量 PNG。
- 使用 Pandera 校验本地私有 sample/pair manifest。
- 使用 exchange_calendars 校验历史 decision session。
- 使用 Hypothesis 和 pytest 建立盲态/泄漏/标签输入测试。
- 使用 Label Studio Community Edition 作为单图和双图标注工具，不自建标注网站。
- 首轮配置默认 250 unique singles + 10% repeats + 125 pairs。
- 首轮只使用 Train/Validation，禁止 Historical Test/Fresh。
- 默认不纳入 unknown membership。
- 四个已核验 later-disappeared/acquired security 仅作为隐藏样本 anchor。
- 真实 identity/date 只写入 gitignored private manifest；任务 JSON 只有 opaque ID 和本地图片地址。
- Label Studio export 可回收为统一 parquet，并计算重复标注一致性。
- 新增 `scripts/verify_vision_labeling.py`：生成任务后自动检查图片 hash、任务/manifest 对应、可见字段泄漏、split 边界和 membership 边界。

## 尚未完成

- 尚未在用户本机安装新增 optional dependencies。
- 尚未对 540 万级冻结研究底座实际生成首轮 250 张 pilot。
- 尚未运行新增完整 pytest。
- 尚未运行 bundle verifier 的真实 pilot 验收。
- 尚未产生任何人工标签。
- 尚未评估标注一致性。
- 尚未训练 M1。
- 尚未生成未来 outcome 评价。
- 尚未运行 QC。

因此本报告不能写 P0/P1 PASS，只表示实现骨架已经进入可执行状态。**合并 main 前必须在真实本地冻结数据上完成：全量测试 → pilot 生成 → bundle verifier PASS。**

## 开源复用边界

当前实际采用：Label Studio、mplfinance、Pandera、exchange_calendars、Hypothesis、PyArrow。

后续阶段再采用：PyTorch/torchvision（M1）、MLflow/Aim（实验登记，达到多实验规模后）、Optuna（明确允许的有限调参阶段）、DVC（数据/模型版本量增大后）、SHAP/QuantStats（对应解释和组合报告阶段）。

不因为“能装”就提前接入与当前阶段无关的轮子。
