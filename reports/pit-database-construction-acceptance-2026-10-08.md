# Stock Radar PIT 历史数据库建设验收 · 2026-10-08

> **状态：本轮数据库工程与证据产物已交付；整库 Tier 2 目标尚未达到，不能进入 maintenance。**
> 目标是未来策略共用的历史数据底座。这里没有以某个 Strategy 2 Run、收益率或 Cloud benchmark 作为验收标准。

本轮在 GitHub main 上先核对现状，最后同步到 `a5f1509` 的文档更新。运行时代码和全部数据输入另由 manifest 的 SHA-256 固定。下面数字全部来自实际数据库查询；旧报告的研究子集数字不能替代这次全历史口径。

## 交付内容

- 按连续生命周期生成 `security_episode`，保留现有内部 ID；ticker、issuer、class、交易所区间、价格系列分别记录。证据图有来源、版本、日期、置信度和 hash；未知 predecessor/successor 保持 NULL。
- 重建 2021-09-01 至 2026-10-07 的 1,280 个已观察交易日：`daily_population` 共 9,600,753 行。新增只读 API、逐日 scorecard、12 个固定哈希回放日期和固定抽样。
- 自动完成全部 ID 的 A/B/C 分类和结构性风险排队。普通股与其他类别队列分别统计；没有逐证券人工搜索，也没有未经证据合并身份。
- Unknown 保持 nullable Boolean。另有 `uncertainty_on` / `candidate_population_on` 返回过去出现、后来缺失但没有确认终止的身份，防止把目录缺失当作 False。
- 机器证据安装生成独立版本，仅能添加审查注记和保守质量隔离，不能直接 splice 身份。已安装 TTGT 的新证券风险注记。
- 优先修复明确的退市案例：旧 BBBY 新增 419 条原始 SIP 行情和 419 条因果特征；沿用既有字段、公式和 research 配置，横截面排名保持 NULL。
- 保留原 master、原价格/特征库、策略参数、Formal/Native gates 和 QC smoke；没有继续导出 QC reference/market data，也没有启动新的策略 Run。

实现和操作合同：[数据库接口说明](../docs/PIT_HISTORICAL_DATABASE.md)。可复查计算：[audit 脚本](../scripts/audit_pit_database.py)、[inspection notebook](../notebooks/pit_database_inspection.ipynb)。

## 完成度与可信度

这里的 Membership / Price 分母是 **6,929,009 个已观察普通股候选 member-days**，不是整个美国市场的真实上市全集。Identity 分母是 **15,262 个曾被标为普通股的保守内部 ID**，其中包含身份碎片和类别变动，不是 15,262 家不同真实公司。

| 项目 | 实测比例 | 分子 / 分母与含义 |
| --- | ---: | --- |
| 架构验收覆盖 | 100% | 18 / 18 个用户要求的测试合同有覆盖；不是整个数据库已经完成 |
| Membership 有正面证据 | 92.7803% | 6,428,756 / 6,929,009；confirmed + probable |
| Confirmed membership | 71.6284% | 4,963,139 / 6,929,009；日期可用的多源支持 |
| Probable membership | 21.1519% | 1,465,617 / 6,929,009；主来源支持，缺少有效交叉证据 |
| Unknown membership | 7.2197% | 500,253 / 6,929,009；冲突/身份不确定，不作为 False |
| Identity 自动低风险 A | 15.5615% | 2,375 / 15,262；全窗口审计评级，禁止用来筛选过去的股票 |
| 当前仍被观察的普通股候选 A | 44.8733% | 2,372 / 5,286；仍没有达到 90% 自动安全通过目标 |
| 有身份区间绑定的行情可用性 | 79.9471% | 5,539,539 / 6,929,009；legacy split 和独立 raw 分系列统计，不拼接 |
| 原始价格 ticker/date 可用性 | 32.6085% | 2,259,445 / 6,929,009；包含尚未接受的源数据命中 |
| Accepted raw prices | 13.0829% | 906,514 / 6,929,009；具有完整 provenance 的接受行 |
| Features 可用性 | 78.9911% | 5,473,303 / 6,929,009；存在特征不等于事件/身份/组合已经可放行 |
| 已确认的生命周期风险记录 | 0.1097% | 13 / 11,852；分母含疑似消失/类别变化，不是确认发生了 11,852 起法律公司行动 |
| 后来消失身份的早期记录保留 | 100% | 9,976 / 9,976 个普通股候选 ID |
| 已确认停止上市交易案例保留检查 | 100% | 4 / 4；membership、prices、features、scanner 映射资格均仍存在 |
| 整库 Tier 2 门槛满足 | 37.5% | 3 / 8 条预先固定的验收门槛；不称作总体数据库完成百分比 |

