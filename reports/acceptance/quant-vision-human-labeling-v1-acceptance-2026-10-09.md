# Quant-guided Human Labeling v1 — 真实本机验收

日期：2026-10-09。状态：**Quant-guided Human Labeling READY**。

范围：Quant 高召回候选生成与独立人工标注合同/界面。**未训练 Vision，未计算/读取 Y，未做视觉 QC 回测，未发现或声称 Fusion alpha。**

基线：GitHub/local main `6b6e6face90e5ec0423be01396bd257f385e7f43`；分支 `quant-guided-human-labeling-v1`。Native Git fetch 两次连接超时，使用已连接 GitHub API 核对 main，完全相同；不存在未合并本地修改。旧 P0/P1 的 632 项测试是历史基准，本轮重新执行。

## 1. 实际实现

- `quant_features.py`：纯 OHLCV、尺度不变、T-prefix 因子与六维模糊评分，另存 shape/extension score。不是 Strategy 2 门槛复刻。
- `quant_guided.py`：冻结 historical visual index 的只读批量适配、historical membership、causal split normalization；入选 300 个窗口全部与冻结 API 重新逐值核对。
- `quant_contracts.py`：Q 全人口/字段/版本/安全状态、Q/X 数值重算、配置/生成器/文件 hash、两阶段抽样重放。
- `quant_labels.py`：Pydantic H、项目/namespace/version/choice 严格校验、幂等导入、原 JSON 内容 hash 保存、旧 revision 保留、冲突/过期拒绝、单写者锁、Observe/Entry 分别重复统计。
- 复用 mplfinance renderer `mplfinance-blind-v2`，960×720，price + volume，完整首尾边界，无 ticker/date/轴文字/机器建议。
- 独立 Label Studio 项目，沿用本机账号、数据根与 local-file storage authorization；没有 Storage Sync，也没有新标注 Web 服务。
- Windows CLI bootstrap → 单工作线程 Waitress 3.0.2 + WhiteNoise 6.12.0；继续使用 Label Studio 1.23.2 原路由、模型和保存。

详细因子定义、权重/直觉、合同、命令和操作见 [说明书](../../docs/QUANT_GUIDED_LABELING_V1.md)。所有 knobs 在 `config/quant_vision_labeling_v1.yaml`；版本 `quant-guided-v1` / `fuzzy-shape-v1`。未使用 H 或未来收益优化初值，未读 Historical Test/Fresh。

## 2. 真实历史覆盖和候选分布

按固定 20-session grid 扫描 **44 个历史交易日**。基于冻结历史索引，不是今天存活名单。

| 指标 | 实际数量 / 含义 |
| --- | --- |
| 已观测 confirmed/probable member security-days | 219,520 |
| 同期 unknown member security-days | 21,853，未进入正式 Q/H 样本 |
| 完整安全窗口可评分 security-days | 163,233 |
| 已观测成员但无安全 60 日 visual 窗口 | 56,287；包含历史不足、缺口、冲突/隔离或跨 split，未伪造细分类数 |
| 完整安全 60/126 窗口 Q | 290,909；60 日 163,233，126 日 127,676 |
| 扫描 root securities | 5,902 |
| score-guided 高/中/边界/冲突窗口 | 285,398；另有 5,511 低分窗口，control 并不限于低分 |
| 唯一入选 | 300 个 security/window；30 个隐藏重复，330 个单图任务，0 Pair |

unsupported visual-index entries 额外保留统计：窗口末日 membership unknown / minor 28,999；confirmed / READY 1,780；probable / minor 3,042；confirmed / minor 34。后面三类不能因为末日可信就绕过窗口内 unknown 的冻结门禁。这是 index-entry 分母，不能与 security-day 排除直接相加；缺失或完全未成窗的行不在该 index 分母中。

全扫描 Q 的连续总分：min 15.14，P5 39.51，P25 51.15，median 59.67，P75 67.83，P95 79.62，max 97.83，std 12.06。不是全部挤在单一分值附近。

| Quant 分类 | 全扫描窗口 | 正式抽样来源层 |
| --- | ---: | ---: |
| High | 92,534 | 90 |
| Medium | 127,001 | 70 |
| Boundary | 58,911 | 50 |
| Conflict | 6,952 | 60 |
| Ordinary control | 无 score 限制；5,511 为低于边界的自然分类 | 30 |

抽样层和事后 Q 分类不同：普通对照可能恰好是高分/冲突。300 样本的实际 Q 分类为 high 101、medium 82、boundary 55、conflict 61、低分 1；不能把 30 controls 谎称成 30「负样本」。

| 年份 | 扫描窗口 | 唯一样本 |
| --- | ---: | ---: |
| 2021 | 7,070 | 33 |
| 2022 | 72,311 | 72 |
| 2023 | 88,147 | 69 |
| 2024 | 60,794 | 64 |
| 2025 | 62,587 | 62 |

窗口：60 日 **167**、126 日 **133**。Split：Train **238**、Validation **62**，Test/Fresh **0**。2021 的 126 日完整窗口还不足，所以不假造等额年度/窗口覆盖。

