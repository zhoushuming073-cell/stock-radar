# Quant-guided Human Labeling v1 操作说明

本轮范围：Quant 找题 + 本人标注。没有训练模型、未来收益标签、视觉回测或 alpha 验证。

## 开始标注

正式本机项目：[Quant-guided v1 READY — Human Ground Truth](http://localhost:8123/projects/7/data)。点击 **Label All Tasks**。

第一批完成 **50 个任务**即可，包含少量隐藏重复；不要刻意找重复。Observe、Entry、Confidence 必填，原因可不选。

- **Observe**：观察 / 不观察 / 不确定。是否值得在未来几天重点看？
- **Entry**：当前可买 / 等回落或进一步确认 / 不买 / 不确定。只根据最后一根收盘信息形成意向，尚不知道下一开盘价。
- 二者独立：形态值得观察、最后一天涨太远，可以选「观察 + 等回落或进一步确认」。
- Confidence：高 / 中 / 低。原因是辅助信息，不是逐项筛选条件。

Submit 保存并切到下一张；Undo/Redo 撤销/恢复未提交操作。Skip 保留任务，之后在数据列表打开该任务，点击 **Cancel skip** 再提交。修改已保存标签：数据列表打开该任务，改选项后 **Update**；刷新可恢复已保存结果。默认 1440×1000 桌面已实测，编辑模式也能完整看到选项；缩放工具可放大最右侧蜡烛。

只使用 **READY — Human Ground Truth**。项目9为最终 **SMOKE WSGI**，全部是测试操作，不是人工真值；项目8是静态资源修复前的失败smoke。项目5/6是修正抽样前的预发布项目，保留审计，不继续标注；原项目1–4与旧Pilot（含旧Pair5标签）完整保留。

若服务未启动，在项目根目录运行（可复用原启动入口）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_vision_label_studio.ps1
```

Label Studio 使用独立 `.venv-label-studio`；已安装 Label Studio 1.23.2、Waitress3.0.2、WhiteNoise6.12.0。使用官方CLI初始化和原Django/Label Studio路由，单线程Waitress服务、WhiteNoise服务官方collected静态文件，规避本次SQLite连接异常和hashed资源404；不另建标注网站。缺少依赖时使用同一脚本的 `-Install`。登录信息只在 `data/vision-research/label-studio/local-login.json`，不得上传或复制进报告。

## 本地文件和生成命令

正式配置：`config/quant_vision_labeling_v1.yaml`。正式私有目录：`data/vision-research/quant-guided-v1/ready/`。

```powershell
.venv\Scripts\python.exe scripts/prepare_quant_guided_labeling.py
.venv\Scripts\python.exe scripts/prepare_quant_guided_labeling.py --verify-only
.venv\Scripts\python.exe scripts/setup_quant_guided_label_studio.py
.venv\Scripts\python.exe scripts/replay_quant_guided_labeling.py
```

已有目录禁止重新生成。需要研究新配置时，另设版本和输出目录、新建项目；不可覆盖正在标注的批次。Replay 只重新验证和渲染比较，不写入人工标签。配置/生成器 hash、私有数值窗口、图片、task、manifest 必须相符，否则拒绝。

本轮曾在预发布扫描结果上发现阶段二随机排序复用问题，修正为独立 `stage2` hash；正式批次复用已校验且未改变的 290,909 个历史 Q 输入，重新抽样、逐个核对冻结 API 并重新渲染 300 张图片。旧批次不覆盖。缓存只在冻结基础设施、特征 kernel、扫描配置和 artifact hash 一致时允许使用，正常首次生成仍读取冻结库。

## Quant 特征与初值

`fuzzy-shape-v1` 只接收 T 日前的 canonical OHLCV，不能接收 Strategy 2 分数、未来收益或人类答案。价格和成交量分别归一化；不恢复严格 PIT 绝对价格/成交额。

| 维度 | 连续特征 | 初始权重与直觉 |
| --- | --- | --- |
| Strength | 5/20/60/125 区间收益、前高相对前低涨幅、近期高低位置、最大三根上涨日占正收益比例 | 22%；5%–60% 前涨幅渐增，少数极端日集中的强势减分 |
| Pullback | 前高到 T 收盘回撤、持续 session、近期低点变化、下跌加速度 | 18%；回撤 3/15/45/75% 梯形，持续 2/8/50/110 session 梯形；持续破位减分 |
| Exhaustion | 最近 5 vs 前 10 日负收益、阴线实体比、波动比、近期低点变动 | 18%；收缩和低点不再明显降低加分 |
| Support proxy | 下跌量比、上涨/下跌量比、下影占比、收盘位置、单日量异常 | 14%；OHLCV 承接代理，**不证明主动买盘** |
| Turning | 最近五根阳线比例、收盘位置、五日收益、局部结构距离 | 14%；小幅改善加分，不要求大幅突破 |
| Entry location | 最后一天收益、距 20 日低点、距 10 日均线、五日快速反弹 | 14%；单日 3–12%、低点反弹 10–45%、均线偏离 3–20%、五日 6–25% 连续惩罚 |

所有评分 knots、维度/组件权重和惩罚在 YAML 中公开；这是形态直觉初值，未使用未来收益或 H 优化。特征回看长度属于版本固定定义：窗口 60 根只能提供 59 个日间收益，因此 `return_n` 使用 `min(n, window_length-1)`；后续模型必须同时读取 window_length，不把不同可用回看当成同一尺度。

宽松分层：高分 >=65，中等 >=50，边界 >=35；shape >=55 且 extension >=45 单独归 conflict。高/中/边界/冲突各层并非人工答案。Control 从同期安全代表池按年份/窗口分层抽取，**不以 score 限制**，可能本来就是高分形态。

## 抽样和偏差

每 20 个有安全窗口的历史 session 扫描一次，所有当日已观测、confirmed/probable、完整 Train/Validation 窗口都参与；不使用今天上市名单。60/126 窗口分别计算。未知资格、跨 split、不完整/异常/不安全窗口继续由冻结索引隔离。

第一阶段在每个已知 CIK 或 root security 的所有扫描窗口中用 uniform hash 取一个代表。第二阶段使用**独立** hash，在隐藏层的年份/窗口 cell 中等额轮转、均匀抽取；四个可信消失/并购历史证券保留为 forced anchors。每个 batch 每 security/已知 issuer 仅一个样本，无高度重叠窗口。

私有Q记录stage1、stage2条件概率、cell、分层、候选量、排除统计、来源和版本。Quant来源层的stage2概率条件于 **control已抽走后的可用代表池**；`conditional_path_probability`只保存两项条件概率的数值乘积，**不是全流程联合选择概率，更不是完整市场边际inclusion probability**，不得直接作为IPW。未来概率研究还须显式处理control先抽的条件/生存事件及随机代表池。随机种子、所有扫描Q、代表池和选取顺序都保存供偏差分析。

大部分 root ID 尚无已核验跨 ID 的 issuer CIK，明确记 `issuer_known=false`。不靠今天的 ticker/name 猜测合并。root 证券不重叠不等于已证明发行主体全局不重叠，未来分组切分/训练仍需审查 alias 风险。本批不包含 membership unknown，但不是完整无缺价的美股总体，也没有测量目标形态的真正召回率。

## Q / X / H / Y 合同

| 数据 | 文件 / 关联 |
| --- | --- |
| Q | `quant-features.parquet`：private task_id、security/date、完整因子、六维/shape/extension/quant score、feature version、来源层、条件概率；全扫描 Q 在 `scanned-features.parquet` |
| X | `images/` + `windows/` + `sample-manifest.parquet`：60/126 根规范化 OHLCV、raw/normalized/image hash、renderer version、冻结库 hash、split、安全状态、私有重复映射 |
| H | `labels/human/labels.parquet`：Observe、Entry、Confidence、Reasons、task/annotation/project ID、schema/origin、created/updated、repeat_group；`revisions.json` 追加保留历史版本，content-hash 原始 JSON 永不覆盖 |
| Y | **本轮不存在、未读取**。未来另立 outcomes 表与计算版本、next-open availability/entry reference，才可计算 1/3/5/10 日收益、MFE/MAE、+5/-5% 先后触达 |

Label Studio 可见 JSON 只有 `data.image` 和 opaque `data.task_id`，没有 Q、ticker、日期、身份、机器建议或 Y。导入服务器的 `meta` 只含标签 schema/origin。Vision-only 以后只接 X 和 H；Fusion 可通过私有 manifest 接 Q；Y 不得进入人工任务或图像。重复不是独立训练观测。

## 导出和回收

Label Studio 正式项目的 Export → JSON 保存到被 Git 忽略的本地目录，再运行：

```powershell
.venv\Scripts\python.exe scripts/import_quant_guided_labels.py data/vision-research/my-human-export.json --origin human
```

导入器严格检查真实 project ID、task/图片映射、version=`quant-human-v1`、origin、choice 和时间；同任务多个完成 annotation 要求明确 adjudication。相同 revision 再导入幂等；相同 revision 不同内容、过期 revision、跨 annotation ID 冲突拒绝。修改保存为新 revision；原 JSON/旧 revision 留存。每 namespace 单写者锁避免并发覆盖。

Smoke 只能 `--origin smoke`，进入独立 `labels/smoke/`。取消/跳过不当作 H。重复一致性分别统计 Observe 和 Entry；smoke 的一致次数只验证管线，不能冒充本人人工自洽率。

GitHub 不含真实行情图、security/date 映射、任务 JSON、数据库、标签、登录凭据和浏览器 session。公开的报告只含汇总、hash 和测试结果。

## 下一阶段

先完成本人约 50 个任务，再检查标签含义、Observe/Entry 独立性、置信度与漏标情况；对真正人工重复做描述性一致性检查。之后收集足够的 Train/Validation H，冻结图片/合同/数据快照、issuer 分组与模型评估计划，获得用户明确授权才进入 Vision M1。当前没有训练结果、Fusion alpha 或 QC 收益声明。
