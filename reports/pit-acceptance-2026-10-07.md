# Stock Radar PIT 数据库专项验收 · 2026-10-07

> 本机日期：Asia/Shanghai。整体状态：**工程第一版完成，真实数据可信度部分完成**。
> `reconstructed_membership_exploratory` / `source_dependent_incomplete`，不是 survivorship-bias-free。
> 唯一当前 backlog 在 [当前总账](journey-2026-09-30-0651-📌当前总账.md) 第 3.2 节；本报告是验收证据。

## 1. 结果与架构

已生成 2021-09-01–2026-10-07 的区间型历史 master，接入现有 `point_in_time` adapter。
旧 `current_snapshot`、四个旧 DuckDB 和旧研究证据保留。PIT 使用独立因果特征库，策略/参数、网页和 LEAN 执行算法没有修改。
历史 Scanner 在生产 `scan_frames` → 策略 adapter 路径消费当日证券集合；真实 RunManager 已成功排队 PIT Scanner，精确指纹与本报告一致。队列验收使用独立 SQLite，检查后取消，没有启动全期评价或污染正常 Run History。

在本机独立 LEAN 上重新运行完整 pytest：**314 passed，1 warning，34.10 秒**；警告为既有 `websockets.legacy` 弃用提示。此为本地证据，不是 GitHub CI。
LEAN PIT 请求实际返回 `LEAN PIT terminal/corporate-action support is not yet validated; use Current Snapshot`。没有研究收益、调整阈值或生成虚构终止支付。

## 2. 先审计后修改

[初始架构审计](pit-initial-audit-2026-10-07.md)基于 `main @ 3521ce3`，已与远端核对。当前资产来源为 Alpaca active US equities，研究库用这批存续资产构建历史特征；每日因果筛选仍无法复原未进入当前 cohort 的退市证券。原始资产、日线与特征主要按 ticker 作键，缺少稳定证券身份。现有 PIT contract 已具备日期映射、终止事件边界和 fail-safe，但此前没有实际安装 master，也缺少防止 ticker reuse 串入滚动特征的独立 store。

本轮核心实现为 `0b0f50c`；安装路径修复及回归为 `99c9282`。
安装验收暴露 feature sidecar 的错误目标目录，修复后已实际验证 RunManager。初始失败没有绕过安全检查，也没有将缺少 sidecar 的模式当作可运行。

## 3. 数据源审计

