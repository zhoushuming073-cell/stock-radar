# PIT 数据可信度与退出证券行情专项验收 · 2026-10-07

本轮复用首版 Security Master / universe adapter / feature store contract，已
安装一批有官方身份证据的证券和退出交易所前行情，并打通同一 PIT 数据库的
特征、Scanner 和前瞻标签价格读取。**数据可信度仍为 PARTIAL，正式 PIT LEAN
组合执行仍 BLOCKED；不宣称消除了幸存者偏差。**

首版 [验收报告](pit-acceptance-2026-10-07.md) 保持原样。唯一开放总账仍是
[当前总账第 3.2 节](../journey-2026-09-30-0651-📌当前总账.md)。本报告保存本轮证据，
不建立第二套 backlog。基线为 `main @ e70bdbc60c73b7812787b5470f7a57aede4f4dfb`。

## 1. 实际交付与数量变化

| 项目 | 首版 | 本轮安装版 |
| --- | ---: | ---: |
| 历史 mapping intervals | 90,339 | 90,339 |
| 保守 security episodes | 88,344 | 88,340 |
| verified identity intervals | 4 | 17，涉及 9 个证券身份 |
| unresolved identity intervals | 90,335 | 90,322 |
| unknown type intervals | 5,709 | 5,707，eligible 为 0 |
| multi-episode tickers | 4,826 | 4,825 |
| verified multi-symbol identities | 1 | 2 |
| eligible common episodes | 15,265 | 15,263 |
| common 无行情 episodes | 7,610 | 7,605 |
| common 观察区间价格完整 | 7,515 | 7,518 |
| common 价格部分缺失 | — | 140 |
| 少于 126 条历史行情 | 9,647 | 9,642 |
| expected common security/sessions | 6,892,718 | 6,892,714 |
| 缺失 common security/sessions | 1,421,296 | 1,419,830 |
| PIT feature rows / identities | 5,471,422 / 7,655 | 5,472,884 / 7,658 |

新增真实行情 **1,462 条**，全部实际进入特征计算。缺失数减少 1,466 包括这
1,462 条及官方交易边界修正减少的 4 个 expected sessions；无价格 episodes
减少 5 包括 3 个实际补价身份及 2 个官方证据合并产生的计数变化，不能说
“补齐了五只股票”。身份数变化不代表从分母删除缺价证券。

Master 观察范围为 2021-09-01–2026-10-07；**价格覆盖统计的真实 SPY session
calendar 只到 2026-09-28**。区间完整不是全上市生命周期完整，也不认证 supplier
价格身份。跨年份/交易所表中同一身份可能重复出现，不能简单相加为全局人口。

## 2. Identity / 分类 / 事件证据

`config/pit_trust_evidence.json` 保存 10 个官方来源的 URL、文档版本、原始
SHA-256，13 个 issuer/class/exchange/date 范围映射以及 15 个事件。
`enrich_pit_evidence.py` 离线核验原始文件 hash 后生成 17 个映射决策。
支持 verified / strongly_supported / inferred / conflicting / unresolved；
**仅 verified 的证券级证据可跨 symbol 合并**。名称相似仅用于找到 observation。