历史环境的描述性代理（同期安全证券 20 日收益中位数，不是 SPY regime 或选股条件）：负向 <−2% **122**，正向 >2% **118**，中性 **60**。显示并未集中在单一方向环境；不把这称为正式宏观环境分类。

样本总分 min **31.90** / P5 **42.02** / median **62.06** / P95 **80.58** / max **90.84** / std **12.05**。每项因子与六维分数的完整 describe 分布保存在 [公开汇总证据](../evidence/quant-guided-v1-acceptance-evidence-2026-10-09.json)，私有原始 Q 不提交。

## 3. 采样、身份和真实局限

第一阶段按已知CIK/root security均匀hash取一个窗口；第二阶段使用独立随机域，按hidden layer × year × window cell等额轮转、均匀抽取。记录每阶段条件概率和代表池；Quant层stage2条件于control已抽走后的pool，列`conditional_path_probability`仅是这两项条件概率乘积，**不是全流程联合概率或市场边际IPW**，后续需处理control先抽的生存事件与随机代表池。四个已核验历史cessation/M&A anchors固定保留，未依未来收益选图：旧BBBY、TWTR、ATVI、SPLK。四例是保留能力证据，不是法律退市全总体认证。

全批每 root security/已知 CIK 仅一个窗口，因此同 security 无重叠，名义冷却至少126 session；隐藏重复单独映射。**295/300 样本的跨 ID issuer CIK 尚未核验**，记录 `issuer_known=false`，不按今天 ticker/name 自动拼接。membership unknown=0，不等于 issuer alias 风险=0。未来训练的证券/发行人分组仍需处理该风险，不能将这批宣称为已完全去重的法律发行人总体。

112 样本 READY，188 READY_WITH_MINOR_UNCERTAINTY；6 个样本 T 日 volume=0。继承冻结允许的 probable/非关键成交量缺口，未放松原门禁。成交量代理无信息或可失真时不解释为真实买盘；本阶段保留这种边界图，H 可选不确定。窗口不得伪造行情或成交量。

Quant 尚未获得人工真值，**高召回是设计目标，不是实测召回率**。有前强势+回撤候选、有过度延伸冲突、部分转强和缺陷/普通对照；是否真符合目标由本人判断。Vision 将来在这个有选择偏差的候选分布表现好，不证明完整美股市场同样有效。

## 4. 真实浏览器与回收验收

