# Vision P0/P1：盲态人工标注基础设施

> **当前用途更新 · 2026-10-08：** 这套 P0/P1 基建继续保留并复用，但“随机 250 图 / 125 Pair 的人工审美标注”已暂停，不再要求补完旧 50 Single +25 Pair。现行主线见 [Quant + Vision Fusion Research Plan v1](QUANT_VISION_FUSION_RESEARCH_PLAN.md)：下一批正式人工任务应由 Quant 高召回模糊筛选生成，并改用 Observe / Entry Readiness 标签。

状态：**P0 PASS / P1 INFRASTRUCTURE PASS；旧随机 Pilot 正式人工标注 0、PAUSED；Quant-guided 新标注尚未生成；模型训练 NOT_STARTED。**

真实本地 Pilot、测试和 Label Studio 验收见 [2026-10-08 验收报告](../reports/vision-p0-p1-pilot-acceptance-2026-10-08.md)。这表示可以开始人工标注，不表示视觉策略有效或 Ground Truth 已完成。

这套基础设施按 `docs/VISION_DEEP_LEARNING_RESEARCH_PLAN.md` 的 P0/P1 实施。目标不是先追收益，而是先建立可复现、无明显未来泄漏的人工 Ground Truth。

## 1. 直接复用的成熟组件

本阶段不重复造通用轮子：

| 需求 | 组件 | 边界 |
| --- | --- | --- |
| 人工单图/双图标注 | Label Studio | 本地运行；真实标签和图片不进 Git |
| K 线 + 成交量绘图 | mplfinance + Matplotlib | 只画截至 T 的标准化 OHLCV |
| DataFrame 合同 | Pandera | 校验私有 manifest 和 pair manifest |
| 美股交易日 | exchange_calendars | 检查 decision date 是真实 XNYS session |
| 边界/性质测试 | Hypothesis | 测 opaque ID、泄漏和异常输入 |
| 本地列式数据 | Parquet / PyArrow | manifest、标签中间件 |

本阶段**暂不接入** Optuna、MLflow/Aim、DVC、LightGBM、SHAP、QuantStats、Huey。它们分别属于模型训练/调参、实验登记、数据模型版本、解释、组合报告和大规模任务调度阶段；P0/P1 现在接入只会增加不必要的复杂度。

## 2. 数据边界

- 数据源只读使用冻结的 `Research Infrastructure v1`。
- 默认只从 **Train + Validation** 生成标注任务。
- **Historical Test 和 Fresh OOS 不进入首轮人工标注。**
- 默认只使用 confirmed/probable membership。
- 图片输入只有标准化 OHLCV；不显示 ticker、公司名、日期文字、未来涨跌、收益标签、Strategy 2 分数。
- 后来退市/被收购的四个已核验历史 security 作为隐藏 sampling anchor，标签页面不会显示其身份。
- 真实 security/date 映射只存在于 gitignored 的私有 manifest。

## 3. 安装

项目研究环境：

```powershell
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`dev` 已包含 P0/P1 需要的 mplfinance、Pandera、exchange_calendars、Pillow 和 Hypothesis。

Label Studio 建议使用独立虚拟环境，避免它的大依赖树污染 Stock Radar：

```powershell
.\scripts\start_vision_label_studio.ps1 -Install
```

后续启动：

```powershell
.\scripts\start_vision_label_studio.ps1
```

脚本只监听 `127.0.0.1:8123`，手动打开 `http://localhost:8123`；`data/` 是唯一 local-files 根目录。不要把这个服务暴露到公网。账号与随机密码保存在本机忽略目录 `data/vision-research/label-studio/local-login.json`，不要上传或分享这个文件。

Label Studio 使用独立 Python 3.11 环境。本机已安装；首次在其他电脑安装可用 `-Python311 <实际 python.exe 路径>` 指定 Python 3.11，脚本会核验版本，不会改主研究环境。

## 4. 生成并验收首轮盲态任务

默认配置：

`config/vision_research_v1.yaml`

默认首轮：

- 250 张唯一单图；
- 约 10% 重复单图用于自洽性；
- 125 组双图比较；
- 60/126 session；
- Train/Validation；
- 每个普通抽样 security 首轮最多一张图；
- 不读取未来 outcome 或 Strategy 2 score。

生成：

```powershell
& .\.venv\Scripts\python.exe scripts\prepare_vision_labeling.py
```

生成后必须立即验收：

```powershell
& .\.venv\Scripts\python.exe scripts\verify_vision_labeling.py
```

只有 verifier 返回 `status: PASS` 后，才把任务导入 Label Studio。验收器会核对：

- task JSON 与私有 manifest 是否一一对应；
- Label Studio 可见字段里有没有 ticker / security ID / 日期 / future / outcome / Strategy 2 信息；
- 图片 SHA-256 是否与生成时一致；
- 是否误用了 Historical Test / Fresh OOS；
- 是否误纳入 unknown membership；
- 单图、重复图和 pair 数量是否一致。

输出全部位于：

`data/vision-research/pilot-v1/`

该目录被现有 `.gitignore` 覆盖，不会上传 GitHub。

主要文件：