| 真实案例 | 身份与边界 | 官方证据 |
| --- | --- | --- |
| FB → META | CIK 1326801、Class A；2022-06-09 换代码，同一 security_id | [NASDAQ ECA2022-125](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-125) |
| ATVI | CIK 718877 common；2023-10-13 合并/开盘前停牌，最后交易日 10-12 | [issuer SEC 8-K](https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b) |
| TWTR | CIK 1418091 common；2022-10-27 合并，10-28 开盘前停止 NYSE 交易 | [issuer SEC 8-K](https://d18rn0p25nwr6d.cloudfront.net/CIK-0001418091/84881052-8f1d-4857-bda8-2fdb55ebce68.pdf) |
| SPLK | CIK 1353283 common；2024-03-18 收购完成/停止交易，最后交易日 03-15 | [Cisco completion disclosure](https://s21.q4cdn.com/812015656/files/doc_news/Cisco-Completes-Acquisition-of-Splunk-2024.pdf) |
| 旧 BBBY | CIK 886158 common、NASDAQ；2023-05-03 停牌，05-02 最后可交易日 | [Nasdaq notice](https://ir.nasdaq.com/node/106476) |
| OSTK → BYON → 新 BBBY | CIK 1130713 common；2023-11-06 改为 BYON/转 NYSE；2025-08-29 改为 BBBY | [issuer transfer/rename](https://investors.beyond.com/news-events/press-releases/news-details/2023/Overstock-Heads-into-the-Future-as-Beyond/default.aspx)、[2025 10-Q](https://s203.q4cdn.com/409549452/files/doc_financials/2025/q3/BBBY-2025-09-30-10Q-2025-EDGAR-FINAL.pdf) |
| PLTR | CIK 1321655 Class A；2020-09-30 direct listing，2024-11-26 NYSE→NASDAQ | [2024 10-K](https://investors.palantir.com/files/2024%20FY%20PLTR%2010-K.pdf) |
| NVDA | CIK 1045810 common；10:1 split 的交易 ex-date 为 2024-06-10 | [issuer split FAQ](https://investor.nvidia.com/files/doc_downloads/2024/06/nvidia-2024-stock-split_faq_investors.pdf) |
| BABA | CIK 1577552、NYSE ADS，每 ADS 对应 8 股 ordinary；default common 排除 | [issuer FAQ](https://www.alibabagroup.com/en-US/faqs-investor-information) |

新旧 BBBY 的 CIK、股票类别范围和交易所不同。收购旧公司的品牌/IP 不是股票
身份延续，两者不会串价格、特征或标签；新公司的 OSTK/BYON/BBBY 则按已验证
日期共享 ID。无法覆盖的末尾 observation 不人为延长为 verified。

`observed_first/observed_last` 独立保存；first/last snapshot 不填成 IPO/delist。
本轮事件为换代码 3、合并 3、停牌 4、转所 2、实际 listing 2、split 1。
已知 listing 字段为 3 个区间/2 个证券；**正式法律 delisting date 仍为 0**。
停牌、Form 25 提交、合并完成和法律退市生效分开处理。PLTR direct listing
不称为 IPO。原有首版不够范围的 unknown META observation 继续 unresolved。

分类 provenance 在每个区间保存 `classification_source/confidence`。已验证
common 区间 16、ADS/ADR 区间 1；其余按首版名称/industry 规则保留 inferred，
unknown 保持 unresolved + ineligible。完整类型统计见附录和本地分类报告。

Multi-episode 自动候选分类：短期缺失恢复 3,034、较长 source gap 恢复 2,254、
类型变化 2,306、转所 82、无法判断 1,001、已验证 ticker reuse 1。
类别可重叠，不能相加当作分区；跨 symbol rename 单独为 3 个官方事件。
这些候选不自动 merge，4,825 个 ticker 中的大部分仍需核验。

## 3. 实际退出证券 OHLCV 与数据源限制

免费来源为 [post-no-preference/stocks on DoltHub](https://www.dolthub.com/repositories/post-no-preference/stocks)，
固定 SQL `AS OF 'vt6qeesk27k07492k5jc5b7p04mf0s6o'`（2026-10-06
05:30:37.288 UTC）。该版本 LICENSE.md 为 **CC-BY-SA-4.0**；价格衍生数据
再分发须保留署名及相同许可。本轮数据库仅本地保存，不上传价格 dump。

| Symbol | 研究起日 | 已验证最后交易日 | bars | 最后 close | 预热后 tradability-pass feature rows |
| --- | --- | --- | ---: | ---: | ---: |
| ATVI | 2021-09-01 | 2023-10-12 | 532 | 94.42 | 407 |
| TWTR | 2021-09-01 | 2022-10-27 | 292 | 53.70 | 167 |
| SPLK | 2021-09-01 | 2024-03-15 | 638 | 156.90 | 513 |

三只在原 research bars 中均无数据；补齐范围内全部真实 SPY sessions，
无额外周末/重复日。来源 date 是美国交易 session label，下载时刻另存收据。
按 source symbol → 官方 identity → 有效日期范围 → security_id 导入独立
`external-prices.duckdb`。核验 source SQL 原始 hash、聚合 payload hash、
license pin、OHLCV 合法性及真实 session 集合；HTTP 200 的 RowLimit 仍拒绝。
跨身份、范围外、缺日、raw/聚合突变、未审价格口径、split、许可不明均拒绝。
同一身份不能未经审核将 legacy 与新 source 两段价格拼接。

价格口径证据：NVDA 2024-06-07 raw close 1208.88、06-10 121.79，来源
split 表为 10:1；MSFT 2024-08-14/15/16 的 close 与独立 Yahoo quote
交叉核对，而非 dividend-adjusted close。**这是 strongly_supported 的来源
探针，不是全部历史价格的官方认证。** MSFT volume 在两源间约差 6–10%，
未认证 consolidated SIP；该差异不能隐藏。三只补价区间未发现 split，原始
价格在这些区间等价于研究使用的 split-only 价格。通用 split/dividend factor
流水线仍未验证；dividend 表也不能宣称完整。

Stooq 返回浏览器验证页面，未绕过；Yahoo FRCB 的早期 NYSE 历史是回溯别名，
身份/授权未达到接收标准，留在 quarantine。SEC 直接请求 HTTP 403 时未绕过，
使用已核验的 issuer CDN/交易所公开文件。Git 三个辅助/主数据树未找到 LICENSE，
继续只保存本地 raw 和完整 symbol 导出。

官方文档中的 95 / 54.20 / 157 cash consideration 没有被实现成 settlement。
三只最后 close 不等于 payout；没有价格归零、自动现金补偿或伪造 terminal exit。

## 4. 差异解释、缺口优先级与 source conflict

价格队列：Tier 1 **7,693**、Tier 2 **278**、Tier 3 **73,077** 个存在价格
缺口的 identity。Tier 1 保留 eligible common + 未知流动性，表示潜在影响；
Tier 2 以已有行情估算的中位 dollar volume 低于冻结研究 $1M 下限；Tier 3
为默认不 eligible。它不是全市场流动性认证，也不把当前缺价等同于低流动性。
辅助 delist 声明只匹配事件日期附近的 episode，不能跟着复用 ticker 永久迁移。
附录列前 N 项；日期限定的辅助声明仍 unresolved，不能称已验证退市。

12 个历史日期重新运行 production `scan_frames` 和完全相同 Strategy 2。
只提供信号日 OHLC/session，future labels censored，未检查未来收益。
候选数仍与首版相同；新行情增加早期 available features，但三只不改变这
12 次抽样的选中名单。实际 Scanner 漏斗单列 membership、no_price、
insufficient_warmup、feature_unavailable、strategy_rejected；warm-up 阈值仍
为既有 126，策略选择逻辑未改。没有把缺价格证券移出 universe 分母。

`current-vs-pit-reasons.json` 区分已证实 later exchange retirement、future
listing、rename/reuse 生效前、产品过滤、identity/source scope unresolved；
价格/预热/策略影响另由 Scanner 漏斗记录。没有证据时不把 Current-only
叫 future IPO，也不把 source scope 差异当作纯 survivorship bias 贡献。
Scanner 候选 ID 可追加给价格队列作为有界 12-session 使用频率证据。

13 条 identity/event conflict 保存值 A/B、source A/B、优先证据、原因和状态：
10 条官方边界与 Screener lag 修正；BBBY 停牌/法律退市日期混淆；BBBY 股票
复用/品牌收购混淆；VMW 辅助单值 payout 142.5 未核实。另有价格源 volume
差异和 raw/adjusted 探针，保存在 raw public-price adjustment receipts。

主源审计仍是 1,281 个 accepted snapshots、583 个无新快照 calendar days、
最多 4 日有界 carry、0 个整日异常 rejection。0 rejection 不证明没有小规模
漏抓。NASDAQ Screener 的 NASDAQ/NYSE/AMEX 过滤 population 不是官方完整
historical directory；无 OTC、native instrument IDs/type flags，观察人口和
unknown 数量随年变化。UTC commit availability 使用收盘后/下一 calendar day
保守处理，不能当盘前已知的证券清单。年度主源 profile 见附录。

## 5. Readiness 与 LEAN 边界

| 维度 | 状态 | 验收数字与限制 |
| --- | --- | --- |
| Membership | PARTIAL | 90,339 区间；source-attested completeness=false；583 日 carry |
| Identity | PARTIAL | 17 verified / 90,322 unresolved 区间；unresolved 99.9812% |
| Classification | PARTIAL | 17 verified；5,707 unknown；unknown eligible=0 |
| Event | PARTIAL | 15 条事件；2 证券已知 listing；法律 delisting=0 |
| Price | PARTIAL | 3 只补价；common 仍缺 1,419,830 sessions、7,605 无价 episodes |
| CorporateAction | FAIL | 通用 factors 未验证；terminal economic models=0 |

十项 LEAN portfolio 放行条件均未在请求人口/持仓生命周期上完成全链路认证，
继续 FAIL/BLOCKED。真实 golden cases 通过研究边界验证，不代表 native PIT
portfolio parity 已完成。[LEAN map/factor/delisting 设计](../docs/PIT_LEAN_DATA_DESIGN.md)
依据本机 LEAN 源码固定 commit，只有非执行格式测试夹具。

## 6. 版本、复现、安装与代码耦合

```text
Master version: 509fe269e2e84a257f9b6d3116063f8a7d3f52ee8dec0adb236c8a192b95293d
Master CSV SHA-256: a6f1362eaa38ed8a0daf00273b858c4c9dbf5f476de35688868ff6fd86564569
Semantic universe fingerprint: 96004bbb8fb71f9e9ddee528be1f4de46d7a2b3918d86404c33051454465ff04
Eligible feature-input SHA-256: 9a407c1c22f4b3e4100631c761ec258b8851f048028d12b517ffb1fe3522ad62
PIT feature DB SHA-256: 8d5b8ee4af9b0f97b3bfc1de7295681c52e12d69fa2c52f4a808f3c0d6fcabc4
Source research SHA-256: b2565184a372c6ce7d5b448acebad3dfbad0bf51c77b785f5d0a342352d364c3
External prices DB SHA-256: 90d458e4396c58a017402f76efc6f3addf4ed51734bc1a815c957dbd99605a2c
Coverage v2 semantic SHA-256: ba7324120245ca761db2555f253d03e6e6f4f0a6c3a71e26a6d41ccf19f6ffd8
Price source commit: vt6qeesk27k07492k5jc5b7p04mf0s6o
```

新目录独立 replay 验证 version、CSV、完整 snapshot quality/evidence/lock、
feature-input mapping、universe fingerprint 一致，构建 receipt 时间不同。
两个目录的 coverage-v2 JSON 字节完全相同。修复原来 runtime timestamp 混入
fingerprint 的问题：规范化 manifest 排除 built_at/Stock Radar receipt commit；
sidecar 排除本地路径、物理 DuckDB 布局和 reviewed-reuse 历史。仍绑定 CSV、
source commits、代码/配置、raw evidence/price payload、source database hash。
**队列另冻结 physical feature DB SHA-256**；Scanner/Backtest worker 和消费
Scanner 的 manager 比对它，loader 再核验实际 DB bytes，不因语义指纹稳定
允许替换队列输入。旧指纹任务不会静默迁移。

实际特征计算首次生成在 `data/pit/normalized/c60d30.../pit-research.duckdb`；
随后两个 provenance-only master 修订的 eligible ID/date/listing/delist 输入
逐列一致，external bars 双向 EXCEPT 为空，经 source/config/DB hashes 核验
复用这些 immutable bytes。新 sidecar 明确保存 reviewed_reuse 和原 feature
builder hash。不会把重新绑定描述成重新计算。主源及 feature formula/config
未改；原 legacy DB 和首版 PIT artifact 保留。
原计算时的完整 builder 源码已按其 SHA-256 保存在
`data/pit/raw/build-code/999b0abb5de7a4b8294e19b41d3f62a5e5efb749658956b181d5db7523e0b0df.py`；
与当前版本的差异只是后加的旧 external-price bytes 复用保护，计算函数未改。

已备份首版根目录三文件到 `data/pit/install-history/<first-version>/`，安装
新版 `data/security-master.csv` / manifest / feature-sidecar。无 queued/running/
cancel-requested Scanner/Backtest 时静默重启原 API，`/health` 正常，
`/api/lab/universe-status` 返回本报告 version/fingerprint、完整六维 scorecard
及 `lean_pit_execution_ready=false`。一日真实 readiness 见本地 witness。
默认 Current Snapshot、UI、用户后台计划任务保持原设置。

本轮修复 PIT 前瞻标签价格仍读 legacy bars 的耦合缺口：现在特征及 host-only
标签 OHLC 都走 `pit_database_for` 的同一 source/hash/identity gate，新退市
行情实际可被读取，ticker reuse 后价格不接给旧 ID。没有改标签公式或收益
标准，没有解除 LEAN 拒绝。

## 7. 自动测试与旧数据库保护

最终 **342 tests passed**，含 `STOCK_RADAR_TEST_LEAN=1` 本机原生 Current
Snapshot LEAN golden/parity/empty/cancellation；一个既有 websockets deprecation
warning。测试新增真实 observation scope、BBBY 复用、ADR 排除、转所、事件
边界、原始/聚合 hash、许可/RowLimit/复权拒绝、feature/forward coupling、
全漏斗分母、独立目录确定性、physical queued artifact gate、coverage/缓存
突变拒绝和非执行 LEAN map/factor 格式。实际 master/feature/OHLCV 九案例
另外由 `verify_pit_golden_cases.py` 核验，证据并非只依赖 synthetic tests。
真实 FB 2022-06-08 close 196.64 → META 06-09 close 184.00，首条 META
`ret_1=-0.06427990235964187` 与价格连续计算相符，未在换代码时重置。
新旧 BBBY 在现有实际 PIT bars 都仍为 0；本轮真实证据核验身份分开，价格/
标签隔离由 adversarial case 验证，不将没有行情的真实案例称为已补齐。

`strategies/full_strategy2_v1/`、research/backtest thresholds、ranking/score、
MarketGuard、止盈/止损/持有期、`src/radar/lean/` 和 site 均无本轮 diff。
large raw/normalized DB、API/Run receipts 不提交 Git。

**不能将“四库与首版 hash 全部未变”写成通过。** `market.duckdb` 已被既有
`StockRadar-DailyUpdate` 在本任务前更新：08:30 启动、08:36:09 成功；新 brief
创建于 08:37:45；market mtime 为 08:35:06。新增 12,531 bars、更新 bars=0。
本轮没有写四个旧库，也不回滚这批新增数据。其余三个旧库 SHA-256 与首版
一致，四库都 read-only 打开/查询成功。market 本轮前后新 hash 稳定。

| 数据库 | bars | 与首版比较 |
| --- | ---: | --- |
| market.duckdb | 4,656,573 | 定时更新先于新任务，+12,531；本轮不写入 |
| phase2-research-v2-frozen.duckdb | 6,133,793 | bytes unchanged |
| phase2-research.duckdb | 12,151,417 | bytes unchanged |
| phase2-source-snapshot.duckdb | 6,133,793 | bytes unchanged |

market 当前 SHA-256 为
`0043f66ea4ac75c14d1a65e2765cb314d8cc19299f64abe390fd58e30caad60d`。
完整各库 hash/mtime、定时任务状态/时间线在本地验收收据。

## 8. 本地审计文件与可复现命令

原始官方文件：`data/pit/raw/official-evidence/<sha>.raw` + source-index receipt；
价格：`data/pit/raw/public-prices/<sha>.raw`、queries、license/adjustment receipts；
候选/失败来源：`data/pit/raw/trust-research/`；normalized：
`data/pit/normalized/<master-version>/`；报告：`data/pit/reports/<master-version>/`。

该 report 目录包含 membership-summary、daily-universe、coverage-v2 JSON/
interval CSV、identity-classification-events-conflicts、episode-candidates、
price-priority-queue、current-vs-pit-reasons、scanner-selection-comparison、
golden-cases、fresh-directory-replay、installation-receipt、installed-readiness、
local-api-reload-check、final-original-database-check 以及 pre-task daily receipt。
所有 identity decision 的 source commit/version/hash 可追溯。官方各文档和
price payload 的完整 hash 在 tracked config，附录列 source hashes。

离线 enrichment、接受价格、特征绑定、audit、golden、Scanner/priority 命令
见 [现有 contract 的扩展](../docs/PIT_SECURITY_MASTER.md)。下一轮仍按当前
总账推进 identity/classification → 优先退出证券价格 → 正式事件 → 通用
factors/terminal/native reconciliation；不按收益选择/回滚数据。

<!-- GENERATED_AUDIT_APPENDIX -->

## 附录 A. 年份 × 交易所 eligible-common 覆盖

Active 为同一身份在 master 末日仍被观察为 eligible；不是官方全市场幸存认证。
Retired 指已验证后来停止该交易所交易；不与正式法律 delisting 合并。
Complete/Partial/None 是该年 local session 范围。每组正式 delisting count=0，
price-before-legal-delisting complete 为 unknown/null，而非伪造 0% 完整率。

| 年 | Exchange | Common | Active | Retired | Verified / Unresolved | 完整 / 部分 / 无价 | Terminal last price | 缺 sessions |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: |
| 2021 | AMEX | 245 | 125 | 0 | 0 / 245 | 156 / 0 / 89 | 0 | 6,656 |
| 2021 | NASDAQ | 3,865 | 1,729 | 3 | 6 / 3,859 | 2,112 / 4 / 1,749 | 2 | 111,517 |
| 2021 | NYSE | 2,385 | 1,362 | 1 | 2 / 2,383 | 1,591 / 3 / 791 | 1 | 54,628 |
| 2022 | AMEX | 300 | 148 | 0 | 0 / 300 | 181 / 0 / 119 | 0 | 18,789 |
| 2022 | NASDAQ | 6,578 | 1,889 | 3 | 6 / 6,572 | 2,536 / 12 / 4,030 | 2 | 337,734 |
| 2022 | NYSE | 3,096 | 1,451 | 1 | 2 / 3,094 | 1,713 / 8 / 1,375 | 1 | 153,290 |
| 2023 | AMEX | 330 | 159 | 0 | 0 / 330 | 198 / 1 / 131 | 0 | 16,214 |
| 2023 | NASDAQ | 4,527 | 2,053 | 3 | 6 / 4,521 | 2,547 / 15 / 1,965 | 2 | 221,055 |
| 2023 | NYSE | 2,365 | 1,546 | 0 | 2 / 2,363 | 1,722 / 9 / 634 | 0 | 94,538 |
| 2024 | AMEX | 287 | 189 | 0 | 0 / 287 | 223 / 1 / 63 | 0 | 10,948 |
| 2024 | NASDAQ | 3,648 | 2,251 | 1 | 4 / 3,644 | 2,704 / 10 / 934 | 1 | 153,919 |
| 2024 | NYSE | 2,104 | 1,639 | 0 | 2 / 2,102 | 1,768 / 1 / 335 | 0 | 64,587 |
| 2025 | AMEX | 321 | 223 | 0 | 0 / 321 | 264 / 0 / 57 | 0 | 6,683 |
| 2025 | NASDAQ | 4,147 | 2,628 | 0 | 3 / 4,144 | 3,382 / 1 / 764 | 0 | 100,678 |
| 2025 | NYSE | 2,159 | 1,767 | 0 | 1 / 2,158 | 1,953 / 0 / 206 | 0 | 36,726 |
| 2026 | AMEX | 310 | 255 | 0 | 0 / 310 | 284 / 5 / 21 | 0 | 1,934 |
| 2026 | NASDAQ | 3,841 | 3,038 | 0 | 3 / 3,838 | 3,505 / 60 / 276 | 0 | 22,673 |
| 2026 | NYSE | 2,092 | 1,882 | 0 | 1 / 2,091 | 1,984 / 9 / 99 | 0 | 7,261 |

## 附录 B. 类型与 confidence（区间计数）

| Type | Inferred | Verified | Unresolved |
| --- | ---: | ---: | ---: |
| common | 15,527 | 16 | 0 |
| adr | 694 | 1 | 0 |
| etf | 34 | 0 | 0 |
| etn | 31 | 0 | 0 |
| preferred | 2,012 | 0 | 0 |
| warrant | 22,239 | 0 | 0 |
| unit | 17,797 | 0 | 0 |
| rights | 2,012 | 0 | 0 |
| spac | 24,269 | 0 | 0 |
| closed_end_fund | 0 | 0 | 0 |
| test | 0 | 0 | 0 |
| other | 0 | 0 | 0 |
| unknown | 0 | 0 | 5,707 |

## 附录 C. 主源年度观察 profile

| 年 | Accepted snapshots | Population min–max | Unknown min–max | Exchanges |
| --- | ---: | --- | --- | --- |
| 2021 | 87 | 7,869–8,300 | 629–665 | AMEX,NASDAQ,NYSE |
| 2022 | 251 | 8,030–8,601 | 604–643 | AMEX,NASDAQ,NYSE |
| 2023 | 251 | 7,298–8,093 | 560–614 | AMEX,NASDAQ,NYSE |
| 2024 | 252 | 6,930–7,417 | 551–579 | AMEX,NASDAQ,NYSE |
| 2025 | 251 | 6,817–7,089 | 526–571 | AMEX,NASDAQ,NYSE |
| 2026 | 189 | 7,000–7,204 | 506–540 | AMEX,NASDAQ,NYSE |

## 附录 D. 真实生产 Scanner 选择与漏斗

已选中 ID 的缺价队列附加文件 `price-priority-scanner-witnesses.json`
覆盖 12 日，0 个缺价 identity 至少在抽样中被选中过；未命中不代表无研究影响。

| 日 | Membership | Available features | 无价 | 预热不足 | 特征缺口 | 策略拒绝 | Current / PIT 选中 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2021-09-24 | 5,645 | 3,631 | 2,014 | 3,631 | 0 | 0 | 0 / 0 |
| 2021-11-30 | 5,788 | 3,745 | 2,043 | 3,745 | 0 | 0 | 0 / 0 |
| 2022-06-07 | 5,990 | 3,896 | 2,094 | 206 | 4 | 3,661 | 34 / 25 |
| 2022-12-20 | 5,846 | 4,013 | 1,833 | 217 | 1 | 3,781 | 30 / 14 |
| 2023-07-19 | 5,292 | 4,059 | 1,233 | 172 | 1 | 3,874 | 18 / 12 |
| 2023-11-28 | 5,229 | 4,131 | 1,098 | 181 | 0 | 3,941 | 11 / 9 |
| 2024-04-30 | 5,215 | 4,249 | 966 | 210 | 0 | 4,029 | 16 / 10 |
| 2024-09-03 | 5,175 | 4,307 | 868 | 205 | 0 | 4,100 | 3 / 2 |
| 2025-04-10 | 5,183 | 4,516 | 667 | 283 | 1 | 4,231 | 2 / 1 |
| 2025-07-30 | 5,199 | 4,634 | 565 | 331 | 1 | 4,297 | 9 / 5 |
| 2026-05-01 | 5,195 | 4,998 | 197 | 407 | 1 | 4,535 | 69 / 55 |
| 2026-08-27 | 5,189 | 5,155 | 34 | 407 | 0 | 4,715 | 50 / 33 |

## 附录 E. 优先队列前十项（基础缺口排序）

以下是日期相符的 secondary claims + 缺价观察候选，身份和真实退市仍 unresolved。
均无本地价格，流动性 unknown，Tier 1 表示潜在影响；不是高流动性认证。

| Symbols | Tier | 缺 sessions | Secondary claim |
| --- | ---: | ---: | --- |
| MCW | 1 | 1,184 | True |
| APLS | 1 | 1,181 | True |
| SEE | 1 | 1,155 | True |
| HOLX | 1 | 1,154 | True |
| CTRA | 1 | 1,149 | True |
| EXAS | 1 | 1,144 | True |
| CFLT | 1 | 1,140 | True |
| ALEX | 1 | 1,137 | True |
| THS | 1 | 1,116 | True |
| CMA | 1 | 1,109 | True |

## 附录 F. 原始内容 hash 与 source pins

Dolt license raw query SHA-256: `9d4c8edfd801f6f57a67d4660fd7e149e4c9f3273b6931ee4857b73e7ff2d1aa`。
价格 payload SHA-256 在 `config/pit_public_price_review.json`，每个 SQL 响应的
独立 raw hash 在 payload queries。官文 raw hash 如下：

| Source key | Document raw SHA-256 |
| --- | --- |
| atvi | `c2f3d7ce46bddd7e933c75c490231116ff7047bdbdcb4ac123e85e81dbbfddd4` |
| twtr | `f5a81085e8889ce5a4ba8a1be59ce2605ac2257444c1b302f8a0b2bc10639d65` |
| splk | `7e305106e8161a970894dd840aa3bcced17fb1e7865bc7c895133ca915de6827` |
| ostk | `7b2a5af3931b7f2dba8c554dd4d4e360b20b877cc600c3cf066f3c7c77c27f0d` |
| bbby-new | `f9d070c06b94aef2f87de6a75421734a0f5be2f1f1440802c3730c55355d4b02` |
| bbby-old-nasdaq | `87020cf438526d03e0d5e283e80ac707208293896b9892c35c0c14fc7b542fb7` |
| pltr | `d525792fef879690ce3d052eea1540047127572b8b31fad6678cf39fbb4703b8` |
| nvda | `7f6b7651d7874784cd7666464431395e62a9570a139932183470094c4d51faf3` |
| baba | `1b454e6ec23356dd98e923aa6e506009dc18b08822bfdb050f20ac474f98177a` |
| fb | `5ee92081f4966749ed40e1d4cae9bc6add4207c5cf115e16d5ca87302227a928` |

| Git source | Commit |
| --- | --- |
| symbols | `157439344501b2020cc2ae37addd6f628fa00699` |
| delisted | `37b4198b6c5cc4a4354aad6f71c2aeac631703b2` |
| reference | `a3eb36f951f9796c60c0a4c6bb70f13e50d9da6b` |

本地核心验收 artifact 的文件 SHA-256（收据中的 wall time 不是内容版本）：

| Artifact | File SHA-256 |
| --- | --- |
| scanner-selection-comparison.json | `9756e73257a1fbd6369606230023d893837f6dddcfe0a1e6db4ad4d3f7762fd8` |
| golden-cases.json | `4f98d5acee311da75736f4f789301964b992cf2cc2a2bd18de21c29401948ff8` |
| fresh-directory-replay.json | `d90b0c3af7f3ff0e147e5ac179992c7eadfa08c9123fbbd3de61d491e45f520f` |
| price-priority-scanner-witnesses.json | `448a77bf1f8c93ba668248d5a1a063f617bad50a36052005b5ef4e3d08131d67` |
| installation-receipt.json | `29e6929b019bfe727da5bcbc41627fb83424c711840a64fa8f740ef1dd1062e6` |
| local-api-reload-check.json | `8ff8769006968f2ceb9bf7b76fdd54426e1973c21460b3fc391816f0ea323735` |
| final-original-database-check.json | `1511f68aaf1d8eaf290b2ed76bf29f2bfa97319537a96ec7cf2ab2c68ff0c005` |