正式 URL：[项目 7](http://localhost:8123/projects/7/data)。**330 tasks / 0 annotations**。第一批建议50个任务。

最终 smoke：[项目 9](http://localhost:8123/projects/9/data)，10 个不同图片 +1 个隐藏重复，实际11个保存标签。Chrome headless / Playwright，1440×1000；Browser plugin 不可用，按现有 frontend-testing-debugging 技能使用真实 Chrome 备用路径。

全部通过：图片加载、Observe 三种、Entry 四种、Confidence 三种、原因多选、Undo/Redo、Submit、自动下一张、Skip 持久化、Cancel skip 后返回提交、修改 Update、刷新恢复、重复 opaque task 命名。最终页面 JavaScript errors **0**、意外 HTTP errors **0**。保存、修改和导出都由真实 Label Studio API 完成；没有直接向数据库塞标签代替 UI。

smoke-export JSON → 独立 `labels/smoke/labels.parquet` **11 行**；最终服务复测修改增加1个revision，再次导入新增 revision **0**。human 项目全导出 → 严格回收 **0 行**，没有创建 human 真值。重复统计可运行；最终一组机械smoke的Observe相同0/1、Entry相同1/1，只验证统计管线，不是本人的一致性率。

公开只提供浏览器 receipt/hash/尺寸/操作计数。真实截图、浏览器 session、原 task 和标签 JSON 留在被忽略的本地 ready 目录，不上传 GitHub。

本轮实际修复与重试也保留：

1. 发现阶段二错误复用最小 stage1 hash，偏向窗口多的 issuer；修成独立 `stage2` hash，正式目录重新抽样/渲染。初始 Q 核心与冻结数据没有改变，扫描缓存先完整核验再复用。旧预发布目录和项目5/6保留。
2. 原 Django 开发服务在 Windows 出现一次退出以及 export 的 SQLite closed-connection 500；改用单线程 Waitress。第一次 WSGI finder 没有服务 collected hashed jQuery，浏览器发现404；改用 WhiteNoise 实际 STATIC_ROOT 后在新 smoke9 完整重验无错误。发布前连续检查仍出现closed-connection，证明单线程并不足够：最终设SQLite `CONN_MAX_AGE=None`、健康检查，避免每请求关闭连接。延迟响应finalizer是可能原因，未宣称已证明所有内部竞态。重启后20次无重试交替导出成功，再实际打开10独图、修改smoke/保存/刷新恢复，之后另20次无重试导出全部200；正式330任务仍0标签。失败smoke8留存审计，旧项目与文件不变。有限验收不是长期无人值守稳定性保证。
3. 编辑模式侧栏曾遮住选项；保持原 Label Studio，调整为可折行两列/合理最小宽度，实际普通标注和已保存编辑都复查。PNG renderer 未改，不裁首尾。

## 5. 自动化与 Native LEAN

全项目最终命令：`STOCK_RADAR_TEST_LEAN=1 .venv/Scripts/python.exe -m pytest -q --junitxml=data/vision-research/quant-regression-final.xml`。

**674 passed / 0 failed / 0 errors / 0 skipped，86.747 秒（最终JUnit；pytest命令报告87.84秒）**。新增 Quant/H 用例42项；历史基准632项不是本次免测证明。真实 Native LEAN 实际运行 golden nonempty/empty、cancel、PIT none/rename/split/reverse_split/cash、research-grade、decision-scoped reconciliation fixture；不是正式新策略 QC 或收益验证。

测试覆盖未来后缀变动不改变 T 特征、T+1 不进入输入、vendor 常数缩放不改变 Q、raw split 和未来事件隔离、非法/重复窗口、严格 Train/Validation、unknown/unsafe 拒绝、错误 task/image/project/origin/version/choice、漏字段、重复任务、多 annotation、幂等修改、冲突/过期拒绝、单写者锁、原始 revision 不丢、独立随机域、固定 seed 重放与布局迁移不改 label contract。

真实 replay：**300 PNG hash 全相同 /600 raw+normalized window hash 相同 /300 Q 重算一致 /290,909 Q schema检查 /抽样重放 PASS**。本轮未重复读取并重算全部44日 Q scan；replay 在已校验不可变的全扫描 Q 上重做抽样，再从冻结 API 重算并重渲染所有入选窗口。此边界公开记录，不把缓存重放冒称第二次全历史扫描。

warning：既有 `websockets.legacy` deprecation 一项；render 的字体 weight fallback 与常量/零 volume 轴自动扩张。没有为消除 warning 降低 gate。主环境与独立 LS 环境 `pip check` 都通过。

## 6. 隔离、版本与 hash

旧 Pilot **756 files SHA256 全部不变**。原LS项目1：275任务0标签；2：10任务10smoke；3：125任务**5已有标签**；4：10任务10smoke。启动前/结束后逐 task data 和完整 annotations 相同。尤其已有5个 Pair 标签保留，没有按旧报告0标签假定清空。

- infrastructure semantic hash：`74b765911a8a4f18b2074cd8d9e529b25b54afade15309a148b0ca43340b80be`
- renderer：`mplfinance-blind-v2`，960×720；五种 renderer dependency 版本按 bundle receipt 绑定。
- config SHA256：`1d284b2bea787e9b8418d80dfdd9d4ec064a089e2d0ec818c306ffc384b7dd2a`
- generator SHA256：`312cda075e208f4c8032249dc515be68444b007faaf00bc476f7f4928a5a9790`
- sample manifest SHA256：`4d8675035d212cd2c54408a615ee6c324fa7c939c2c8da94033120d62835ad91`
- Q selected SHA256：`2bdbeb272a4edd45b5976d86ee99c556c532f29a576f0e26ce03646d2bc36b18`
- full scanned Q SHA256：`805691dfb103145ae352e4991cc2024094ca9d265b6306a3ae66ff217264ab2b`
- label config canonical SHA256：`186bc6fa75cb95ef759ca356f24c8336d2c2b5c11b1386e1de42e1dbb6954ee3`
- label schema：`quant-human-v1`，origin human/smoke 分离。

其余 artifact/hash、因子分布、测试和浏览器汇总见 [机器证据](../evidence/quant-guided-v1-acceptance-evidence-2026-10-09.json)。源数据 read-only 前后 hash 不变；Strategy2 冻结参数、Research Infrastructure v1 语义与旧Pilot未修改。

## 7. 完成与下一阶段

**发布状态：PR [#7](https://github.com/zhoushuming073-cell/stock-radar/pull/7) 为草稿，尚未合并。** 本轮从同步的main `6b6e6fa`开始；期间main新增`0d98a9c`，将主线改为[未来结果监督 v2](../../docs/PRICE_STRUCTURE_OUTCOME_LEARNING_PLAN.md)，与本轮明确的人类标注任务不同。实现与数据验收已完成；研究主线定位及文档冲突需由用户确认后再合并，不覆盖并发更新。本轮未开始任一种训练。

已完成：真实 Quant/Q/X、五层样本与300PNG、独立人类项目、标签合同/回收、浏览器10独图、旧成果隔离、完整回归和真实Nativefixtures、公开安全汇总/说明书。

尚未完成且本轮不实施：本人新批次实际标注、Vision M1、Fusion、Y计算、formal QC验证、issuer全局alias认证、完整市场coverage/recall证明、主站内嵌标注。现阶段主站不重写，LS是同一研究合同的独立操作入口。

下一阶段门槛：本人先标约50任务并审查问题语义；后续足够Train/Validation H、真实重复检查、issuer分组风险处理、冻结 X/Q/H/renderer/评估计划、明确用户授权。**到 Human Labeling READY 即停止。**
