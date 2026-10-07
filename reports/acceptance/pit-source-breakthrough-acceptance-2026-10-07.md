# Stock Radar PIT 批量来源突破验收 — 2026-10-07

本轮找到了大规模候选数据空间，但没有找到满足正式门禁的免费来源组合。**435,678 条缺价中，Dolt 固定版本存在 322,439 条同代码、同日期记录（74.01%）；新增正式接受价格、认证身份、完整行动 scopes 均为 0。Formal PIT 仍 BLOCKED。**

这次停止逐证券人工清障，改为按日期查询全部依赖代码、批量历史身份匹配和全窗人口比较。未开发新的正式 adapter/importer，未安装候选数据。免费路线的当前边界主要是身份、原始价格口径及人口/行动完整性证明，不能把结果解释为“免费行情根本不存在”。

- [完整 40 来源评分表](../evidence/source-breakthrough-scorecard-2026-10-07.md)
- [所有能力、许可、版本字段的 JSON](../evidence/source-breakthrough-scorecard-2026-10-07.json)
- [可审计的计数、版本、receipt、保护哈希](../evidence/pit-source-breakthrough-evidence-2026-10-07.json)
- 前序 [数据清障验收](pit-clearance-acceptance-2026-10-07.md)、[最终工程验收](pit-final-acceptance-2026-10-07.md) 保留原样。

## 1. 重新读取的真实基线

启动和收尾均读取 GitHub `main`，均为 `3637282ea3fbb7726063b65b2b1633af52782de1`，tree `4e7616226f4666e319c75c683e65288e65d24683`。读取旧验收、唯一总账、正式 dependency、blocker inventory、ResolutionQueue、现有 identity/price/action adapters 和安装后的 master/feature store；收尾用现有 `readiness()` 重验相同冻结闭包的物理锁。

正式请求仍是 `b4483d79-adac-4845-b28c-ebf9605ca5cb`。Dependency semantic SHA：`2538efd79fdc64f5479f4345256f4d077e709d475c84a0452be9baa87256febf`；文件 SHA：`cf9ae48ad8511280b8b245fc5aca7a15411b6f11c1cc82f6181adab707a08dbf`。

Validation：2024-09-30–2025-09-08，评估至 2025-09-22；**实际 required price 范围为 2023-12-12–2025-09-22**，含暖启动，不假设只需要 Validation 内价格。

| 指标 | 开始 | 收尾重算 |
|---|---:|---:|
| 依赖证券 / signals | 6,421 / 4,176 | 6,421 / 4,176 |
| required prices | 2,023,436 | 2,023,436 |
| missing prices | 435,678 | 435,678 |
| fully / partly unpriced 身份 | 1,138 / 1,176 | 1,138 / 1,176 |
| identity blockers | 6,416 | 6,416 |
| complete action-scope certifications | 0 / 6,421 | 0 / 6,421 |
| Membership | FAIL | FAIL |
| ResolutionQueue | 6,421 blocked，0 active | 未修改 |
| Terminal / LEAN Input | PASS / FAIL | PASS / FAIL |
| Native / reconciliation | NOT_RUN / NOT_RUN | NOT_RUN / NOT_RUN |

Installed master `533905312e4c19ef2f80558d80c06c1b644f3eefc01fbba0c703904f1dc8bdaa`：7,657 feature IDs、5,472,884 行；数据库 SHA `9c39a9f99c8fb1985b40c797a74f41dd6073872243b26584c8401347115a00ff`。上述数字没有沿用提示词近似值。

## 2. 搜索范围和计数口径

调查 **40 个具名候选 offering**，其中 9 个为商业基准或商业产品的公开样本。它们不等于 40 个独立上游；SEC 镜像、Nasdaq 目录镜像、Yahoo 镜像均明确标识共同来源。