**整体等级是 Tier 1 Exploratory PIT。** 可以进行明确证据范围内的探索、数据审计和策略原型研究；尚不能把全历史集合当作已达 Research-Grade 的共用输入，更不能声称 Vendor-Grade。各组件分母不同，不能取平均制造“总体完成 xx%”。

## 来源与时点

新取得并固定了 176 份原始快照，形成 1,661,963 个有日期的观察记录：

| 来源 | 固定版本 | 快照 | 实际可用区间 |
| --- | --- | ---: | --- |
| SEC CIK mapper 的历史镜像 | `7883b83389836f9bba9bdfe53031467235746334` | 143 | 2021-12-26–2025-02-28 |
| Nasdaq listings 历史镜像 | `3bfa59eee648599edb0f1f7c33755cf3790038be` | 33 | 2024-10-08–2026-10-01 |

原始来源分别是 SEC issuer registry 与 Nasdaq 目录。镜像 Git 时间按现有纽约收盘规则转换成可用日期，不伪造为 IPO/上游公告时间。只使用当日已可用的记录，CIK 的 2025-02 终点不会被外推为 2026 年最新 issuer 证明。Nasdaq 镜像和主目录可能有同源关系；多份镜像不是多个独立完整市场证明。Confirmed 仅指已观察 census 内的多证据支持。

