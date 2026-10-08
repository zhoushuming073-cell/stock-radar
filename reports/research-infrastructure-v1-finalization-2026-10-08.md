# Stock Radar 本地数据库最终收口 — 2026-10-08

状态：**RESEARCH_INFRASTRUCTURE_V1_FROZEN**。General PIT = Tier 1（deep/audit）；Shape Research = READY；Database expansion = CLOSED；Database maintenance = ACTIVE；Strategy Research = READY TO RESUME；新的 Formal frozen-strategy QC validation = NOT_RUN。

保留用于研究的历史 K 线、成员证据、身份/拆股隔离、退市样本、原始来源和严格审计记录。冻结统一研究入口，修正 Fresh 决策回看。一个旧快照进入冷存储；实际删除为零。本地用于高效规则/特征/视觉研究，下一步回归策略研究。数据收口不能证明 Strategy 2 有效或消除全部幸存者偏差。

起点先 fetch / fast-forward 核实为 `168368de255501de6b45237037f52c3eaa1ea582`，当时工作树干净；提交前再次 fetch，远端未前进。本轮使用实际源文件和 SQL 复算，不套用上一轮数字。

证据：[资产清单](evidence/database-asset-inventory-2026-10-08.json)、[清理计划](database-cleanup-plan-2026-10-08.md)、[清理回执](evidence/database-cleanup-results-2026-10-08.json)、[schema 清单](evidence/database-schema-cleanup-manifest.json)、[代码引用补充](evidence/database-code-cleanup-manifest-2026-10-08.json)、[数据复算](evidence/research-infrastructure-finalization-2026-10-08.json)、[实际接口与导出](evidence/research-infrastructure-integration-2026-10-08.json)、[测试](evidence/research-infrastructure-tests-2026-10-08.json)、[运行合同](../docs/RESEARCH_INFRASTRUCTURE_V1.md)。

## A. 清理：1–10

**1.** 主要遗留包括未发布 construction 失败库、未发布 Shape 大库/WAL/spill、重复已发布 Shape 快照、旧全市场重建与清障证据、源 adapter/一次性修复脚本、原始网页/交易所/SEC/Dolt 数据，以及 LEAN/历史 Run bundles。清单逐文件记录 22,032 项；代码补充 219 项，schema 6,888 个对象。分类审查后 A 2,289 /B 15,587 /C 4,142 /D 6 /E 8。

**2.** ACTIVE core、current membership/identity/split、market 日更库、phase2 研究/冻结/源快照、strict accepted raw、已恢复 BBBY 与 ATVI/TWTR/SPLK、QC smoke PASS 回执、Git 历史报告、唯一原始数据和用户上传均保留。已锁 raw 目录保持原路径并作为 cold source，防止移动破坏复现。

**3.** 旧 Shape 版本 `25137ad2123ffc57cc7873dcd0dab5307152e61f036d39b12900b4c3315c507e` 整体移入 `archive/legacy-pit/shape-25137.../`，3 文件、4,758,857,898 bytes。目标散列逐项等于清理前；独立 archive README 和忽略规则禁止自动运行/提交大库。

**4.** 实际删除 0 文件、0 表、0 view、0 脚本；没有将政策阻止写成清理成功。

**5.** 可删除候选限于无 published manifest/current 指针、无 exact external consumer、源仍保留且可以重建的失败/临时产物。第一个确切删除被策略阻止后，保留同族和此前受阻文件。

**6.** 先检索 Git tracked Python/SQL/测试/notebook/docs/配置，再纳入本地 generated manifests/current/source-lock/receipt，记录路径/版本匹配和 basename 提示；动态/模糊引用一律 REVIEW_KEEP。归档版本仅自己的 manifest 有引用，外部 consumer 为空。策略/Scanner/特征/视觉/web/日更/LEAN 源代码补充逐项列 consumer。

**7.** 删除文件/表/view/脚本均 0，归档文件 3；脚本归档 0。旧 audit 脚本因报告、测试或物理代码锁保留显式路径，不加入主 CLI/运行自动路径；不能证明无 consumer 的代码没有删。

**8.** 实际释放磁盘 0 bytes。data 目录缩小主要是约 4.759 GB 转入 archive，未减少总磁盘占用；新增 sidecar 为 50,868,224 bytes，清单/回执也占空间。以下为逻辑文件长度，含 .git/.venv，不是分配簇占用。

