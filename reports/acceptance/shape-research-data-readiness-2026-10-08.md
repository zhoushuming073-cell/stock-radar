# Shape Research Data Readiness — 2026-10-08

**结论：General PIT = Tier 1；Shape Research = SHAPE_RESEARCH_READY（本地形态研究范围）。**

当前 **5,775,762 条历史普通股 K 线**通过形态安全检查，占已观测证券交易日 **83.3562%**，占实际可取得行情的 **99.6392%**。其中默认 confirmed/probable 范围是 **5,372,282 条 / 77.5332%**；另外 403,480 条技术通过但 Membership unknown，需显式敏感性选项。

可以回归 Strategy 2 的形态/因子研究，准备视觉模型训练数据。没有运行或优化策略，没有训练模型，没有 QC 导出/Cloud 回测，没有自动将 Shape 结果接入生产 Scanner 或释放正式 PIT Run。

**重要范围：**分母是 2021-09-01–2026-10-07、1,280 个已观测 session 内的 **6,929,009 个普通股 ID/session**，不是完整美股市场。保守 Master 有短观察片段，同一真实公司可能有多个未合并 ID。已有 Test 曾被研究过，仍是 exploratory；本次数据冻结不能恢复它的未使用独立性。Fresh OOS 当前所有长度为 0。

## 1–6. 多少 K 线可以研究

| 问题 | 实测结果 |
| --- | --- |
| 1. OHLCV 总体可用率 | 5,796,676 / 6,929,009 = **83.6581%** |
| 2. Shape-ready 率 | 5,775,762 / 6,929,009 = **83.3562%**；可取得行情中 99.6392% |
| 3. Quarantined 率 | 20,914 / 6,929,009 = **0.3018%** |
| 4. Missing 率 | 1,132,333 / 6,929,009 = **16.3419%** |
| 5. 可用 security | 15,262 个已观测普通股 ID 中，8,828 有行情、8,823 至少一条安全 K 线；默认至少一个完整 20/40/60/126 日窗口分别 **7,381 / 7,022 / 6,818 / 6,159 个 ID** |
| 6. 可用 security-session | 技术通过 5,775,762；默认 supported member 5,372,282；不将多个来源重复算成多条 K 线 |

READY 4,094,757 / 59.0959%；READY_WITH_MINOR_UNCERTAINTY 1,681,005 / 24.2604%。后者包括 probable/unknown Membership、零成交量/极端成交量警告、非官方单独认证的拆股等不改变已检查窗口图形的缺口；unknown 仍不会默认进入 Universe。

6,434 个 ID 完全缺价；2,025 个 ID 至少有一次隔离，但不意味着整只股票不能研究。窗口只排除包含冲突/缺口的片段，后续干净窗口重新通过。security-level「任一安全 K 线」不等于具备足够训练历史，所以另列完整窗口 ID 数。

相较此前 79.9471% 的 bounded accepted/legacy availability，本轮没有新抓取行情。新增评估此前只列为 raw ticker/date hit 的 **257,137 个 member-days**，严格按已有历史区间绑定并做源/拆股/形态校验。严格 accepted raw **906,514 条 / 13.0829%** 原封不动；Shape 的扩大不是改写 accepted 标准。

## 7–9. 未来泄漏、Identity 和拆股

| 问题 | 实测结果 |
| --- | --- |
| 7. future leakage | 已安装 listing/退出/区间边界检测 **0**；通过行中的边界违反 **0**；visual 切分越界 **0**；索引重复 **0** |
| 8. ticker/issuer 串线 | 22 个 ID、14,000 个独立 session 命中多 CIK/已有 TTGT reuse 核验边界并被隔离；通过行中的已知 identity conflict **0**；有价 session 无该类冲突 99.7585% |
| 9. split 冲突 | 415 个 session 命中未解释 split-like（351 个 ID）；4 条异常 action 记录，实际 common 有价数据涉及 2 个 session；这些冲突在通过行中 **0** |

安装的有效 split/reverse split 事件 980 条，825 个事件日期有绑定行情，其中 781 个在至少一个来源上通过价格关系/其他安全检查。**只有 1 条具有已安装官方独立核验证据**；781 是自动图形相容，不是 781 份法律公告认证。其余 44 个有价事件同时存在来源/身份/价格等问题，不能把差额全部叫未确认拆股。

raw 的 known split 比例只用于有效日之后的窗口；已复权 legacy 不重复调整。对 split-only series 采用窗口首 close 和窗口最大 volume 归一化，取消窗口内均匀的后来复权常数。保留 source/basis/hash。绝对复权价格与绝对成交量不被宣称为严格 PIT 原始价。

零检测只相对于已安装的身份、IPO 和退出证据。许多原始事件缺历史公告 known_on，未覆盖发行人不能被证明零真实世界泄漏；这些限制不作为图像输入字段，也不伪装成 vendor completeness。

## 10–12. 失败证券与 Membership