SEC master index、submissions 与 Form 25 搜索实际返回 HTTP 403；GitHub API 也返回 rate-limit 403，公开 Git 克隆则成功。失败收据保留于 [来源探测证据](evidence/pit-database-source-probes-2026-10-08.json)。缺少可访问文件不能被解释成没有发生事件。[SEC 官方获取说明](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) 与 [FINRA 官方数据说明](https://developer.finra.org/docs) 已核对；没有把 OTC 事件直接当成美股上市 membership master。

旧的 13 份官方证据原文 SHA-256 全部重新验证。未解析公告可用日期的 legacy 事件保持 `known_on=NULL`，只作回溯事实，不输入历史预测；终止结算经济模型仍未启用。普通股票不要求逐只 no-event certificate。

## 实际修复与代码耦合

**旧 BBBY：** 先确认旧 issuer `SEC-0000886158-COMMON` 的 Nasdaq 普通股区间和既有官方证据，再取得 2021-09-01–2023-05-02 的 419 个交易日 raw SIP 行情。请求固定 `asof=2023-05-02`，避免使用当前复用 ticker 的实体。Alpaca 的 [官方历史行情参数说明](https://docs.alpaca.markets/us/reference/stockbars) 区分原始/复权口径，并说明历史 asof 用于实体解析。价格和 SPY/QQQ 基准分别缓存、校验分页和 SHA-256。419 条特征使用既有因果公式；237 天通过既有 tradability 条件，横截面排名 0 行有值，不据此宣称策略有收益或可以运行 Native。

**TTGT：** 自动队列发现 CIK `0001293282` / `0002018064` 冲突。官方 issuer [2024-12-02 公告](https://investor.informatechtarget.com/news-events/news/News/2024/Creation-of-Informa-TechTarget-the-B2B-Growth-Accelerator-for-the-Technology-Sector/default.aspx) 说明新公司的普通股于 2024-12-03 开始沿用 TTGT 交易。日期后的旧 ID 特征被隔离，membership 为 unknown；2024-12-02 的历史映射仍可读。没有把新公司股价接到旧公司的历史上，也没有安装未经验证的现金结算。见 [机器审查证据](evidence/pit-database-ttgt-review-2026-10-08.json)。

12 个种子回放日期上的来源 eligibility ID 集合，与原 `LocalSecurityMaster` 完全一致。ATVI/TWTR/SPLK 各 20 条真实旧特征通过新适配器，ID/date 保持一致；旧 BBBY 的新特征使用同一字段 schema 并通过适配器。见 [实际耦合检查](evidence/pit-database-integration-2026-10-08.json)。新数据库是显式 opt-in，原 `load_universe`、queued Runs 和原 feature store 没有被覆盖。

24 个之前记录的受保护/活跃数据库及 frozen 产物 hash 均保持一致；本次构建的 19 个输入锁也保持一致。原 QC 两个 smoke PASS 仅留作外部抽查，未用于目录或价格导入。

## Survivorship audit 与历史回放

固定 seed 为 `stock-radar-database-2026-10-08-v1`，按 seed + ID 的 SHA-256 排序选择，未挑选容易案例。

| 分层 | 可用对象 | 本次抽取 | 距 50 的缺口 |
| --- | ---: | ---: | ---: |
| 当前仍被观察、曾为普通股的候选 | 5,286 | 50 | 0 |
| 官方证据确认停止上市交易（含已完成 M&A） | 4 | 4 | 46 |
| 已确认 ticker change | 2 个 ID | 2 | 48 |
| 已确认 M&A | 3 | 3 | 47 |
| 普通股 reuse / identity-risk | 11,655 | 50 | 0 |

合计 109 个分层样本记录，历史保留 109/109（100%）；同时具备审计 A、accepted raw 与 features 的 19/109（17.4312%）。同一证券可以出现在不同分层。确认停止交易不是已解析法律退市生效日，也不等于 OTC 股权已取消。不能用 9,972 个未解释的目录结束记录补足“50 个已确认退市”样本。因此用户要求的三类 50 样本仍未达标。

| 案例 | 最后上市交易资格日期 | 价格交易日 | 特征行 | 历史保留检查 |
| --- | --- | ---: | ---: | --- |
| 旧 BBBY | 2023-05-02 | 419 | 419 | 通过 |
| TWTR | 2022-10-27 | 292 | 292 | 通过 |
| ATVI | 2023-10-12 | 532 | 532 | 通过 |
| SPLK | 2024-03-15 | 638 | 638 | 通过 |

十二个回放日期覆盖每年两个交易日。每日已观察各类证券 6,817–8,601 个，中位数 7,217；普通股区间记录 5,161–6,001 个。按固定 >500 行变化阈值未发现单日异常跃变；这不能证明市场全集没有遗漏。2026-04-20 还有 9,010 个曾为普通股的缺失观察候选 ID 保持 unknown，其中有身份碎片，不能把它们当作仍上市股票，也不能把它们全部视为已退市。

完整回放计数、各交易所分布、各类样本 hash 和所有分母见 [机器 scorecard](evidence/pit-database-scorecard-2026-10-08.json)。逐条 source 观察、详细样本、每日 scorecard 和数据库都在本地 ignored 的版本目录中。

## 25 个验收问题

| # | 问题 | 实测回答 |
| ---: | --- | --- |
| 1 | 总历史 episode 数 | 88,340；90,339 ticker/type/exchange 区间；88,339 保守内部 ID。不能解释为 88,339 只真实普通股。 |
| 2 | A/B/C 数量 | 全 ID：2,375 / 1,232 / 84,732；曾为普通股 ID：2,375 / 1,232 / 11,655。 |
| 3 | Identity Tier2 PASS 比例 | 普通股候选 ID 的 15.5615%；全窗口审计，不是当日选股名单。 |
| 4 | unresolved 数量 | 普通股非 A 12,887；全部类别非 A 85,964。其他类别不进入普通股人工清障主队列。 |
| 5 | 每日 population | 已观察 6,817–8,601，中位 7,217；普通股 5,161–6,001；不是完整 US census。 |
| 6 | confirmed membership | 71.6284%，4,963,139 / 6,929,009 普通股 member-days。 |
| 7 | probable | 21.1519%，1,465,617 / 6,929,009。 |
| 8 | unknown | 7.2197%，500,253 / 6,929,009；另外保留已出现后缺失的不确定集合。 |
| 9 | future IPO leakage | 对已安装 listing/interval 边界发现 0 行；未掌握真实 IPO 日期的记录仍不能获得全市场零泄漏保证。 |
| 10 | later-delisted 保留率 | 后来消失候选 9,976/9,976 保留；四个确认上市交易终止案例的 membership/价格/特征/资格检查 4/4。 |
| 11 | ticker reuse 冲突 | 4,824 个 ticker 有多个 ID（包括保守碎片）；涉及 8,893 个普通股候选 ID；accepted price 的跨 ID 区间错误 0 行。 |
| 12 | lifecycle unresolved | 普通股风险/候选记录 11,839；含 9,972 个未解释观察终点，不是 11,839 起确认法律事件。 |
| 13 | price raw coverage | ticker/date 原始来源命中 32.6085%；全部独立口径绑定行情可用性 79.9471%。 |
| 14 | accepted coverage | 906,514 个 accepted raw rows，占全历史普通股 member-days 13.0829%。 |
| 15 | delisted price coverage | 后来消失候选 member-days：legacy bounded 26.2383%，accepted raw 3.5002%；四个确认案例价格历史均保留。 |
| 16 | detected material actions | 11,852 个普通股风险/候选事件记录，包含观察结束和类别变化；真实物质事件完整性未获证明。 |
| 17 | resolved | 13 个已确认记录，占 0.1097%；现金/股票终止经济模型启用数为 0。 |
| 18 | survivorship audit 通过率 | 历史保留 100%；研究字段条件 17.4312%；三类样本不足 50，不能给整体审计 PASS。 |
| 19 | 当前整体 Tier | Tier 1 Exploratory PIT。 |
| 20 | 是否 Research-Grade | 整库尚未达到；既有有界研究证据继续保留，不把研究子集结论外推全库。 |
| 21 | 最大风险 | primary snapshot 造成的身份碎片、错误类别切换与不完整终止观察；继而影响 membership/issuer。 |
| 22 | 真实影响未来研究的风险 | 串 issuer、缺失消失股票的价格/特征、未知竞争者被过滤、未处理转换/终止、不同复权口径串接。 |
| 23 | Vendor-Grade 残余 | 每只普通稳定股的完整法律 class 文件、供应商级全球完整性证明、精细 legal effective/注销链和逐股 no-event certificate。普通股 A 没有要求这些；真实高风险例外。 |
| 24 | 可否 maintenance | 不可；8 个预设门槛只满足 3 个，小型冲突队列与足够退市样本尚未形成。 |
| 25 | 下一阶段 | 继续有限的来源级批量身份/成员修复与已确认案例增量补价；明确可信范围可做探索，暂不把整库作为正式通用策略输入。 |

## 真正重要的剩余工作

1. **批量辨别身份碎片与真实证券边界。** 8,893 个普通股候选 ID 命中多 episode ticker，并不全是真正 reuse。需要按有日期的 issuer/class/原始目录证据交叉验证短缺口；对无强证据的记录不合并。不把 73,077 个其他类别风险 ID 变成逐个人工任务。
2. **集中处理真实 issuer/类别/交易所风险。** 自动发现 22 个多 CIK 身份、618 个类变化 ID、131 个未验证交易所变更 ID；优先有官方结构化事实的批量处理和少数定点调查。TTGT 已隔离但还需独立证券边界重建，不能拿注记代替新 class 事实。
3. **丰富有证据的历史终止/M&A/rename 样本。** 完成 Form 25/交易所/issuer/FINRA 的有效批量来源接入，分清停止上市交易、OTC continuation 和股权注销，并验证少数真实持有跨事件所需经济模型。不要要求普通稳定股逐股无事件法律证书。
4. **只补身份与成员已确认的行情缺口。** 旧 BBBY 已完成；保持 raw 来源/version/asof/provenance 独立。原 split 系列不被假装成 raw，831 个已发现的源价格冲突不自动选赢家。

普通稳定股票的法律文件不是这次低通过率的主要原因；大量保守 episode 碎片、观察冲突与实际数据缺失才是原因。解决路径是来源批量证据与确定性规则，不是继续扩展策略框架或开几千个网页。

## 验证与冻结产物

- 新增 37 个数据库测试用例，覆盖所要求的 18 类合同；完整 Native-inclusive suite **544 passed**，88.47 秒；只有既有 websockets.legacy 弃用警告。
- 现有 QC 测试曾假设本地没有真实 smoke；已改成用 mock 测缺少前提分支，实际 smoke 文件完全保留。
- inspection notebook 所有 code cells 在最新实际数据库上执行成功；新 BBBY feature schema 与原 `RESEARCH_COLUMNS` 一致。
- 数据、raw responses、特征、详细样本均保存在本地；Git 只提交代码、合同、聚合 scorecard、公开证据引用及 hash。

当前本地版本：`bd743ee2310659c839afe1b56fa6ae8fb287d1fc4ed744347ee7db7b83f882c5`。
数据库 SHA-256：`a41a38992bfd2e0e3fc1a91838725ff9f851bde760ed5aaf6a7fc167abced641`。
入口：`data/pit/construction/current.json`；实体库：`data/pit/construction/versions/bd743ee2310659c839afe1b56fa6ae8fb287d1fc4ed744347ee7db7b83f882c5/historical.duckdb`。
回滚保留父版本；新 raw 数据不改变原 root master/feature store 或任何历史 Run。