**9.** 14 个 blocked/同族保留文件共 9,053,898,264 bytes；本轮拒绝的是 `data/pit/construction/versions/32b31d12.../historical.duckdb`（360,984,576 bytes），返回 `blocked by policy`。另外 4 个同族 construction 文件不再尝试；此前 9 个 Shape/WAL/spill 不重试。完整路径/大小/原因/desired action 在回执。

**10.** 这些未发布产物无运行 current 指针；API 按冻结 manifest/目录读取，不递归挑选数据库，因而不会污染运行。archive 也不参与 package imports、pytest testpaths、Scanner、日更或 LEAN。

| 规模 bytes | 清理前 | 后测量点 |
| --- | ---: | ---: |
| repo_bytes | 63,599,064,859 | 63,655,705,808 |
| data_bytes | 63,188,178,186 | 58,429,383,190 |
| archive_bytes | 0 | 4,758,858,696 |
| active_research_database_bytes | 4,757,401,600 | 4,757,401,600 |
| temp_cache_bytes | 3,088,308,038 | 3,088,308,038 |
| fresh_sidecar_bytes | 0 | 50,868,224 |

测量点：2026-10-08T09:35:03.897036+00:00，在最终回执/报告和 Git commit 前；随后文档、Git objects 会增加少量体积，未因此声称释放空间。

## B. Active Database：11–18

**11.** 合并 current core 与已有本地日行情 Fresh sidecar：5,811,586 /6,929,009 observed common ID/session = **83.8733%** 技术 ready。core 本身仍 5,775,762 /83.3562%，字节未变。增加 35,824 个 ready session 仅来自已经在本机的 post-F 行情，不是新增市场下载。

**12.** 默认 confirmed/probable 安全 K 线 **5,407,961**，unknown 默认不纳入且保持未知。available 5,832,812 /84.1796%；MISSING 1,096,197 /15.8204%。这些百分比不是全美市场完整率。

**13.** 全历史任何 safe candle 的 ID 共 8,823；默认 supported 安全 candle ID 8,773。最后决策日 2026-10-07 的 supported 20/40/60/126 Universe 分别 4,876 /4,774 /4,661 /4,321；不要把全历史 ID 数当作当前同时上市数。

**14.** 下面分别列完整研究窗口（不要求整个输入在训练区间）及隔离后的 visual split 窗口。计数是 ID/决策日/长度组合，窗口重叠，不是独立样本数。

**15.** 共 QUARANTINED 21,226 /0.3063% session；Fresh 36,136 候选中 312 行隔离，历史同源 bridge 修订冲突 ID 5。保留不合法/身份/边界/拆股/极端跳变/来源冲突原因；没有因缺口伪造 K 线。

**16.** 固定 ID 与 dated ticker episode 绑定，不拼接前后不同 issuer 或 ID；已知碰撞、TTGT 和类别转换边界隔离。core ready identity_conflict = 0，Fresh ready identity_conflict = 0；这不是全市场法律级 identity 认证。

**17.** raw effective<=T 拆股因子仅应用一次，split 系列不重复复权，无法解释的跳变隔离。core ready suspected/invalid split = 0，Fresh ready extreme gap = 0；拆股候选的公告发布时间和绝对执行价 PIT 完整性仍有限。

**18.** 实际 SQL 检查 core future/identity/split、Fresh boundary/identity/extreme/bridge ready 违规均 0；22 个新增测试覆盖未来 bars、benchmark、标签/未来 metadata、冻结与训练污染。future labels 不进 tensor。未声称绝对价格或所有第三方 source publication time 都达到供应商级 PIT。

| 长度 | 研究窗口 supported | 显式含 unknown |
| --- | ---: | ---: |
| 20 | 5,178,242 | 5,589,194 |
| 40 | 4,976,214 | 5,387,891 |
| 60 | 4,789,547 | 5,202,289 |
| 126 | 4,256,368 | 4,658,543 |

| 长度 | visual Train | Validation | Test | Fresh decision |
| --- | ---: | ---: | ---: | ---: |
| 20 | 2,705,603 | 999,559 | 1,079,929 | 34,491 |
| 40 | 2,578,979 | 876,021 | 961,925 | 33,745 |
| 60 | 2,458,881 | 761,164 | 849,981 | 32,979 |
| 126 | 2,107,260 | 429,953 | 517,162 | 30,462 |

## C. Survivorship：19–25

新分母先对全部历史 common episode 进行宽松、按日期的研究资格判定，再将 later-disappeared 仅作为审计分层。要求 20 个连续 supported potential session、20 session 范围内至少 5 个正价/正成交量观察、这些观察 median dollar volume >=50,000。不使用 S2 参数、未来收益、最终是否完整窗口或今天是否存活决定研究 Universe。这是历史观察级资格，split-only 美元额不是严格 PIT 执行流动性证明。