- `images/<opaque-id>.png`
- `windows/<opaque-id>-ohlcv.parquet` 和 `windows/<opaque-id>-normalized.parquet`（canonical 输入、独立哈希）
- `sample-manifest.parquet`
- `pair-manifest.parquet`
- `label-studio-single-tasks.json`
- `label-studio-pair-tasks.json`
- `bundle-receipt.json`

图片文件名是哈希化 opaque ID，不包含 ticker / 日期。

抽样 v2 按 split/year/window 分层轮流取样，每个 security 最多一张唯一图；故意重复任务与普通任务混排，ID 外观一致。当前 PNG renderer 为 `mplfinance-blind-v2`，固定 960×720。图像 SHA 绑定依赖环境；canonical OHLCV hash 是底层研究真相。已开始正式人工标注时，生成脚本会拒绝重建同一 bundle，以防任务漂移。

## 5. 在 Label Studio 标注

建立两个本地项目。

**本机已经配置好，无需再次导入：**

- Single 正式人工项目：`http://localhost:8123/projects/1/data`（275 个任务，含25个重复）。
- Pair 正式人工项目：`http://localhost:8123/projects/3/data`（125组）。
- 项目名含 `SMOKE — NOT HUMAN GROUND TRUTH` 的两个项目只用于验收，不用于正式标注。

旧正式项目仍可用于回归/界面检查，但**不要继续把 50张 Single +25组 Pair 当作当前研究任务**。下一批正式任务将由 Quant-guided candidate pool 重新生成；用户主要标注“观察 / 不观察 / 不确定”，并可独立标注“当前可买 / 等回落或确认 / 不买 / 不确定”。Quant 分数、股票身份、日期和未来结果仍应在人工页面隐藏。

在其他电脑重建项目时，除了下述模板与 JSON 导入，还须在项目 **Settings → Cloud Storage → Add Source Storage → Local Files** 添加实际的 `data/vision-research/pilot-v1/images` 绝对路径；仅用于图片访问授权，**不要 Sync**，否则会额外生成不符合合同的图片任务。Label Studio 1.23 的本地文件访问要求项目级存储授权，仅设置环境变量不够。参考 [官方本地存储说明](https://labelstud.io/guide/storage.html#Local-storage)。

### 单图项目

Labeling config：

`labeling/vision-single.xml`

导入：

`data/vision-research/pilot-v1/label-studio-single-tasks.json`

标签：

- 很喜欢
- 一般
- 不喜欢
- 看不懂

可选主观原因：

- 下跌未停
- 承接明显
- 拉升已过
- 疑似形态异常

同时记录高/中/低置信度。

### 双图项目

Labeling config：

`labeling/vision-pair.xml`

导入：

`data/vision-research/pilot-v1/label-studio-pair-tasks.json`

选择：

- A 更值得继续观察
- B 更值得继续观察
- 都不好
- 难判断

标注时不要通过其他窗口查 ticker 或之后走势。

## 6. 回收标签

从 Label Studio 导出 JSON，然后：

```powershell
& .\.venv\Scripts\python.exe scripts\import_vision_labels.py .\data\vision-research\single-export.json --kind single
& .\.venv\Scripts\python.exe scripts\import_vision_labels.py .\data\vision-research\pair-export.json --kind pair
```

默认写入：

- Single：`data/vision-research/pilot-v1/human-single-labels.parquet`
- Pair：`data/vision-research/pilot-v1/human-pair-labels.parquet`

同一任务重新标注后导入会按 task ID 更新，保留之前的其他标签；不同 label version 不混写。测试导出必须添加 `--smoke`，固定使用 `smoke-vision-v1`，写到独立 `data/vision-research/smoke/smoke-single-labels.parquet` 或 `smoke-pair-labels.parquet`。含 `meta.label_origin=smoke` 的任务不能按正式标签版本导入。

导入器会：

- 拒绝 manifest 之外的任务；
- 拒绝未知选项和不完整标签；
- 不连接未来 outcome；
- 计算重复图的简单自洽率；
- 保留 label version / 标注时间 / 标注者来源。

Pair 项目只保存偏好和置信度，不产生单图重复一致性。正式一致性仅在用户亲自标注后计算；smoke 的一致性只证明映射机制可用，不代表人的判断质量。

## 7. 研究纪律

人工标签 A 与未来客观结果 B 永远分开。

P0/P1 只回答：

1. 图能否稳定、盲态、可重复地产生；
2. 人能否快速标；
3. 自己重复看同一图是否相对一致；
4. 数据覆盖是否有明显年代/退市偏差。

首轮完成前不训练 M1，不跑 QC，不看“哪种标注最赚钱”。

下一阶段 P2 只有在人类标注稳定性和样本偏差报告出来后才进入。M1 优先使用成熟的 PyTorch/torchvision 小模型（ResNet-18 量级），不会自写 CNN 框架。

## 8. 为什么仍保留现有 SVG renderer

`radar.pit.shape.render_svg` 是 Research Infrastructure v1 已冻结的审计 renderer，不删除、不替换。

P0/P1 新增的 mplfinance PNG 是**人工标注展示层**。Canonical OHLCV hash 仍是数据真相；PNG hash 只绑定当前 renderer/dependency 环境，避免为了“用轮子”破坏已经冻结的审计合同。