# Vision P0/P1：盲态人工标注基础设施

状态：**代码基建已建立；尚未训练模型。**

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

脚本会打开本地 Label Studio，并把 `data/` 设为允许读取的 local-files 根目录。不要把这个服务暴露到公网。

## 4. 生成首轮盲态任务

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

执行：

```powershell
& .\.venv\Scripts\python.exe scripts\prepare_vision_labeling.py
```

输出全部位于：

`data/vision-research/pilot-v1/`

该目录被现有 `.gitignore` 覆盖，不会上传 GitHub。

主要文件：

- `images/<opaque-id>.png`
- `sample-manifest.parquet`
- `pair-manifest.parquet`
- `label-studio-single-tasks.json`
- `label-studio-pair-tasks.json`
- `bundle-receipt.json`

图片文件名是哈希化 opaque ID，不包含 ticker / 日期。

## 5. 在 Label Studio 标注

建立两个本地项目。

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
& .\.venv\Scripts\python.exe scripts\import_vision_labels.py .\data\vision-research\pilot-v1\label-studio-export.json
```

默认写入：

`data/vision-research/pilot-v1/human-labels.parquet`

导入器会：

- 拒绝 manifest 之外的任务；
- 拒绝未知选项和不完整标签；
- 不连接未来 outcome；
- 计算重复图的简单自洽率；
- 保留 label version / 标注时间 / 标注者来源。

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