**19.** 全量 observed disappeared 仍为 9,976 ID，1,924,869 sessions；any available ID 3,560 /35.6856%，any ready ID 3,555 /35.6355%；safe session 822,924 /42.7522%，missing 56.9383%，Q 0.3095%。20/40/60/126 supported window IDs 为 2,251 /1,952 /1,824 /1,465。含短片段及疑似退出，不称法律退市名单；此前 core-only safe822,889 /42.7504% 保留为原报告事实。

**20.** research-relevant disappeared：2,212 ID；any available/any ready 均 2,212，但这是已有少量价格证据定义带来的条件统计，不能解读为“退市数据100%完备”。safe sessions802,380 /1,250,196 =64.1803%，Q3,819 /0.3055%。20/40/60/126 有至少一个 supported 完整窗口的 ID 为2,135 /1,932 /1,814 /1,462，即96.5190% /87.3418% /82.0072% /66.0940%。

**21.** 443,997 /1,250,196 sessions 缺价 = **35.5142%**；影响 1,035 research-qualified IDs，日期2021-09-01–2026-10-05。缺口主要类别为已具历史价格资格但大量缺 session 的 episode，以及有成员潜力、无法确认价格/流动性资格的另外3,463片段。后一组617,323 /623,257 sessions缺失（99.0479%），不能当作不具资格/不流动而从风险中消失。年度缺口见下表。

**22.** 已安装 verified merger cohort 3 ID（ATVI/TWTR/SPLK），历史1,462 sessions均 safe，无缺价；四种窗口每种3/3。小样本覆盖不能外推全市场并购，也不能代替终止对价和执行财富处理。

**23.** 已安装 verified exchange cessation cohort 4 ID（BBBY/TWTR/ATVI/SPLK），1,878 /1,881 sessions safe（99.8405%），Q3、missing0；四种窗口每种4/4。verified bankruptcy/termination/equity cancellation 类型当前0，因此该类覆盖 N/A；不代表没有破产证券，不用 cessation 冒充完整法律终止证明。

**24.** 最大残余风险是失败证券和资格未知 episode 的缺价/缺历史窗口形成非随机可观察性，加上碎片身份、退出经济后果与来源 publication-PIT 不完整。即使形态输入合法，研究结论仍可能偏向可取价证券；必须做 unknown include/exclude 和缺口分层敏感性，不能宣称 bias-free。

**25.** 不继续主动批量下载或全市场清障。记录影响范围与研究限制；未来具体策略/候选/持仓确实命中时，再按来源、日期和必要研究窗口局部修复。

| 年份 | research-qualified missing sessions | affected IDs（年度间不相加） |
| --- | ---: | ---: |
| 2021 | 50,712 | 624 |
| 2022 | 163,759 | 701 |
| 2023 | 169,093 | 781 |
| 2024 | 1,570 | 242 |
| 2025 | 29,821 | 806 |
| 2026 | 29,042 | 354 |

## D. Fresh OOS：26–31

**26.** 旧 visual index 要求整个输入落在 Fresh 内，最新仅7个post-F sessions；core价格又停在Sep28，故四长度0。旧core保持原字节/历史统计；不是修改 Test 记录冒充 Fresh。

**27.** F=2026-09-29；决策日>=F，所有输入<=决策日，允许pre-F lookback。sidecar仅绑定已有本地同provider/feed/basis行情，历史20session重叠比对至少5条、OHLC容差1e-6、volume一致，不一致追加隔离；完整market calendar内安全窗口才可生成。

**28.** 策略形态研究与 visual dataset 使用同一套 Fresh decision index，supported20/40/60/126为 **34,491 /33,745 /32,979 /30,462**；显式含unknown为34,636 /33,883 /33,117 /30,593。不是所有策略正式可评估样本数，forward labels成熟度及模型冻结另判。

**29.** 允许。实际首日2026-09-29各长度可选Universe为4,953 /4,838 /4,737 /4,369；实测窗口起日2026-09-01 /2026-08-04 /2026-07-07 /2026-03-31，末日均Sep29。数字窗口与图片重复一致。

**30.** 接口拒绝未来bars/benchmark/未批准metadata与labels；normalized模型输入只含OHLCV，membership/source/ID只作内部资格与审计。Fresh不可 training_tensor；evaluation 要模型/参数/receipt时区时间早于F、实际hash不变、Fresh未调参声明。不能以程序校验保证任意人手写冻结时间的真实性，仍需可信历史记录；系统未创造这种记录。