| 检查层级 | 数量 | 口径 |
|---|---:|---|
| Formal dependency coverage comparison | 6 | Dolt stocks、CIK Mapper、Nasdaq Listings、defeatbeta 当前身份目录、FINRA、YLiu 退市清单 |
| 实际数据小样本 | 7 | Stonks、FINSABER、Liquidata、graziek9、Nasdaq 当前目录、OpenFIGI、Apify 公开样本 |
| 文档 / 元数据 / Git tree | 24 | 无实际数据覆盖结论，逐项列在评分表 |
| 访问测试未取得数据 | 3 | PWB ListingStatus HTTP401、SEC 13F 直接下载 HTTP403、Alpha Vantage demo 返回 Information |

因此实际取得数据并测试的是 **13 个**；若把访问尝试也计为测试则为 16 个，不能混用。六个正式依赖比较中，只有 Dolt 是完整缺价 date/symbol 存在性测试；defeatbeta 的全量测试限于**当前身份目录**，不声称完成其全价格文件压测。

搜索覆盖 GitHub/GitLab、Dolt、SEC、Nasdaq/NYSE、FINRA、学术复现、Hugging Face/Kaggle/Zenodo/Figshare、Internet Archive、data.gov 和免费 API。GitLab/Internet Archive 搜索没有得到可核验、覆盖目标窗口的批量候选；它们是搜索渠道，不虚构成新增来源。data.gov 的相关命中主要回到 SEC NPORT/13F，按原始 offering 计数，不重复增加独立证据。[SEC data.gov 目录](https://catalog.data.gov/organization/sec)。

高潜力来源实际查询了 META/FB、NVDA、ATVI、TWTR、SPLK、BBBY、BYON、IREN、AAPL、LEHMQ；结果允许“未返回”“访问失败”“只覆盖当前日期”。没有把 README 的完整性声明当验收。低优先级的单股票/指数数据和受限数据不进行昂贵下载。

## 3. Breakthrough Matrix

| 来源 | Membership | Identity | Price | Actions | Formal Run 实际改善 |
|---|---|---|---|---|---|
| Dolt stocks（已有） | 无全人口认证 | 无 class/permanent ID | 322,439 同代码日期候选；259,563 在观察映射内 | split/dividend 有表，非完整覆盖 | 0；正式缺价仍 435,678 |
| CIK Mapper 历史 | SEC 目录观察，非全人口 | 5,626 dated issuer 候选，其中 5,621 是 blocked 身份；3 个多 CIK 冲突 | 无 | 无 complete action feed | verified 增量 0 |
| Nasdaq Listings 历史 | 235 日比较，230 日有近期月度快照；Nasdaq only | 名称/ETF 标识，缺完整 class ID | 无 | 目录变化不等于事件认证 | 全窗 Membership 仍 FAIL |
| defeatbeta Yahoo 镜像 | 当前目录 | 5,226 当前代码候选；dated proof 0 | 大文件实际抽样；BBBY 复用和 split basis 不合格 | 无完整声明 | 0，quarantine |
| FINRA OTC Daily List | OTC 范围 | old/new symbol/class 候选 | 无 OHLCV | 24,580 事件；160 同代码身份候选，76 在映射及 required 日期内 | 完整认证 scopes 0 |
| YLiu 退市清单 | best-effort，非全人口 | 514 US 行、84 同代码身份候选 | 无 | 退市日期/部分 payout 注记 | verified / certified 增量 0 |
| 其他免费价格候选 | 缺完整历史人口 | 当前符号或无身份 | 数据过期、局部或调整口径未认证 | 不完整 | 无正式改善 |

“同代码日期存在”只说明来源有一行，尚未验证整条 OHLCV 的有效性、issuer/class 归属、价格口径或来源许可。“观察映射内”也不是 identity-safe accepted。

### 3.1 Price：完整 360 日期批量测试

固定 Dolt commit `vt6qeesk27k07492k5jc5b7p04mf0s6o`。对全部 360 个有缺价的日期，查询该日期全部缺价依赖的 symbol 集合；按 date/identity 去重，不把多个 alias 算成多条补价。日期聚合返回一行，绕过公共接口 1,000 行结果上限带来的截断风险；两条 I/O worker 不是多 agent。

| 计数 | 实测 |
|---|---:|
| missing before | 435,678 |
| source ticker/date rows exist | 322,439（74.0086%） |
| candidate remaining，未按身份审核 | 113,239 |
| inside observed mapping | 259,563（59.5768%） |
| 至少一个价格候选的 dependency IDs | 1,880 |
| 所有缺日期均有同代码行的 IDs | 678 |
| identity-safe accepted 新价格 | **0** |
| formal missing after | **435,678** |

初期查询超时/接口 deadline 及一次缓存后汇总的 benchmark schema 错误均保留、修正后重新执行；最终 360/360 查询全部成功并输出结果。失败响应没有加入覆盖数。代码支持从 SHA 校验的缓存续跑，正式结果只在所有日期完成后输出。

来源没有命中的 113,239 个 identity/date 对只能叫**在该固定来源版本和查询标签下未找到**；可能涉及别名、复用、遗漏或来源范围，不能推断互联网没有行情，也不能填零或用最后价格延长上市生命周期。

### 3.2 Identity：历史观察并非完整证券身份

66 个 pinned CIK CSV 快照覆盖 2024-09-25–2025-02-28；另查询 2022-06、2022-10、2023-04、2023-10、2024-03 的五个历史版本做生命周期样本。5,626 个依赖 ID 有落在观察 mapping 区间中的 ticker→CIK 证据，含原有 5 个已认证身份，**新增 blocked 身份候选为 5,621**。终点后存在空窗；issuer CIK 不能代表唯一股票 class。

| 多 CIK 候选 | 实际 CIK | 处理 |
|---|---|---|
| BLK | 0001364742 / 0002012383 | 保留冲突，未按代码合并 |
| MPU | 0001036848 / 0001953021 | 保留冲突，未认证 |
| TTGT | 0001293282 / 0002018064 | 保留冲突，未认证 |

没有补齐证券 class、所有交换所/代码区间、复用排除、effective/available 时点证据，因此 verified 增量为 0。

### 3.3 Membership：独立采集的局部交叉检查

22 个 pinned Nasdaq CSV 与完整 235 个 Validation 交易日逐日比较。230 日有 2024 年以后的最近快照，年龄 0–30 天；其中 47 日年龄不超过当前历史目录 4 天 carry 上限。其余 5 日只能找到很旧的快照，单独标为陈旧比较，不能作为近期历史证据。

近期 230 日的 intersection 为 **2,977–3,060**，current-only 为 **0–45**，directory-only 为 **1,766–2,017**。比较左侧是当前 master 的 eligible Nasdaq common symbols，右侧是来源全部 Nasdaq instruments；右侧包含 ETF、ADR、preferred 等，**不能把 directory-only 数量解释为漏掉的普通股数量**。

这是不同采集仓库的历史交叉检查，仍共享 Nasdaq Trader 上游，不是全市场独立权威人口认证。月度观测无法证明相邻快照间每天的 IPO、退出、类别/交易所变化；缺 NYSE/AMEX 完整历史。未将月度快照 carry 进正式数据，Membership FAIL 保留。[来源](https://github.com/datasets/nasdaq-listings)。

### 3.4 CorporateAction：官方局部事件和完整 scope 分开

FINRA 实际 read-only API 按完整 required 日期范围 **2023-12-12–2025-09-22** 分页取得 **24,580 条** OTC publication records。五页、每页至多 5,000，验证日期、字段完整性、事件 ID 唯一性。160 个依赖 ID 有同代码事件；76 个候选落在观察 mapping 且对应依赖 required 日期范围内。

初始全字段 CSV 的并购 commentText 存在未正确转义的引号，造成列错位；未采用这些错位行。改为明确字段查询，保存失败/原始响应并验证结果。calendarDay 是发表日期，exDate 是生效日期，两者不互换。

FINRA 可做 OTC 退市后生命周期的 validation source，不能覆盖 Nasdaq/NYSE/AMEX 全部普通股行动。零事件返回不能认证 `reviewed_no_material_action`。未生成 no-action certificate，完整 action scope 增量为 **0**。[官方 API 定义](https://developer.finra.org/docs#query_api-equity-otc_daily_list)。

## 4. 真实生命周期样本的淘汰依据

| 案例 | 实际响应 / 风险 |
|---|---|
| META / FB | 历史 CIK Mapper：旧 FB 与 META 均为 CIK1326801。OpenFIGI 当前 FB 返回 ProShares ETP；不能用当前 FB 识别 Meta。Dolt 2022-06-08 返回 FB，2025-09-22 同时有不同价格的 FB/META。 |
| NVDA | 2024-06-03 Dolt stocks close1150；defeatbeta close115；graziek9 close114.95。后两者 OHLC 调整过，不能标为原始执行价格。 |
| ATVI | Dolt 2023-10-12 close94.42；Stonks 停2023-10-10，缺最后两日；当前 Yahoo 镜像和 OpenFIGI 该查询不返回。 |
| TWTR | Dolt 2022-10-27 close53.70；Stonks 保留至该日。YLiu 对应公司名为字面值 `Nan`，不能凭该清单认证身份。 |
| SPLK | Dolt 留有退市前行情；Stonks 提前停2023-10；当前 Yahoo 镜像/OpenFIGI 不返回该案例。 |
| old BBBY | CIK Mapper 历史 CIK0000886158。2023-04-28 Dolt oldBBBY close0.1072，defeatbeta 的“BBBY”却为20.36，等同 BYON；镜像没有恢复旧破产发行人。 |
| BYON / new BBBY | 历史 Mapper BYON 为 CIK0001130713；其归属不能迁移到旧 BBBY。defeatbeta BBBY 与 BYON 回写同一较新发行人历史，2023-04-28 两者都20.36。 |
| IREN | 历史 CIK0001878848 连续；Dolt/Yahoo 有价格，源目录不直接证明完整 class/event coverage。既有官方身份认证保持。 |
| AAPL | 正常 active 对照：Dolt/Yahoo/Stonks均有不同范围的历史；证明 active 可取不等于证明 inactive 完整。 |
| LEHMQ | 明确退市对照：所选价格日期、目录及 OpenFIGI 小样本未返回。仅记录本次查询不命中，不宣称所有历史来源不存在。 |

defeatbeta 抽样固定 revision `4679dc75b0a7e3f6c0951f2913e3dc46b4e033db`，读取 12 个 Parquet row groups，共 16,298,820 bytes，校验 HTTP206、Content-Range、ETag/size 不变及 raw SHA。文件 36,955,324 行、370 groups。publisher ODC-BY 声明不证明 Yahoo 上游授权；身份和 split basis 实测不合格，未继续写全量正式价格 adapter。[数据卡](https://huggingface.co/datasets/defeatbeta/yahoo-finance-data)。

另外：Liquidata `prices` 是 2020 last_sale snapshots；graziek9 最新 commit 删除价格表，查回删除前版本才得到上述调整 OHLC；FINSABER 实际 COF 样本有 OHLC/adjusted_close/volume，但 S&P500-only 和 2024 截止范围不够，11 个 ticker-filter 请求失败未被写成“无该证券”。PWB 明示需批准/订阅，未利用 `gated=false` 元数据绕过要求。Apify 仅取其公开标注的 200-record 样本，未运行 actor、注册或购买；Form15 注销不能直接当交易终止。

## 5. 来源组合和接入决定

按现有证据只保留三个主要**研究候选角色**：A = Dolt stocks 的价格空间；B = CIK Mapper 的 dated issuer cross-check；C = Nasdaq Listings 的历史人口交叉检查。A 是已接入的来源，并非本轮新发现。FINRA 保留为官方 OTC validation 证据，未变成第四个正式接入来源。

| 组合 | 价格存在性 / 身份候选 | 可正式接受新价格 | 可认证新身份 | action / membership | 正式缺价预测 / 实测 |
|---|---|---:|---:|---|---:|
| A | 322,439 ticker/date hits；观察 mapping内259,563 | 0 | 0 | 未认证 | 435,678 / 435,678 |
| A+B | 1,330个有价且有datedCIK候选的ID，279,362价格hits；其中mapping内255,552 | 0 | 0 | 缺class/区间及action证明 | 435,678 / 435,678 |
| A+B+C | 同上；增加235日Nasdaq目录比较 | 0 | 0 | 全市场membership仍FAIL | 435,678 / 435,678 |

B/C 没有提供额外 OHLCV，不把来源重叠累计成补价增量。A+B 的交集是**更有身份线索的候选子集**，不表示加入 B 后 A 的原始行消失。即使候选数超过5%或几千个，达到正式接入门槛的“减少 blocker / 解决 identity / 完整 scope认证”仍为0。

所以 production primary/secondary/validation **新 adapter 选择为空**。许可、身份和 basis 不能通过改门禁解决。本轮不安装、不 rebuild feature store/Scanner/dependency，也不创建重复 blocked Run；现有冻结 closure 的正式 gate 直接重算，仍 FAIL。这符合“先 benchmark，明显有效才接入”的条件。

## 6. Free/Open Data Ceiling 与最小商业补充

免费研究可继续做批量候选整理和局部交叉核验；**当前已测试来源组合达到正式可信度闭环的边界**。这不是对所有未来公开数据的普遍不可能性证明，也不是“价格不存在”的结论。停止无新证据的几千次人工证券复核。

| 剩余阻塞类别 | 本轮证据 |
|---|---|
| 免费完整来源未找到 | 全市场 dated class-level master / full action coverage 未找到 |
| 许可或使用范围未闭合 | Yahoo 镜像上游 rights unclear；部分平台需批准/订阅；代码许可证不等于数据许可证 |
| Identity 无法证明 | 5,621 blocked issuer候选仍缺 class/所有代码与交易所区间/复用证明 |
| Membership 无法证明 | 局部 Nasdaq 月度历史，不是 Nasdaq+NYSE+AMEX 每日 common完整人口 |
| CorporateAction coverage 无法证明 | OTC官方事件不是全listed scopes；事件缺席不能认证无行动 |
| 价格不存在 | **未证明**；仅113,239在固定Dolt版本/标签下未命中 |
| 商业补充需求 | 优先权威 historical security master + daily listing status，随后精确残差价格/事件范围 |

如果只买一块数据，优先询价**美国普通股历史 Security Master + 每日 listing/status 历史**，包括 active/inactive、永久证券/class ID、CIK、全部 ticker/exchange/type 区间、上市/退市 effective dates、可解释的来源版本和本地研究授权。时间至少覆盖实际 required 2023-12-12–2025-09-22，并提供此前身份链；以现有6,421 ID与完整市场人口校验范围验收。这个结构性数据块比再买一份当前代码行情更能释放已找到的322k候选。**它单独仍不保证 Formal PASS**：raw basis、剩余价格和行动覆盖证书仍必须逐门禁验收。

最低公开套餐的试验基准是 Massive Stocks Starter **$29/月**：官方文档提供 PIT `date`、`active`、type、CIK/shareClassFIGI/reference history，套餐含5年行情，可覆盖本次暖启动。免费 Basic 仅2年历史，以当前日期不能覆盖2023-12暖启动。只评估一个月/所需数据范围；购买前必须确认落盘保留许可、inactive/reused案例和历史字段完整性。文档不等于实测，也不保证一次购买解决全部门禁。[价格](https://massive.com/pricing?product=stocks)、[历史证券目录接口](https://massive.com/docs/rest/stocks/tickers/all-tickers)。

尤其不能把 Massive “corporate actions”营销文字当 complete merger/cash feed；当前 Ticker Events 仅支持 `ticker_change`。[官方 endpoint](https://massive.com/docs/rest/stocks/corporate-actions/ticker-events)。若需要严格的 merger/terminal/负事件覆盖声明，另行询价**目标窗口的 action/event scope**，而非默认为$29已覆盖。

其他基准：EODHD price-only **$19.99/月**较便宜但不解决关键身份/人口；Norgate US Platinum 含退市数据为 **$346.50/半年或$630/年**，历史指数成分不等于全市场人口；Sharadar OHLC的split-adjusted口径不能因为存在closeunadj就称全部OHLC原始；CRSP/NYSE master/ZHDM须合同报价，没有虚构价格。Tiingo动态页没有核实到当前价格，未给旧数字。[EODHD](https://eodhd.com/pricing)、[Norgate](https://norgatedata.com/stockmarketpackages.php)、[CRSP](https://indexes.morningstar.com/research-data-products/crsp-us-stock-databases)。没有注册、购买或混入付费数据。

## 7. 直接回答15个问题

1. **调查多少？** 40个具名offering，非40个独立上游；9个商业基准/公开样本。
2. **实际测试多少？** 13个取得实际数据响应；另3个访问尝试未取得数据，不混计。
3. **哪些仅文档？** 24个，评分表 `docs-metadata` 完整列出，含Timemachine、复现代码、受限PWB、SEC holdings/FTD、单股/指数档案及商业文档。
4. **哪些压测Formal Run？** Dolt缺价全量、CIK历史、Nasdaq全窗、defeatbeta当前身份目录、FINRA完整required时间批量事件比较、YLiu全US清单，共6个。
5. **价格覆盖最大？** 已有Dolt，322,439存在性候选；新增正式accepted0。新价格来源没有通过小样本可信度条件。
6. **身份覆盖最大？** CIK Mapper，5,626dated候选、其中5,621blocked；新增verified0。
7. **行动最有价值？** 免费官方FINRA OTC事件作局部验证；无来源认证显著比例listed完整scopes。
8. **独立Membership找到吗？** 找到不同采集仓库的Nasdaq局部历史交叉检查；未找到全市场独立完整认证。
9. **最佳组合？** 研究A=Dolt、B=CIK Mapper、C=Nasdaq Listings；正式新接入组合为空。
10. **预测能降多少？** 身份6416→6416、缺价435678→435678、unreviewed actions6421→6421、Membership FAIL→FAIL；候选上界单列。
11. **实际接入后？** 未接入不合格候选；门禁重算同上述值，正式改善0。
12. **免费路线能继续吗？** 可以做批量research/quarantine；当前证据不足以继续承诺免费Formal闭环。
13. **到达Ceiling吗？** 已测试免费组合的身份/人口/行动可信度边界已明确；不是全网价格缺失或普遍不可能证明。
14. **Formal PIT PASS？** 没有；Native和reconciliation未运行，未生成PIT收益比较。
15. **最小付费需求？** 优先target-window历史证券master+每日listing/status；$29/月Massive是最低公开多能力试验基准，须验证，不保证PASS；随后只补认证后的price/action残差。

## 8. 代码、测试与现有数据库耦合保护

新增四个小型研究脚本：`benchmark_pit_sources.py`、`discover_pit_bulk_sources.py`、`sample_pit_public_parquet.py`、`sample_pit_bulk_references.py`。仅产生 ignored `data/pit/source-breakthrough`/`raw/source-breakthrough` 的研究证据；不调用 install/accept，不修改现有配置、PIT core、Strategy2、Scanner、LEAN架构、TP/SL或窗口/人口。

测试 **409 passed**，包含原397项和新增12项；`STOCK_RADAR_TEST_LEAN=1` 启用既有原生LEAN测试。新增测试防止alias重复计数、ticker reuse被当认证、benchmark单symbol schema错误、失败/缺字段/错SQL响应、未固定revision、HTTP忽略Range、partial payload、缓存字节/metadata和源ETag变化。已有正式adapter的license/basis/identity等测试全部保留。只有已有websockets弃用警告。

所有被保护数据库、active master三文件、installed PIT feature DB和frozen run plan的收尾SHA均与entry一致。现有consumer的数据路径、schema与身份合同未改变；实际相同dependency物理锁通过，gate结果保持fail-safe。没有伪造新正式Run、完成状态或回测差值。

复现：先读machine evidence内entry/原闭包，保留对应本地raw与snapshot pins，然后执行 `.venv/Scripts/python.exe -B scripts/benchmark_pit_sources.py --dolt --reference`；另外两条small sample脚本按其固定捕获版本运行。网络响应失败明确报错，不安装partial output；失效/不明确license的payload只保存在本地研究区。大体积上游raw未提交Git；公开报告是来源评价、计数和receipt hash。

唯一总账§3.2与RESEARCH-03继续OPEN/PARTIAL。本轮达成的是批量来源实测及免费可信度边界识别，未达成无幸存者偏差的正式PIT研究运行。