| 来源 | 固定提交 | 用途与边界 |
| --- | --- | --- |
| [rreichel3/US-Stock-Symbols](https://github.com/rreichel3/US-Stock-Symbols) | `157439344501b2020cc2ae37addd6f628fa00699` | Primary；历史 Git 快照，NASDAQ/NYSE/AMEX full JSON |
| [YLiu95/delisted-equity-data](https://github.com/YLiu95/delisted-equity-data) | `37b4198b6c5cc4a4354aad6f71c2aeac631703b2` | Secondary；514 条 US 退市/复用声明，不能认证全市场 |
| [Quant-Lodge/ticker-reference-data](https://github.com/Quant-Lodge/ticker-reference-data) | `a3eb36f951f9796c60c0a4c6bb70f13e50d9da6b` | Secondary；18,210 条 lookup，1,509 个无有效日期的 rename 候选，禁止自动合并 |
| SEC EDGAR / NASDAQ Trader | 小型已审阅证据文件 | FB→META Class A 官方有效日期；不代表全量 SEC 下载成功 |

Primary 仓库最早历史提交为 2021-01-30；本轮使用 1,281 个有效日快照（含 2021-08-31 前置观察），最后观察为 2026-10-06。
实际工作流调用 NASDAQ **Screener**，不是穷尽官方 Symbol Directory。cron 是 midnight UTC，不能依据 README 误认 midnight Eastern。commit 以纽约收盘前后转换可用日期，收盘后观察不会进入同日 Scanner。

请求期共有 1,863 个日历日，其中 583 日没有对应的新快照；默认四日有界 carry 后无整段 source gap、无超过 15% 的总量异常。
**零 gap 是有界观察覆盖，不是每天实测、更不是完整市场认证。** 小范围消失/重现、代码描述变更或漏抓仍很频繁，因此保守 episode 数显著膨胀。

原始字段没有可靠证券类别/ETF/test 标识或 stable security ID。Native flags 若存在优先；实际主源主要依赖明确产品描述作 inferred 分类，无法识别的设 `unknown` 且不 eligible。默认只纳入 common；ADR、SPAC、ETF/ETN、preferred、warrant、unit、rights、closed-end fund、test 等留在审计但不纳入默认研究。部分基金/结构化产品可能仍被名称误判为 common，需官方历史类别补充。

三个固定树均未找到 LICENSE/COPYING，redistribution permission 未认证；原始数据/生成数据全部留在 ignored `data/pit/`，不提交大数据。SEC bulk 和 submissions 请求返回 403，错误收据已保留。
人工身份证据来自 [SEC 2022-05-31 8-K](https://www.sec.gov/Archives/edgar/data/1326801/000132680122000070/fb-20220531.htm) 与 [NASDAQ ECA2022-125](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-125)：2022-06-09 开盘前 FB 改 META。
映射限 Meta/Facebook **Class A** 名称范围，避免将未知同代码证券吞入；CIK 不自动等于所有 share classes 的 security ID。原始 FB 晚一天消失/META 晚一天出现的附近观察已按官方有效日纠正，保留两条 correction evidence。2022-06-16 只有发行人名称而无 class/type 的记录仍 unknown/unresolved/ineligible。

## 4. Master 数据质量

| 指标 | 本轮实际值 |
| --- | ---: |
| 区间数 | 90,339 |
| 保守 security episodes（不是认证证券数） | 88,344 |
| 身份未决区间 | 90,335 |
| unknown type 区间 | 5,709 |
| 同 ticker 多 episode，需复用/漏抓核验 | 4,826 个 ticker |
| 已验证跨 symbol identity | 1 个：FB/META Class A |
| 实际 listing/delisting date 已确认区间 | 0 / 0（未知，不能解释为无事件） |

连续同发行人/代码的观察可保留一个 episode，历史 exchange/type 变化另存区间；重新出现/未决名称变化分别建 ID。快照消失只终止 observed membership，不虚构 delisting。缺失抓取与未决身份不会被强行合并成漂亮的连续历史。

## 5. PIT × 本地行情覆盖

研究库截止 2026-09-28；master 观察延伸至 2026-10-07。以下 expected sessions **仅按本地 SPY 日历**计算，未对没有本地日历的后续日期声称完整价格覆盖。

| 范围 | episode 总数 | 无任何 bars | observed/local interval OHLCV 完整 | 不足 126 行 warm-up |
| --- | ---: | ---: | ---: | ---: |
| 全部产品/unknown | 88,344 | 59,194 | 28,745 | 81,396 |
| eligible common | 15,265 | 7,610 | 7,515 | 9,647 |

Eligible common 共有 6,892,718 个 expected security/session，缺少合格 OHLCV 1,421,296 个。
全产品/unknown 共有 9,551,622 个，缺少 2,876,006 个；6,656 个区间最后行情早于最后观察。
上市后才有价格/退市前结束的基于实际 event-date 指标均不可认证，因为真实 event dates 未确认；报告保留 unknown 的上下文，不能把计数 0 当作无缺口。

辅助 514 条 US 退市声明中，160 条日期处于请求期，158 条按本地原始 ticker 无退市日前 bars，只有 2 条最后价格在声明日前七个日历日内。
这是未验证的 secondary claim × raw-symbol proximity；有行情不证明身份一致，更不证明最终退市回收。该源不完整，因此不能推算全市场还缺多少真实退市证券。

No-price 记录仍在 master/审计分母。独立 PIT feature store 实际计算 7,655 个有行情 identity、5,471,422 行特征。
未决 episode 会重置滚动历史；不从同 ticker 的新证券继承特征/标签。Vendor symbol-only bars 尚未认证证券身份，拆股/分红/终止经济事件亦未完整认证。没有 forward-fill 终价、默认归零或虚构 payout。

## 6. 实际 Scanner 抽样对比

固定随机种子 `20261007`，每年两个本地交易日。策略 `full_strategy2_v1@1.0.0`，原配置及阈值不变。
表中的集合 intersection/PIT-only/Current-only 按 **all observed instruments** 与当前 ACTIVE US_EQUITY assets 比较；eligible common 与 available-feature 行另列，避免混淆类型和价格分母。

| 日期 | PIT 观察 | PIT common | Current assets | 集合交集 | PIT-only | Current-only | PIT 可用特征 | 候选 Current / PIT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021-09-24 | 7,949 | 5,645 | 14,397 | 4,271 | 3,678 | 10,126 | 3,628 | 0 / 0 |
| 2021-11-30 | 8,177 | 5,788 | 14,397 | 4,410 | 3,767 | 9,987 | 3,742 | 0 / 0 |
| 2022-06-07 | 8,541 | 5,990 | 14,397 | 4,638 | 3,903 | 9,759 | 3,893 | 34 / 25 |
| 2022-12-20 | 8,101 | 5,846 | 14,397 | 4,791 | 3,310 | 9,606 | 4,011 | 30 / 14 |
| 2023-07-19 | 7,649 | 5,292 | 14,397 | 4,909 | 2,740 | 9,488 | 4,057 | 18 / 12 |
| 2023-11-28 | 7,409 | 5,229 | 14,397 | 5,012 | 2,397 | 9,385 | 4,130 | 11 / 9 |
| 2024-04-30 | 7,127 | 5,215 | 14,397 | 5,136 | 1,991 | 9,261 | 4,249 | 16 / 10 |
| 2024-09-03 | 7,022 | 5,175 | 14,397 | 5,210 | 1,812 | 9,187 | 4,307 | 3 / 2 |
| 2025-04-10 | 6,853 | 5,183 | 14,397 | 5,475 | 1,378 | 8,922 | 4,516 | 2 / 1 |
| 2025-07-30 | 6,987 | 5,199 | 14,397 | 5,718 | 1,269 | 8,679 | 4,634 | 9 / 5 |
| 2026-05-01 | 7,101 | 5,195 | 14,397 | 6,372 | 729 | 8,025 | 4,998 | 69 / 55 |
| 2026-08-27 | 7,108 | 5,189 | 14,397 | 6,652 | 456 | 7,745 | 5,155 | 50 / 33 |

每个日期的候选 intersection、差集、security IDs、完整名单和漏斗另存本地 JSON。本轮各日期 PIT 候选均属于该日期 eligible master；缺少特征/价格的数量显式出现在 PIT 漏斗。
2021 两次零候选与冻结策略所需 warm-up/筛选相关，不能理解为没有历史证券。
只向评价层提供信号日 OHLC 和单日 calendar，前瞻 labels 被 censored，**没有读取未来收益**。

差异同时包括 source scope、产品类型、历史身份与 warm-up、当日人口排名以及缺价格，不能将差异比例直接叫作“幸存者偏差贡献率”。Current-only 也不能全部解释为未来 IPO。
由于缺可信 terminal/corporate-action/map inputs，没有运行 PIT LEAN portfolio 对比；候选变化可以独立查看，回测收益变化仍 blocked。

## 7. 版本与复现

```text
Master version: 6d21fe4b24dd17dd9d62863d3870bebe0a0b71f5c36355b3d86fd3f6c433e4fb
Master CSV SHA-256: 2aab8aad77fbb61914d74d33bf7f6d41079eb308cada7b803cf20fdb723f28c0
Universe + sidecar fingerprint: fc2f29dc26751bdda32581ae6e1b900dc618ed120d014721888db2babd5b2615
Source research SHA-256: b2565184a372c6ce7d5b448acebad3dfbad0bf51c77b785f5d0a342352d364c3
PIT feature DB SHA-256: 9d91758d39cdd7ab5b61c233e0930b0ba8d019316fbfed0ddad77886413ec8f7
Original importer code baseline: 0b0f50c65e4d2304740cd410e9f03ebc0b436863
```

归档路径：`data/pit/raw/`、`data/pit/normalized/6d21fe4b24dd17dd9d62863d3870bebe0a0b71f5c36355b3d86fd3f6c433e4fb/`、`data/pit/reports/6d21fe4b24dd17dd9d62863d3870bebe0a0b71f5c36355b3d86fd3f6c433e4fb/`。
Master version 绑定 importer source hashes、pinned source commits、raw snapshot-index hash、覆盖/有界 carry/证据政策与输出 CSV hash；原始构建时间/Stock Radar commit 单独记在 manifest。
同 lock/evidence/code 连续重建两次得到相同 version/CSV，安装前 replay 验证通过。Run 保存精确 universe provenance、source snapshot 与 sidecar；换源/改 master/改 feature DB 会被拒绝。

最终 master 只将一个 **ineligible unknown-type** META 记录从不够范围的 verified ID 改为 unresolved ID；与前一版 15,541 条 eligible feature-input mappings 完全一致。
经逐列比较 security_id/symbol/有效区间/listing/delisting/eligible，并核对源库、配置、feature builder 与输出 DB hashes 后，复用了前版 immutable feature DB。
新 sidecar 保存 `reviewed_reuse`，`feature-reuse-proof.json` 保存输入集合 hash；原版文件/DB没有改动。也可用正常 `build_pit_features.py` 从原始 bars 独立计算相同逻辑特征，不要求依赖复用。

现已在 `data/security-master.csv`、`data/security-master-manifest.json`、`data/security-master-feature-store.json` 安装完整 contract，保持默认 Current Snapshot。
本机原后端仍加载旧代码；确认正常 RunStore 的 Scanner/Backtest 均无 queued/running/cancel_requested 后，保留原启动参数静默重启 API。HTTP `/health` 为 200，`/api/lab/universe-status` 已返回 `point_in_time_available: true`，version/fingerprint 与本报告相同；收据为 `data/pit/reports/local-api-reload-check.json`。已打开的网页可正常刷新读取新状态。本轮不改 UI 或后台计划任务。
离线/联网/安装命令见 [PIT contract](../docs/PIT_SECURITY_MASTER.md)。每个新 master（含旧 certified 导入）必须配身份边界特征 sidecar；旧 survivor features 不能通过改名充作 PIT。

## 8. 正确性与旧系统验收

`CURRENT-P1-01`：队列/worker horizon 最大为 frozen research reserved sessions（当前 10）；10 允许、11 拒绝，实际 forward price/session 读取不能越过 evaluation_end。
`CURRENT-P1-02`：消费 Run 保存 signal-source 完整 provenance/hash，拒绝同 ID/version 但 strategy/manifest/adapter/相关宿主实现变化；worker 复核来源。
`CURRENT-P1-03`：Scanner/Backtest batch 捕获一次 snapshot/watermark/windows/config/master/terminal/feature-sidecar 哈希，提交前复核；源变更时零入队。

异常测试覆盖：日期成员、未来上市/退市后排除、rename identity、复用后的特征/标签隔离、名称范围、缺失快照/失败/有界 carry/异常跳变、历史 exchange、全部类别/unknown/test、重复/overlap、空 eligible、真实 ticker NA、fingerprint/mutation、排队 source 变化、no-price/censored、Current/PIT 分离、确定性重建与 future mutation、实际 Scanner 日期过滤、sidecar 三文件安装与拒绝覆盖。

四个旧库最终 SHA-256 与初始相同，read-only 打开及 bars 查询成功：

| 旧库 | bar rows | 状态 |
| --- | ---: | --- |
| `market.duckdb` | 4,644,042 | bytes unchanged / readable |
| `phase2-research-v2-frozen.duckdb` | 6,133,793 | bytes unchanged / readable |
| `phase2-research.duckdb` | 12,151,417 | bytes unchanged / readable |
| `phase2-source-snapshot.duckdb` | 6,133,793 | bytes unchanged / readable |

完整保存检查收据为 `data/pit/reports/original-database-preservation-check.json`。
`git diff` 已确认策略、research/backtest 参数、ingestion、LEAN 源码和 site 均无本轮变更。原生 LEAN golden/cancel/parity 等在 314 项完整测试中通过。

## 9. 验收界限与下一步

| 要求 | 证据 / 当前状态 |
| --- | --- |
| 任意覆盖日日期查询与版本复现 | 已实现观察集合；583 日 carry 明确记录，不能认证真实全市场集合 |
| 未上市不进入、退市前/后、复用不串价格/标签 | adversarial 自动用例通过；真实 IPO/全部 delisting 仍需官方核验 |
| 真实 ticker change 同一 security | FB/META Class A 已验证；其他 rename 候选未自动合并 |
| Scanner 真正按当日 membership | 12 个生产选股抽样 + 真实 PIT 排队、指纹、漏斗 |
| 缺价不静默删、价格缺口报告 | master 分母保留、all/common 分开、secondary delist proximity |
| Current→PIT 独立实验 | 冻结策略候选比较已完成；PIT 组合收益比较因执行数据不足未做 |
| 旧流程和证据 | 四库 bytes 不变、原生 LEAN 回归、Current Snapshot 并行 |
| survivorship-bias-free / 可信 terminal execution | **未达到；不作声明，不伪造数据** |

后续必须优先核验官方历史类别与 identity/event 日期，验证辅助 delist/reuse 声明，补足退市 OHLCV并校验 vendor 身份，最后才处理可信 terminal economics / LEAN map/factor/corporate-action adapter。
这些开放数据工作只在当前总账第 3.2 节维护；不新建重复 backlog，不调 Strategy 2 参数来美化结果。
