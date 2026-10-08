# Shape Research Layer v1

当前研究主入口和 Fresh 修正以 [Research Infrastructure v1](RESEARCH_INFRASTRUCTURE_V1.md) 为准；原 core、来源锁及历史统计保留。

这是一套独立、显式调用的本地研究数据层。严格 HistoricalDatabase、accepted raw、Security Master、Scanner 默认数据源、Web UI、日更、Native LEAN 和 QC 验证状态保持原样。Shape READY 不会自动释放正式投资组合 Run。

目标是可以使用的历史 K 线窗口，而非供应商级身份档案。General PIT Tier 1 与 Shape Research READY 可以并存。未来收益、QC 选股结果、当前公司是否存活不参与窗口通过判定。

## 构建与证据

```powershell
.\.venv\Scripts\python.exe -B scripts/build_shape_research.py --root .
.\.venv\Scripts\python.exe -B scripts/audit_shape_research.py --root .
```

输入：最新 `data/pit/construction/current.json` 指向的历史数据库、原 PIT OHLCV store、固定 Dolt 原始行情、原冻结 `config/research.yaml`、新的 `config/shape_research_rules.json`。全部源数据库以 READ_ONLY 挂载；输入构建前后 SHA256 一致才发布新 manifest。独立指针 `data/pit/shape-research/current.json` 不替换严格层指针。版本由代码、规则、输入散列决定；失败输出没有 manifest，不可加载。

本地数据库和原始行情不进入 Git。Git 只保留代码、规则、汇总统计、规范化图像与散列证据。原源授权没有因为衍生分类而改变。

| 表 | 粒度与职责 |
| --- | --- |
| population | 历史被观测的普通股 ID/session，unknown 保持未知 |
| shape_price | ID/session/source/basis 的 OHLCV、状态、原因、核验时间、源文件散列 |
| session_assessment | ID/session，至少一个同口径来源能通过则记录通过；缺失独立保留 |
| split_action / invalid_split_action | 已安装事件和异常事件，不创建新法律认证 |
| shape_review_queue | 只保留会污染图形的发行人、类别、拆股、重大跳变、重大来源冲突等 |
| universe_window_index | 20/40/60/126 个完整连续 session 的研究 Universe，不受训练区间限制 |
| visual_window_index | 进一步要求整个输入落在同一个冻结区间，含 split_assignment |

## 状态与自动判定

READY：OHLCV 合法、历史区间合理、连续、没有被检测的重大冲突。READY_WITH_MINOR_UNCERTAINTY：允许 probable/unknown 成员证据、零成交量或成交量异常警告、未经官方单独认证但价格关系相符的拆股事件等非关键缺口。两个状态均表示技术上的窗口 K 线可用；默认 Universe 还要求窗口内所有 session 都是 confirmed/probable。

QUARANTINED：非法 OHLCV、已知上市/退出边界违反、日期内发行人碰撞/TTGT 核验边界、类别/名称切换边界、不可解释重大跳空或日内跨度、疑似未解决拆股、异常事件比例、影响形态的来源分歧、未知调整口径、缺交易日。MISSING：确实没有绑定 OHLCV。一次异常只影响包含异常的窗口，不整只永久拉黑。

先做证券区间绑定，禁止跨 ID 拼接。原 Master 的多个短观察片段不会被当成已证实的法律 ticker reuse；不同 ID 永不合并。第二个不同 CIK 的已知日期起隔离，TTGT 按已有独立注释隔离；使用当时的 ticker/date。并未完成全部真实发行人认证。

普通长期稳定证券自动通过，不需要逐只检索 SEC。Master 中的 full-window A/B/C、后来的消失标记、未完成 merger/no-event 档案不作为历史选择门槛。类别/名称转换的边界行被隔离，后续窗口需要重新积累完整历史。

缺失交易日不能被补成假 K 线，完整窗口不跨缺口。缺口本身不扩大 AI 人工队列；实际持仓/候选遇到生命周期异常，仍走既有严格核验流程。当前 review_queue 是按源/日期记录的 material finding，同一 ID 可以出现多行，不等于要人工调查数万只股票。

## 拆股与未来尺度

来源不混合：一个窗口使用一个 ID、一个源系列和一种 basis。legacy split 系列不再复权；raw 在生成窗口时只使用 effective_date <= T 的安装拆股因子，将窗口过去部分转换到 T 的股数口径。已知 raw 拆股对跳空检验做一次价格比例修正；已复权 series 不重复修正。

拆股来源候选有效日期和比例可以支撑形态纠错，并不证明当年的公告发布时间已被精确记录。缺 known_on 的候选不被解释为严格供应商 publication-PIT。

split-only vendor 历史价格可能因 T 之后拆股乘上一个常数，历史成交量也可能乘上一个独立常数。模型输入价格除以窗口首个 close，成交量除以本窗口最大成交量，这些常数被消掉。测试验证尺度不影响规范化样本。**绝对复权价格、绝对成交量、美元交易额和持仓财富不能由这种规范化恢复成严格 PIT。** 不将它们用来悄悄替换 Strategy 2 原最低股价/流动性或执行门槛。

来源比较检查 close/open、high/low 以及已知拆股修正后的相邻收益比例；忽略可由复权常数解释的绝对价格差。仍不一致的两边共同隔离，不按哪个源收益更好选赢家。gross anomaly 阈值在规则中固定；没有利用收益或 QC 结果调阈值。全量数据中的极端真实事件也可能被保守隔离，这属于可调查范围。

## 研究接口与现有代码耦合