| 问题 | 实测结果 |
| --- | --- |
| 10. later-delisted 保留 | 四个已核验交易所退出案例 BBBY、TWTR、ATVI、SPLK：历史 Membership 4/4、至少一个安全 K 线 4/4、完整 20 日窗口 4/4；安全 session **1,878 / 1,881 = 99.8405%** |
| 11. acquired 保留 | 已核验 ATVI/TWTR/SPLK 三例：历史及安全窗口 3/3；安全 session **1,462 / 1,462 = 100%** |
| 12. Membership 是否足够研究 | confirmed **71.6284%** + probable **21.1519%** = supported **92.7803%**；unknown **7.2197%** 保留为未知。足以开展本地历史形态研究，不证明全市场成员目录完整 |

上述交易所退出包括收购和暂停交易，不等于完成法律 Form 25 或全部 bankrupt/terminated 档案。旧 BBBY 使用原来取得的 asof 2023-05-02 raw 数据，与后来同名新发行人保持不同 ID。其少量大幅真实/待解释波动可能被保守跳变规则排除；没有因此删除整只失败股票。

全量 later-disappeared **9,976 个 ID**的历史 population 全部保留。但它们包含短观察片段、ticker 片段与疑似退出，不能当成 9,976 只真实退市公司。安全 K 线覆盖 **3,555 / 9,976 = 35.6355%**；默认完整 20 日窗口 **2,251 / 9,976 = 22.5642%**；安全 session **822,889 / 1,924,869 = 42.7504%**。这比旧 legacy 价格覆盖 26.2383% 更广，但仍明显低于整体覆盖；**缺价和片段化仍有选择偏差，不宣称已经消除幸存者偏差。**

unknown 的实际样本数量敏感性（不捏造收益）：

| 窗口长度 | 排除 unknown | 加入全部已观测且形态安全 unknown | 增加 |
| --- | ---: | ---: | ---: |
| 20 | 4,785,091 | 5,173,086 | 8.1084% |
| 40 | 4,416,925 | 4,795,016 | 8.5601% |
| 60 | 4,070,026 | 4,438,900 | 9.0632% |
| 126 | 3,054,375 | 3,375,522 | 10.5143% |

这里按已冻结 visual 切分汇总。未知 candle 可增加默认安全 candle 数 **7.5104%**；普通 Universe 日计数最大增加 595 个 ID（跨四种长度取最大）。缺席后无法确定是否仍上市的无价候选保留在原 HistoricalDatabase uncertainty API，没有为其虚构训练窗口。策略收益敏感性留待真正策略运行时做。

## 13–14. 视觉窗口与冻结切分

| 长度 | Train | Validation | Test | Fresh OOS | 默认总计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20 | 2,705,603 | 999,559 | 1,079,929 | 0 | **4,785,091** |
| 40 | 2,578,979 | 876,021 | 961,925 | 0 | **4,416,925** |
| 60 | 2,458,881 | 761,164 | 849,981 | 0 | **4,070,026** |
| 126 | 2,107,260 | 429,953 | 517,162 | 0 | **3,054,375** |

按 security/decision date/length 去重；来源候选不重复计数。整个窗口要求所有 session 存在、安全、默认成员状态 supported、一个来源/口径。窗口内的日期、OHLCV 哈希、source hash、basis、历史 ticker、metadata 和 split_assignment 可按需导出。

沿用原冻结 signal 范围：Train 2021-09-01–2024-08-29；Validation 2024-09-30–2025-09-08；Test 2025-09-23–2026-09-14；Test evaluation end 2026-09-28 后才是 Fresh OOS。没有随机混合相邻窗口，不跨 split 借 warmup；Forward label embargo 不变。Fresh OOS 只有至 2026-10-07 的少量 session，所有长度都不足；不从 Test 借 K 线伪造 Fresh OOS。

同时提供不受 dataset split 限制的普通 Scanner/特征研究窗口。不同 split 内的窗口不重叠，但同一 split 中大量窗口重叠，数量不能当成独立统计样本数。

## 15–18. 研究状态

15. **Strategy 2：可以回归形态/因子开发和本地探索研究。** 新 API 输出标准 OHLCV，复用现有 base/Strategy 2 公式与 `(date,symbol)` 索引，基准只取 <= T，原策略参数保持不变。完整旧策略还需要同日 Elasticity 横截面排名、正确绝对股价/美元成交额门槛与候选持仓生命周期；本轮没有造单股排名、自动替换生产 Scanner 或宣称完整财富回测已验证。

16. **Visual strategy：训练数据准备已经具备足够数量。** 先保留标准 OHLCV，再生成确定性 K 线+成交量 SVG 与五通道规范化 tensor；不把名称、ticker、metadata、未来标签放入模型输入。提供本地 lazy exporter，五个实际窗口图/hash 已重复一致。当前仅准备数据，模型训练和独立 Fresh OOS 验证没有开始。

17. **General PIT：仍为 Tier 1。** 原身份 A/B/C、严格 accepted raw、terminal economics、正式 native gates、QC receipts 全部保留。