**31.** 本轮没有 Fresh 策略收益/标签评估或调参/训练，正式Fresh评估NOT_RUN。为数据质量检查读取过Fresh输入和图形，因此不能说Fresh数据完全无人看过。实际pre-F模型与参数freeze未被证明；今天新冻结的模型要用真实冻结之后的新决策期，不得倒签Sep29或将既有Test改名。

## E. Infrastructure：32–41

**32.** Research Infrastructure v1 semantic hash：`74b765911a8a4f18b2074cd8d9e529b25b54afade15309a148b0ca43340b80be`。

**33.** Shape contract version：`shape-research-v1`；合同semantic hash：`5841adc14e45c5044f7fa5f382a0bfba1cb52a32359250008cda0349bc0a4856`；原shape rules physical hash：`4369249e98627af14597eff120ac674c3b39295ddf1f6b05f3155b806f720ac3`。

**34.** core SHA256：`b2d11cabf686b473566fbc8623e6afd74fc55bb48baf3a85f9e43d43104e030a`（4,757,401,600 bytes，未变）；Fresh sidecar SHA256：`433b2448b8baa33ba5c5c238ad3853c07804626a3326fef16dabb6617f576673`（50,868,224 bytes）。严格historical SHA256仍`a41a38992bfd2e0e3fc1a91838725ff9f851bde760ed5aaf6a7fc167abced641`，accepted raw906,514未变。源manifest/price/config/API/build输入散列逐项核验；原规则代码用Git内容核验（其baseline physical字节未额外追溯假造）。

**35.** 595项（原573+新增22）；STOCK_RADAR_TEST_LEAN=1，包含本地native LEAN实际案例。

**36.** 全部PASS，0failed/0skipped，79.79s；1个既有websockets.legacy弃用警告。实际导出/特征/候选兼容性检查另外PASS。

**37.** Scanner模块/loader可导入，回归案例PASS；实际历史Train2023-02-03从原Current featurestore读8,406行并完成原选择，选3候选。此结果只是兼容性检查，无收益、无PIT证明。新研究默认由统一API确定可用Universe；不静默替换现有生产provider。

**38.** Strategy2原规则/TP/SL/阈值/config/feature公式保持。真实Fresh126行形态特征生成成功，保持(date,symbol)索引；不从normalized数据捏造执行价/美元成交额或横截面排名。恢复的是形态/因素研究，完整组合执行仍需其原始价与生命周期门禁。

**39.** 新exporter走冻结主入口，真实Fresh样本Parquet/tensor/SVG回读一致、重复字节一致；metadata绑定infrastructure hash，只有Train可进入training_tensor。没有训练模型、生成海量样本或重写旧视觉证据。

**40.** LEAN integration import与native-inclusive全量回归PASS；archive未进入LEAN路径。未新增正式QC Cloud策略run、未释放既有阻塞PIT组合、未导出新QC reference/market数据。

**41.** 日更模块import与对应回归PASS；current market源hash等于本轮sidecar锁，不改动现有日更任务/策略。日更不会自动覆盖冻结core/sidecar；采用新版本需要显式QA和版本记录。web API相关回归也PASS，无新增后台任务。

## F. 决策：42–47

**42.** 结束。Database expansion=CLOSED，不再让数据库建设成为长期项目主线。

**43.** 进入maintenance=ACTIVE：daily incremental、study/candidate/holding触发修复、periodic QA、source breakage修复。源库日更与研究快照版本采用分开。

**44.** 可以正式回归Strategy2本地规则/形态/因素研究。Strategy2策略有效性和正式QC独立验证尚未通过；本轮没有优化策略或新收益结论。

**45.** 可以准备视觉样本、人类标注、Train训练计划与Validation流程；本轮未训练。模型真实冻结后使用新的Fresh决策期，再考虑冻结信号交QC验证执行。

**46.** 候选/持仓命中的身份复用/重大事件/终止经济后果、必要missing interval、影响窗口的split/source/gap冲突；保留其他未知风险统计，不扩大人工全市场队列。

**47.** 正式放弃复制QuantConnect/CRSP/Bloomberg、全美法律级Security Master、全市场生命周期与publication-PIT补齐、继续批量QC reference导出、以GeneralTier2作为本地形态总门禁。旧strict evidence及更严格run gates仍保留供其具体作用域调查。