```python
from radar.pit.shape import tensor, render_svg
from radar.research.infrastructure import shape_research_universe_v1

with shape_research_universe_v1(root) as db:
    universe = db.universe_on("2026-09-14", length=126)
    # 普通历史 OHLCV，字段 date/symbol/open/high/low/close/volume/basis/source。
    w = db.window("SEC-0001045810-COMMON", "2026-09-14", 126)
    x = tensor(w.normalized)  # 126 x 5；不含标注、名称、ticker、退出状态。
    svg = render_svg(w.normalized)
    features = db.feature_window("SEC-0001045810-COMMON", "2026-09-14")
    # 从现有 compute_base_features / compute_strategy2_features 复用原公式，
    # 保持原参数和 (date,symbol) 索引；调用前基准数据截断 <= T；新主入口拒绝未来基准行，无 forward fill。
    s2 = db.strategy2_feature_window(security_id, T, spy_close, qqq_close)
```

上述 NVDA 实际窗口属于 Test，只用于读取/检查示例，不能用于模型拟合。Train 示例见下方 BBBY exporter；有质量异常的具体日期/长度会拒绝返回窗口，不能因为 ticker 常见而绕过判定。

`strategy2_feature_window` 提供原规则所用的尺度不变形态因素，不造单股横截面 Elasticity 排名、绝对价格门槛、美元成交额或完整策略绩效。Scanner/Strategy 2 的显式研究适配器可消费这些因素和 `universe_on`；现有 production 默认入口没有改变。未来进行完整 exploratory 策略回测时，要显式接入同日排名和适当的原始价/候选生命周期模块。Shape 标准足以恢复形态/因素研究，不是全市场财富曲线的免检证明。

feature_window 与 universe_on 支持非训练区间日期。visual window 默认要求数据切分隔离；需要普通研究窗口时可以显式 `dataset=False`，但 split_assignment 为空的窗口不能调用 training_tensor。

## 可复现视觉样本

```powershell
.\.venv\Scripts\python.exe -B scripts/export_shape_window.py --root . --security-id SEC-0000886158-COMMON --decision-date 2023-02-03 --length 126
```

输出在被 Git 忽略的本地 `data/pit/shape-research/samples/<sample key>/`：标准 OHLCV parquet、规范化 parquet、五通道 `<f8` tensor.npy、确定性 candles.svg（K 线+成交量面板）、metadata.json。sample key 包含 ID/date/length/source/basis/dataset/split/OHLCV hash，避免不同证券出现相同数字图形时覆盖身份绑定。先保存数字窗口，图片是可替换 renderer 的衍生输出。本轮不生成海量图片，也不训练模型。

metadata 保留内部 ID、当时 ticker、decision date、window start/end、OHLCV hash、normalized hash、source hash、basis、membership、shape 状态、dataset version、split_assignment。metadata 和目标标签不进入 tensor。标准 SVG 没有公司名称、当前 ticker、后来的状态、收益目标、字体依赖或生成时间；同输入逐字节一致。CNN/ViT 以后可以冻结自己的 raster renderer 配置。

## 时间切分与评估隔离

沿用 research-splits-v1 的原 signal 日期：Train 2021-09-01–2024-08-29；Validation 2024-09-30–2025-09-08；Test 2025-09-23–2026-09-14。原十 session forward-label embargo/evaluation end 保留。输入窗口必须完全在对应 signal 区间；跨区间窗口不借之前 Train 的 K 线作为 Validation/Test 输入，因此相邻窗口不会随机分配到不同 split。

2026-10-08 收口修正：Fresh OOS 决策从 2026-09-29 开始，允许使用该日前已经发生的 lookback；仍禁止决策之后的输入。固定 core 的旧 visual index 保留原完整区间规则，新主入口通过只读取已有本地行情的 sidecar 提供 20/40/60/126 session Fresh 决策窗口 34,491 /33,745 /32,979 /30,462。正式评估仍需真实 pre-F 模型/参数冻结回执；本轮没有声称这类记录存在，没有策略 Fresh 收益评估。不能将旧 Test 重新命名；现在冻结的新模型需后续新的决策期。`training_tensor` / `assert_training_split` 只接受 Train；Validation/Test 用于各自冻结流程，不用于拟合。API 无法替用户阻止外部训练程序滥用，所以训练入口仍应调用该 guard。

同一 split 内窗口大量重叠，不是独立观测数。统计检验按时间/证券分组，不能把上百万窗口当成上百万独立试验。现有项目已看过的 Test 仍是 exploratory；本次冻结数据层不能让它重新变成从未看过的 OOS。

## Missingness 与职责

readiness 指标分母是已观测普通股 ID/session，不是完整美国股票市场。保留后来退出证券和所有未知/缺价行；覆盖与形态质量分开统计。全量 disappeared IDs 含保守切片和疑似退出，不能直接叫真实退市名单。支持 unknown include/exclude 的实际窗口数量敏感性；未跑策略，所以没有捏造收益敏感性。

达到 Shape 标准后停止供应商级主动扩建：只对真实候选/持仓异常、研究所需缺失区间、日更和定期 QA 做维护。日更更新源库后，旧 Shape 快照仍可读；要显式重建新版本才能采用新行情。没有另建后台计划任务。

本地负责规则/形态研究、图表、视觉样本、参数探索、候选分析和 exploratory 回测。QC 后续对冻结规则使用自己的历史 Universe、Security Master、行情和 LEAN 独立重跑；视觉初期验证冻结信号的组合执行，成熟后可考虑冻结模型+QC 数据独立推理。本轮没有 QC 数据导出、Cloud 回测、策略调参或模型训练。
