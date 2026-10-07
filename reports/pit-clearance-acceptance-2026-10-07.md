# Stock Radar PIT 数据清障验收 · 2026-10-07

**Engineering complete; formal PIT execution remains data-blocked。** 本轮完成 IREN 的有证据身份合并、独立 feature 重建和安装、全量无价源探测、身份候选分层、事件源调查及正式请求重算。没有把下载成功、同代码记录或空事件表升级成认证。RESEARCH-03 保持 OPEN。

本轮重新读取 GitHub main，基线为 `ea937e5bd70b872c3143a8502ff3234a658f584e`，与本地一致。先前三份验收原样保留。本轮正式请求在提交前运行，metadata 如实记录该基线、dirty 状态和源文件物理 hashes；没有回写 Git 身份。

## 1. 十二个问题的直接回答

| 问题 | 本轮结果 |
| --- | --- |
| 开始缺多少价格？ | 435,803 / 2,023,561 required records |
| 最后还缺多少？ | **435,678 / 2,023,436**，coverage **78.468407%** |
| 开始多少 identity blocked？ | 6,418，Run 共 6,422 个依赖身份 |
| 最后还剩多少？ | **6,416**，Run 共 **6,421** 个依赖身份 |
| CorporateAction coverage 提升多少？ | 完整 required-scope coverage 认证仍 **0**；缺声明 6,422→6,421 是身份去重，非认证提升。已有 15 个事件未增加。 |
| Membership 是否真正解决？ | **否**。允许强的 Run 范围多源认证，七项证据未齐；没有要求全球全库完美，也没有删 gate。 |
| 哪些新来源被接受？ | IREN issuer 2025/2026 10-K、2025-05-14 6-K 接受为身份连续性证据。新增 accepted price rows **0**，新增 action events **0**。 |
| 哪些被 quarantine？ | Dolt 缺价探测 2,461 bars；split/dividend 发现数据；二级 CIK/rename 候选。其他源因日期范围、订阅、许可/身份/口径不足，未进入接受库。 |
| 是否获得正式 PIT Native Run？ | **否**。新请求 `b4483d79-adac-4845-b28c-ebf9605ca5cb` 在 preflight BLOCKED，native/reconciliation 均 NOT_RUN。 |
| 唯一剩余硬阻塞是什么？ | **并非只剩一个**：人口完整性、6,416 个历史身份、435,678 条缺价及全部所需价格/事件范围认证仍独立阻塞。最上游结构性缺口是历史人口与稳定证券身份/完整事件来源证据。 |
| 免费/开源还能不能继续解决？ | 能继续局部增补。已测试来源不能完成当前全人口闭环；没有证明互联网不存在任何其他资料，也不把所有缺口宣称必须付费。下文给出已验证来源边界。 |
| Current vs PIT 能否比较收益？ | **不能**。保留 Current 原生 -6.57782093539% 对照；PIT 组合收益、订单、交易、费用、回撤等仍 null。 |

缺价减少 **125** 来自 IREN 两个错误 episode 合并后，重复预热依赖去重、既有价格归属连续化；**没有新增 OHLCV，也没有缩小每日 Scanner population**。它不是补入 125 条新行情。完全无价仍 1,138；部分缺价 1,177→1,176。

## 2. IREN 修复与数据耦合