18. **Shape Research：READY，在上述观测、形态与本地研究范围。** 规则在 `config/shape_research_rules.json` 冻结：覆盖至少 75%、可取得数据中通过至少 80%、消失 ID 的安全 candle 至少 500、四个已核验退出案例保留、126 日 Train/Validation/Test 窗口至少 100k/10k/10k、通过数据无已知边界/identity/split/cross-split 泄漏。门槛在策略收益评估前确定，参考已有覆盖分布和 gross corruption 标准，没有使用策略收益/QC 结果调门槛；并不声称这是金融收益可靠性的统计认证。

## 19–22. 剩余问题与停止扩建

19. 真正可能画假图的 Top findings（按独立 session，多类可重叠）：

| 原因 | session | ID |
| --- | ---: | ---: |
| 多 issuer / 已核验 ticker reuse 边界 | 14,000 | 22 |
| 未解释重大 gap/return/日内跨度 | 3,589 | 1,579 |
| 影响形态的多源分歧 | 999 | 167 |
| 未解释 split-like | 415 | 351 |
| 类别/名称切换边界 | 78 | 57 |
| 异常拆股事件比率 | 2 | 2 |

review queue 共 27,735 个 source/date finding、1,786 个不同 ID。不是全部都是已证实错价，也不是逐只人工查档案的任务；明显合法大行情可能被保守隔离，只在实际候选/窗口需要时核验。普通稳定证券、未知法律退出档案、单纯零 volume 或 directory 片段不进入人工队列。缺交易日自动禁止跨缺口窗口，不扩大单纯缺价队列。

20. 只属于供应商级、目前不阻塞形态窗口的事项：全证券法律 share-class、完整 merger/delist/terminal 档案、无事件证明、完整 publication-PIT 基本面、短片段全市场主键统一认证、全市场退出完整率。具体成交/持仓遇到 merger/cash-out/terminal 时仍需严格局部处理，不能把它们永远豁免。

21. **可以停止为 General Tier 2 主动扩大全市场建设，转入研究所需维护。** 保留缺失与偏差监测；研究命中冲突/持仓时修、具体缺价区间确有需要时补、已有日更后显式构建新快照、定期运行同一 QA。没有新增后台任务或重建 Master。

22. **下一阶段回归策略研究。** 本地做规则、特征、图表、视觉样本、候选与 exploratory 回测；冻结后 QC 使用自己的历史 Universe/Security Master/行情/LEAN 独立验证规则。视觉初期可验证冻结信号的执行，成熟后再考虑冻结模型在 QC 自有数据独立推理。不能用 QC 选股或收益反向改本地数据。

## 实现、测试与证据

实现和复现命令见 [Shape 数据层契约](../../docs/SHAPE_RESEARCH_DATA_LAYER.md)。量化证据见 [完整机器 scorecard](../evidence/shape-research-scorecard-2026-10-08.json)，[已执行 inspection notebook](../../notebooks/shape_research_inspection.ipynb)。本地版本 **0ee4ddb99d115c467e75967c87a68cb3a55e6357c35f0e298946a5bfa3b51035**；数据库 SHA256 **b2d11cabf686b473566fbc8623e6afd74fc55bb48baf3a85f9e43d43104e030a**。九项代码/规则/数据源锁全部通过；原 strict 数据库 SHA256 仍为 a41a38992bfd2e0e3fc1a91838725ff9f851bde760ed5aaf6a7fc167abced641。五个样本的图像/tensor hashes 在 evidence 中。

新增 **29 项测试**覆盖实际批量 SQL 分类、旧 accepted 和指针不变、OHLC 错误、未知 split、raw known split、复权不重复调整、ticker reuse、已知 issuer 边界、future IPO、退市历史、未来 feature/benchmark/visual 拒绝、SVG/tensor 确定性、split 隔离、边界坏行、Fresh OOS、混合口径、unknown、ordinary 自动通过、material-only queue、多源冲突与非永久拉黑。**完整 native-inclusive suite：573 passed，1 个既有 websockets.legacy 弃用警告，94.86 秒。**

[实际耦合与导出回读](../evidence/shape-research-integration-2026-10-08.json)：NVDA 126 行原公式特征输出 `(date,symbol)`，末行 50 个非空字段；篡改 T 之后 SPY/QQQ 完全不影响结果。2026-09-14 默认 126-session Universe 4,406 个 ID，加入 unknown 为 4,425。BBBY Train 样本 parquet/hash、npy/tensor、SVG 逐字节回读一致；read-only 散列核验打开约 2.97 秒。2024-08-29 的 NVDA 126-session 窗口不通过，API 如实拒绝；普通 ticker 没有白名单豁免。

用户摘要：完整通用 PIT 仍为 Tier 1，但已有 **83.36%** 的观测历史 K 线达到 Shape 标准；默认成员范围可用 **537 万条**。现在可以研究 Strategy 2 的形态因素、准备视觉训练数据。仍需关注后来消失证券的缺价和真实候选的生命周期，Fresh OOS 样本尚未形成；不再把供应商级数据库完整性当成形态研究的总前置条件。