旧 episode `OBS-449bb6f3aa23209884239c73` 与 `OBS-626ad46887c682e17d3cf605` 因 screener 公司名称改变被拆开。官方 [2025 10-K](https://iren.gcs-web.com/node/11431/html) 的上市说明支持持续 Nasdaq 普通股身份；[2025-05-14 6-K](https://irisenergy.gcs-web.com/static-files/b57c7e75-2dbe-4916-8d16-d5657d3712f8) note 1 明确公司在 2024-11-28 更名；[2026 10-K](https://iren.gcs-web.com/node/12566/html) 为同一 CIK 的普通股披露。上市普通股与 B Class 分开，ticker 未变。此次不是两个不同证券加随机 SID 后缀。

两个 observation intervals 保留原日期，统一为 `SEC-0001878848-ORDINARY`。没有把 screener 2024-12-07 名称更新时间当成法律生效日，没有由 observation 推定 IPO/法律退市。

| Artifact | 安装后的值 |
| --- | --- |
| Master version | `533905312e4c19ef2f80558d80c06c1b644f3eefc01fbba0c703904f1dc8bdaa` |
| Master CSV SHA | `5e6985a5d4a756061cdc2dba3ad27055e7b7beeb1491e11690d5dbe7621ac6c9` |
| Feature DB SHA | `9c39a9f99c8fb1985b40c797a74f41dd6073872243b26584c8401347115a00ff` |
| Feature rows / identities | 5,472,884 / 7,657；行数不变，两个 IREN 身份变一个 |
| Verified master intervals | 17→19；unresolved 90,322→90,320 |

独立重建使用既有 feature 公式、研究配置和 broker snapshot；既有 ATVI/TWTR/SPLK 1,462 bars 在新 master 下重新验证接受。新旧 DB 的 `symbol/date/OHLCV/provider/feed/adjustment/downloaded_at` 等源行情列 SQL 双向差集 **0**。非 IREN 的全部未做横截面评分 feature 列双向差集 **0**。IREN 连续历史改变横截面评分，这是允许的数据变化。

安装前确认没有 queued/running/cancel_requested Scanner/Backtest jobs。三个安装入口文件备份至本地 `data/pit/install-history/clearance-509fe269…/`；旧 master、feature DB、external DB 保留。market、frozen research v2、phase2 research、source snapshot 四个旧 DB 的物理 hashes 全部不变。

## 3. 正式重算与门禁

冻结计划 `config/pit_final_run_plan.json` 未变，SHA `6b1336a9bdfa9438471e057460ade0d945f57e8ae9736b5ecca80fb6667c8fcb`。策略 `full_strategy2_v1@1.0.0`，signal 2024-09-30–2025-09-08，evaluation 2025-09-22。strategy/config/fee/slippage/execution policy/window/LEAN identity 与上次请求逐项相同。没有改 score、rank、阈值、退出、每日 intake 或 MarketGuard。

新 Scanner `8583b0e6-cc9b-497c-9ddc-b2355821ea13` completed，235/235。候选 4,177→4,176：新增 3 条 IREN，移除 4 条其他证券；没有依据收益选择窗口。Current 6,981 候选对照仍保留。

新正式 PIT 请求 `b4483d79-adac-4845-b28c-ebf9605ca5cb`，闭包 semantic SHA **`2538efd79fdc64f5479f4345256f4d077e709d475c84a0452be9baa87256febf`**，文件 SHA `cf9ae48ad8511280b8b245fc5aca7a15411b6f11c1cc82f6181adab707a08dbf`。这是真实 queue preparation 重读安装价格/人口计算的完整闭包；随后 inventory 重验物理 locks、重算 readiness，结果相同。

| Gate | 结果 / reason 数 |
| --- | --- |
| Identity | FAIL / 6,416 |
| Membership | FAIL / 1 |
| Price | FAIL / 14,020；reason 数不等于缺价条数或证券数 |
| CorporateAction | FAIL / 6,421 |
| Terminal | PASS / 0 个已知未处理 terminal；不证明未知事件不存在 |
| LEAN Input | FAIL / 1 个 upstream inputs 未就绪；独立 IREN collision 已消除 |
| Native / Reconciliation | NOT_RUN / NOT_RUN |

最终逐证券清单为本地 `data/pit/clearance/iteration-1/blocker-inventory.json`；每行有映射、required range、缺失 dates、身份/类型/membership/action/terminal 状态、reuse/rename 风险、许可/价格口径、源候选及 gate reasons。全部尚有不可放行缺陷，所以主优先级均 P0；另设 P1 本地证据可恢复、P2 需额外 certification 的 recovery priority。不是输出几万条无聚合 reason 代替清单。

新闭包的 ResolutionQueue 已完成 **6,421 / 6,421** 个本地证据 assessment，全部仍 blocked，pending/running/accepted 均 0。每份 outcome 的 canonical hash 与 append-only attempt event 核对一致。它记录的是未满足认证条件的决定，不是补入数据的进度；IREN 接受、重建、重算、新队列构成一次真实 before/after 迭代，旧 Run 与旧依赖记录保留。没有让同一份不足证据无限重试。

## 4. 完全无价、身份分层与部分缺口

对全部 **1,138** 个无价身份，按固定 Dolt commit 查询 946 个不同代码的 metadata，并只探测每个身份三个实际缺失标签。得到 942 个 symbol records、2,461 个样本 bars；**1,052 个身份至少一个样本有价**。119 个分批 SQL 查询没有失败或截断；最初全 symbol 表查询返回截断状态，单独拒绝并保留。

每个无价身份都已归类：1,137 `identity-unresolved`；已认证 BYON/新 BBBY 身份 1 个 `recoverable-via-known-source`，仅代表部分恢复路径存在。86 个抽样无价不能推定整段无价或退市。本轮没有据名称判断 `non-common`，没有因找不到行情把证券删掉。

全缺口本地 broker 检查发现 82,483→82,358 个同代码/日期候选。它们涉及 episode 预热、映射边界及身份隔离；只是可发现的源记录，不能 ticker-only 安装。

固定二级 reference commit `a3eb36f951f9796c60c0a4c6bb70f13e50d9da6b` 的批量候选层：A 2,451、B 171、C 1、D 1、E 1,848、F 1,950；G/H 当前没有检索到相应候选。CIK 统一零填充，避免把同一 CIK 的格式差异当成冲突。此分层使用**任务起点 6,422 个身份**；A/B 仍是 undated secondary 候选，没有历史 share class/date 来源认证，不自动变 verified。C/D 已有局部官方证据。最终已认证依赖身份 5 个；其他保持未认证。

BYON/新 BBBY 既有 quarantine 数据为 354+5=359 个 sessions，required 为 360。缺 **2025-08-29**。对同一固定 commit 在 BYON、BBBY 下查询该日均返回空；本地两个 broker 库也没有 BYON/BBBY/OSTK 行情。BBBY 源还混有旧发行人的 2016–2020 dividends、2025-10-02 split：必须按两个 issuer/date 范围隔离，不能整表绑定同一 identity。359 bars 未被伪装成完整接受，不填最后 close 或换代码 alias。

Resolution worker 已改为逐 mapping 只下载 `missing_sessions`；完整价格证券不下载 OHLCV，缺口在 reviewed symbol intervals 之外时阻止 alias 查询。严格 raw gap merge 审核函数拒绝 adjusted 混用、重叠/冲突、缺日、身份错配、源行变化；本轮 broker split basis 尚未满足其接受条件，没有实际 gap fill 安装。

## 5. Membership policy 与完整行动覆盖

Membership 允许官方完整人口声明，或 `pit-formal-membership-v1` 的强多源 Run 认证：绑定完整 population hash、日期、版本/raw hashes、独立来源、reviewer logic，以及七项逐项有说明和证据的检查。当前 source 的窗口内 245 个快照均接受，数量范围 6,817–7,049，无已检测的大异常；这些结构检查不能证明 NASDAQ Screener 没有较小遗漏。

| 检查 | 当前可支持的边界 |
| --- | --- |
| snapshot continuity | 有连续观察、availability timestamp 和 carry 约束；不能证明每日 exhaustive population |
| exchange coverage | NASDAQ/NYSE/AMEX 过滤已知；缺独立历史完整目录核对 |
| carry policy | 最多四个 calendar days，失败 snapshot 不 carry；保留源代码/raw hashes |
| source anomalies | 大异常检查通过；较小遗漏及名称 episode 误拆仍可能存在 |
| future listing exclusion | dated observations 有约束；多数真实上市日期未知，不能把观察开始当 IPO |
| disappeared securities | observation disappearance 与法律退市分开；没有完整退出事件覆盖 |
| classification boundary | 大量 inferred common、unknown/ineligible，缺历史 native instrument flags/class 认证 |

**Membership remains structurally blocked by source completeness。** 两份同源转载不能当独立多源证明；2026 的当前目录也不能回溯证明 2024–2025。

批量行动调查取得固定 Dolt scope 内 842 个 split symbols、6,631 个 dividend symbols。与起点代码匹配，642/2,250 个 formal IDs 有对应候选；这是宽窗口发现，尚非逐身份/日期接受。NVDA、META、SPY、QQQ 存在 dividend candidates，不能把 split-only review 当成事件完整性证明。通用 dividend native accounting 仍未支持。

新增 `no_material_action_review` 校验：身份、review 起止、sources/versions/raw hashes、完整源覆盖、event types、reviewer logic 必须齐全，且与已知事件不冲突。空结果、仅 split/dividend endpoint 或变更的源 hash 均拒绝。**本轮没有生成任何虚假的无事件认证。**

## 6. Free/Open PIT Completion Boundary

这里的边界是：**已尝试且可核查的来源不足以完成这个固定窗口**，不是数学上证明所有免费资料永远不存在。仍有 6,421 个依赖、435,678 缺价、6,416 未认证身份、6,421 未审核完整 action scopes；另有基准价格/事件口径认证缺陷。剩余逐 ID/逐日清单在本地 inventory，公开交付 hashes 与聚合证据。

| 来源 / 版本 | 实际尝试及决定 |
| --- | --- |
| [Dolt stocks](https://www.dolthub.com/repositories/post-no-preference/stocks)，`vt6qeesk27k07492k5jc5b7p04mf0s6o`，CC-BY-SA-4.0 | 实际缺价 SQL、metadata、split/dividend 分页和单日 rename gap probe。具备不少价格；缺稳定历史身份、完整事件类型/完整性及某些 sessions。发现数据 quarantine。 |
| [rreichel3 snapshots](https://github.com/rreichel3/US-Stock-Symbols)，`157439344501b2020cc2ae37addd6f628fa00699` | 重读本地 snapshot audit；continuity 不等于 exhaustive population；license 未核清，不重新分发 raw。 |
| [Quant-Lodge reference](https://github.com/Quant-Lodge/ticker-reference-data)，`a3eb36f951f9796c60c0a4c6bb70f13e50d9da6b` | 实际读取 CIK/rename 文件并对所有依赖分层；缺历史 class/date 认证、许可未核清。 |
| [YLiu95 delisted](https://github.com/YLiu95/delisted-equity-data)，`37b4198b6c5cc4a4354aad6f71c2aeac631703b2` | 保留 secondary discovery；没有升级为官方事件或有许可完整价格。 |
| [Stock-Data](https://github.com/TylerJForstrom/Stock-Data/tree/a9ef6bf27e48899409ebf0712c61422081a7f457)，`a9ef6bf27e48899409ebf0712c61422081a7f457` | 实际固定 README/PIT manifest，`reconstructable_from=2026-07-28`，拒绝回溯本次 2024–2025。XBRL dividends 为财政期数据，非每日 ex-date 完整源。其许可说明是 publisher claim，本轮不采用为转售许可结论。 |
| [Nasdaq Daily List](https://classic.nasdaqtrader.com/Trader.aspx?id=DailyListPD) | 官方说明实际捕获：Monthly Subscription/Login；不是已获免费全期事件库。 |
| [NYSE official sample directory](https://ftp.nyse.com/Corporate%20Actions%20Data%20Samples/CORPORATE%20ACTIONS%20OF%20NYSE%20GROUP%20LISTINGS/) | 实际捕获目录：有 2025-01-02/03 corporate-action 样本等，不能覆盖完整窗口；历史 [MEF](https://www.nyse.com/market-data/corporate-actions/market-event-feed) 是产品接口。 |
| [MarketParquet documentation](https://marketparquet.com/documentation) | 实际捕获说明：免费为 recent daily sample，完整历史需购买；stocks split-adjusted，不能直接当 raw。未下载与 Run 无关的大包。 |
| [Alpha Vantage docs](https://www.alphavantage.co/documentation/) | 文档评估；没有可用研究数据授权/key，也没有实际采集正式依赖，不能把 demo/近期接口当完整历史接受。 |
| Stooq / Yahoo | 文档/入口检查分别遇 browser verification、999；未绕过访问控制。许可和 historical alias/basis 未核清，没有接受行情。 |
| [Wayback scraper](https://github.com/Acelogic/WayBackMachineStockScraper)、[delist-detection](https://github.com/royelee/delist-detection) | 研究代码/说明；没有执行抓取或接受其价格/分类。前者旧 Yahoo 档案恢复和拼接不证明本期许可/identity，后者分类工具不证明全人口事件完整性。 |
| IREN issuer documents | 三个 SHA-bound 官方文档用于接受身份，未声明为全股票价格或事件完整源。 |

需要补充的供应商能力是：本期完整历史 exchange/instrument universe、永久证券/issuer/class IDs 与 dated mappings、active+inactive 的 raw OHLCV、原始 adjustment factors、带有效日和披露/记录时间的 split/dividend/rename/transfer/merger/delist/cash terms，以及本地研究许可。购买产品也仍需逐 Run 校验，并不自动 PASS。本轮没有购买或注册服务。

没有声称一个更短或不同窗口已经能正式 PASS。公开新目录起点较晚，且仍缺 action/execution 证明；没有按收益挑备选窗口，没有调整当前 population。可以继续新增明确可认证的来源；在上述证据没有变化时重复跑 blocked worker 不会改善 readiness。

## 7. 验证与交付

397 tests passed，native opt-in，73.85s，1 个既有 websockets deprecation warning。新增 20 项用例覆盖有证据批量身份合并/冲突、raw gap fill 与拒绝、源 mutation、无重大行动证据、完整七项 membership policy、100% price gate、IREN root 修复、队列新旧 dependency 迭代、完整价格 worker 不下载。所有 fixture PASS 都明确不是第一份真实正式 PIT PASS。

8766 的新进程验证 `/health`、universe status、PIT readiness、正式 blocked Run 详情、Current completed history 均 HTTP 200。正式 8765 原进程保留；此前自动审批拒绝停止/启动服务，返回原因仅为 `blocked by policy`，本轮未强行终止，也没有把服务重启问题计入数据 gate：**code installed, production local API restart pending user/local shell**。临时验证服务已停止，端口检查仅有 8765 仍监听。

机器证据：[pit-clearance-evidence-2026-10-07.json](pit-clearance-evidence-2026-10-07.json)。完整本地 source/query/queue/安装记录在 `data/pit/clearance/` 和 `data/pit/raw/clearance*`；不上传行情或大型 DB。状态及剩余工作只归入 [唯一当前总账 §3.2](journey-2026-09-30-0651-📌当前总账.md)。正式 PIT portfolio、Current/PIT 收益差和 Fresh OOS 结论都没有生成。
