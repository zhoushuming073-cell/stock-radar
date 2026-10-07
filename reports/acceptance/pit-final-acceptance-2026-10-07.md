# Stock Radar PIT 最终工程验收 · 2026-10-07

**Run 级依赖、条件放行、数据工厂及原生事件会计已实现并验证；完整 Validation 的正式 PIT 组合仍 BLOCKED。项目尚不能升级为 `PIT research execution operational`。**

最终源码实现提交：`013bcc9bbf4e903681e55dcbf6f2ae1f4b6a913f`，已推送并重新读取 GitHub main 核验。任务开始及发布前重新读取的基线均为 `8a523be52d294ddb592ba768d45a29c4175205d8`。本报告和文档在后续文档提交中交付；不把文档提交的自引用 hash 编入文件自身。

保留前两份 [首版验收](pit-acceptance-2026-10-07.md)、[可信度验收](pit-data-trust-acceptance-2026-10-07.md) 原样。唯一开放 backlog 仍在 [当前总账 §3.2](../journey-2026-09-30-0651-📌当前总账.md)。

## 1. 最终链路与实际执行边界

Historical master → dated stable identity → independent PIT feature store → Historical Scanner → frozen signals → **full Run dependency closure** → six preflight gates → Stock Radar generated PIT execution dataset → native LEAN → normalized reconciliation。

`pit/run.py` 冻结完整 eligible 历史人口，包括缺价、未入选证券和实际 feature/rank participants，不能只认证最终买入名单。证券价格依赖包括逐日预热、信号日及所有潜在订单在评价截止前的持仓/退出范围；已有持仓、mapping/action/terminal、SPY/QQQ 前置历史及源 calendar 都进入闭包。未知上市日期不能通过截短观察历史免除预热；已验证上市日期才可以限定上市前不存在的 sessions。评价截止时仍在持仓的证券保留 mark，不补造区间外退出。

闭包保存 canonical hash 和文件物理 SHA-256。Master、feature sidecar、来源/价格库、官方 raw、许可/复权 review、策略/研究配置和信号不可替换。排队时锁定软件源文件；worker 再核验输入与重新计算的信号；native bundle 的 map/factor/zip/index 另有 hash，结果导入后再核验依赖。

Global 不完整不会无条件否决一个独立 READY Run；本次 Run **自身**的缺陷会否决执行。Identity、Membership、Price、CorporateAction、Terminal、LEAN Input 必须全部 PASS，之后才允许 LEAN；Native Execution 和 Reconciliation 要在实际运行后 PASS。没有 Current fallback。

每个认证是有日期范围、来源版本、raw hash、identity、价格口径、许可和事件完整性证据的审核声明，不能把单个 `verified=true` 当作证据。官方证券身份和完整人口证明仍需审核；当前没有创建一份虚假的全人口认证文件。

## 2. 冻结研究设计与 Run IDs

使用已有完整 Validation，未按收益选择区间：signal **2024-09-30–2025-09-08**，evaluation **2025-09-22**，235 个 Scanner 信号日、245 个组合评价 sessions。计划在运行前冻结于 `config/pit_final_run_plan.json`，SHA-256 为 `6b1336a9bdfa9438471e057460ade0d945f57e8ae9736b5ecca80fb6667c8fcb`。

策略固定 `full_strategy2_v1@1.0.0`。策略参数、过滤、score/rank、max_new、TP/SL/max hold、MarketGuard、评价目标全部未修改。两个组合请求逐项核对策略/version/config hash、fee profile、slippage、window、LEAN build 和 resolved execution：**全部相同**。初始现金 $1,000,000；next Open；slippage 10 bps；每日最多 3 个新仓；TP 5%、SL -10%、最长 10 sessions；MarketGuard none，均为既有默认。

| 实际任务 | Run ID | 结果 |
| --- | --- | --- |
| Current Scanner | `d30a9c6d-1780-4211-a0d4-94372bad97b2` | completed，235/235 |
| PIT Scanner | `fc7a7002-277b-4921-b2fc-17e1bb5a929c` | completed，235/235 |
| Current native LEAN 对照 | `7384345d-1137-426c-87a4-b36030135e63` | completed，原生/adapter 核对通过 |
| 初次完整 PIT LEAN 请求 | `9202347f-86fc-45b8-a094-09baa0ceb934` | BLOCKED，未调用 native |
| 最终 PIT LEAN 请求 | `5e2458cf-b587-4367-be36-cf6c1d076b29` | BLOCKED，未调用 native |

最终请求补强 benchmark 证据日期范围、raw basis、非法 OHLCV 和重复 session 的拦截，复用同一完成的 Scanner 和冻结研究设计。旧请求保留。另保留 Scanner `29641e93-1644-4b13-8637-3645e27a9f49` 的 `worker stopped unexpectedly`：首次编排错误，随后改用标准独立 worker 重跑，不能把它当作价格失败或删掉。

这些请求在源代码提交前运行，原 metadata 如实保留基线 Git SHA + dirty 状态及当时各源文件的物理 hash。实现提交拥有最终测试源码；没有回写旧 Run 的 Git 身份冒充在新提交上运行。

## 3. 两套 Readiness

### Global PIT

| 维度 | 状态 | 当前安装数据的实际范围 |
| --- | --- | --- |
| Membership | PARTIAL | 90,339 intervals；snapshot reconstruction，source-attested completeness=false |
| Identity | PARTIAL | 9 verified identities / 17 intervals；90,322 intervals unresolved |
| Classification | PARTIAL | verified common 16 intervals、ADS 1；5,707 unknown/ineligible |
| Event | PARTIAL | 15 官方事件；2 securities 有 listing；法律 delisting date=0 |
| Price | PARTIAL | 1,462 已安装退出证券 bars；common 缺 1,419,830 sessions、7,605 无价 episodes |
| CorporateAction | FAIL | 本轮建立统一事件/局部 native 处理；全人口 action completeness 仍缺失 |

全局 common expected sessions 6,892,714，统计 calendar 截至 2026-09-28；7,518 episodes 在观察范围价格完整、140 部分缺失、9,642 少于 126 条历史行情。完整观察区间不等于完整上市生命周期，更不认证 vendor identity。原 feature store 保持 7,658 IDs / 5,472,884 rows；本轮没有通过删掉缺价人口提高分母。

### 最终 Formal Run

| Gate | 状态 | 可复核阻塞 |
| --- | --- | --- |
| Identity | FAIL | 6,418 个 reason：issuer/class/exchange/type/reuse 范围未认证；这不是全库 90,322 intervals 的 veto |
| Membership | FAIL | 请求完整历史人口缺 source-attested completeness |
| Price | FAIL | 14,023 个 reason，包含缺价、raw/feature/source/license/scope 认证、基准；reason 数不等于证券数 |
| CorporateAction | FAIL | 6,422 个依赖身份缺完整范围的事件覆盖认证 |
| Terminal | PASS | 此请求没有触发已知但无法解释的 terminal event；不证明未知退出事件不存在 |
| LEAN Input | FAIL | upstream 未过，另有 IREN 的 unresolved episode `OBS-626ad46887c682e17d3cf605` 与另一个身份的 root collision；不能安全生成正式输入 |
| LEAN Native Execution | NOT_RUN | 门禁拒绝，未伪造 native Run |
| Result Reconciliation | NOT_RUN | 没有正式 PIT 组合结果可核对 |

Run 含 **6,422 个 security IDs、4,177 条冻结 signals**。所需证券/基准价格 **2,023,561**，缺 **435,803**，实际覆盖 **78.463560%**，不是 100%。其中 2,315 个身份在 required scope 缺日，1,138 个 required scope 完全无价。依赖包含未入选和无价证券；不可通过只取有价 population 放行。

实际 worker 返回：`LEAN PIT run BLOCKED: {"CorporateAction": 6422, "Identity": 6418, "LEAN Input": 2, "Membership": 1, "Price": 14023}`。完整具体原因保存在 immutable Run metadata 和本地 manifest；API 能返回它们。

## 4. Scanner 差异与可归因范围

人口数字是证券/日 observations，不是不同证券数。Current 的既有 population contract 与 PIT 的 dated common population 并不拥有相同分类证据，不能仅把全部差异命名为 survivorship。

| 统计 | Current Snapshot | PIT |
| --- | ---: | ---: |
| 每日人口范围 | 9,609–10,859 | 5,166–5,213 |
| 人口 observations 总和 | 2,397,726 | 1,218,543 |
| feature-complete observations | 1,242,905 | 687,937 |
| ranked candidate observations | 6,981 | 4,177 |
| PIT no-price observations | 未单独提供该计数 | 161,257 |
| PIT insufficient-warmup observations | 未单独提供该计数 | 64,696 |

候选按 `(signal_date, symbol)` 联结：交集 **4,177**，Current-only **2,804**，PIT-only **0**。交集内 score 全部相同，但 **3,706** 条 rank 改变，说明人口/排名效应；不是修改 score 的结果。候选不等于实际订单：执行沿用每天最多 3 个新仓及原资金/流动性约束。

Current-only 的 dated master 观察分解：1,314 条仍为 eligible common，差异需要进一步区分历史 feature/warm-up/选择上下文；939 条没有当日 master observation；431 ADR、89 unknown、22 warrant、9 SPAC 被 PIT 类型规则排除。多数类型标签仍 inferred，上述是**观察分类**而非新法律证据。完整明细留在本地 `candidate-decomposition.json`。

| 潜在原因 | 本轮证据能支持什么 |
| --- | --- |
| true later-retired securities | ATVI/TWTR/SPLK 的真实退出行情已存在，但本次 Validation 在这些已认证退出之后；其他退出身份未认证，不能计算其收益贡献 |
| future listings | 已有 listing/date gate 与泄漏测试；939 个无 dated observation 不能全部认定为未来 IPO |
| source coverage mismatch | 当前快照与历史目录范围不同；无当日 observation 和源 gaps 必须继续审证 |
| security type differences | 上述 ADR/unknown/warrant/SPAC 计数；Current 示例还有 ETF/ADS，不能把分类排除等同幸存者纠正 |
| rename / reuse | FB/META、OSTK/BYON/新 BBBY 连续身份；旧 BBBY 独立；本次新旧 BBBY 缺价不能用同 ticker 价格串接 |
| missing historical price | 435,803 required records 缺失；Scanner no-price 161,257 observations，计数范围不同不可相加 |
| warm-up | 64,696 insufficient-warmup observations；上市日期/观察起点不能混淆 |
| corporate action | 因果 split/native accounting 在案例中验证；安装正式请求仍缺 raw/action 认证，未形成组合修正收益 |
| population ranking | 重叠 score 不变、3,706 ranks 改变，是直接可观察证据；订单和资金联动仍不能独立归因 |

**没有正式 PIT 收益，因此 portfolio delta=null；没有可宣称的“幸存者偏差 X%”。**

## 5. Current 原生对照的真实结果

| 指标 | Current | 正式 PIT |
| --- | ---: | --- |
| 初始资本 | $1,000,000 | 请求相同，未执行 |
| 期末权益 | $934,221.7906461 | null |
| total return | -6.57782093539% | null |
| closed trades | 640 | null |
| win rate | 56.71875% | null |
| 平均 closed-trade net return | -0.1719583827% | null |
| max drawdown | -47.7494454042% | null |
| Sharpe | -0.03882763056 | null |
| CAGR | null，245 sessions 未达既有 252 门槛 | null |
| fees | $207,619.738886 | null |
| turnover（既有 contract） | 92.8456340184 | null |
| peak / end open positions | 19 / 1 | null |
| SPY benchmark return | 16.2228109314% | null |

保持既有 `usmart_hk_us_pro_spec_sep2026_unconfirmed` fee profile 和全部 execution assumptions，不因费用或收益难看改模型。平均收益由 native-normalized closed trades 计算；其他主要指标来自既有 normalized contract。Current 模型未认证 terminal actions，不把没有 action journal 说成真实世界事件为零。

LEAN 接收日线 Open/Close 的两个隔离代理，非真实分钟行情，不模拟 intraday TP/SL 顺序或订单簿。Current 导出仅含潜在持仓所需区间；native 全期订阅 1,767 symbols，产生 58,500 次成功和 807,332 次失败/重复数据路径探测。它不是 807,332 个缺价 sessions 的证据，也不能忽略此限制声称 native 输入全人口完整；export 已检验当前订单依赖范围的价格，结果/fills/fees/cash 与 native 核对通过。相关日志和监控 raw 留在本地。

## 6. 数据工厂与公司行动

`ResolutionQueue` 为 SQLite，任务绑定 dependency/security/sessions，P0 缺陷优先，P1 selected/near，P2 其余依赖；支持 lease、崩溃恢复、cache、幂等任务、失败最多三次显式重试和每次 outcome hash。单次最多 1,000；批量迭代。本次 P0 不是只处理三只样例股，而是完整 6,422 个依赖证券；全量局部证据判断保存在最终队列。实际全部完成一次评估：6,422 blocked、accepted 0、pending 0，逐个 attempt outcome hash 已核验。blocked 是等待新增证据的真实状态，不是完成认证。历史初次请求的旧队列保留，当前工作入口为 `resolution-final.sqlite3`，不把两个版本相加当作新证券覆盖。

网络阶段自动复用四个已认证身份的日期映射，采集 NVDA、BYON/新 BBBY、PLTR 两个 exchange scopes、META 的 **1,439 条**价格，连同 split/dividend/source-symbol responses 固定 Dolt commit/raw hash。**全部 quarantine，未安装也未降低缺价数**：下载成功不等于完整 raw/action/license/vendor identity 认证。SEC current discovery 实际 HTTP 403，失败收据保留，不绕过访问限制；当前 issuer metadata 也不能证明历史 listing/reuse。

新 `corporate_action_event` 表包含 security_id、event type、effective date、old/new symbol、ratio/consideration、source/confidence/handling/review；本轮独立 action DuckDB 有 15 个官方 catalog events，`coverage_complete=false`。四个旧行情/研究库和已安装 PIT feature/external price store 均未被重写。

原始价格用于执行；feature 是 **as-of causal split-only**：发生拆股后才把此前 OHLCV 换为当日股本单位，后续事件不改早期 feature，保持原 feature 公式。dividend-adjusted inputs 不能充当 raw；旧 split-only 数据必须有范围内无 split 的 raw-equivalent 审核，不能再复权。native RAW holdings 由 LEAN split 事件调整，adapter 仅调整入场成本注记及核对 fractional cash，避免 double split。

map 按同一 SID 的 dated ticker intervals；factor seed/preceding-session reference 已用 native 验证。现金收购需要官方 consideration、effective date、最后真实交易日、USD/零结算费审核。**按生效日确认 gross cash right**，不声称是投资者银行实际到账日或含税后金额；不能用最后 close 代替 payout。native CashBook 与 Holdings 做明示权利结算，并核对原生余额；它不是模拟一笔市场 fill。

现金收购的 map economic lifetime 截止于 reviewed entitlement date；最后可交易日单独约束；法律 delisting date 单独保留 unknown。把 map 结束设在 last quote 会触发 native 以旧价格提前清仓，本轮真实 native 测试发现并修正，不能把三种日期混为一谈。

rename / 美国交易所转所不是终止事件；stock conversion、未知 bankruptcy recovery、OTC continuation、缺 settlement terms 仍 BLOCK。通用 dividend/cash distribution 和 stock-merger conversion 尚未实现；必须有完整范围的 action review，不能漏事件后 PASS。SID root collision、已有组合持仓导入也明确 BLOCK，等待单独验证的适配。

## 7. 三个真实 native Golden Cases

这些是**手工会计测试信号**，不是 Strategy 2 完整 Scanner population；没有用它们代替正式 Run PASS。小型 evidence metadata 已提交于 `tests/fixtures/pit/native-real-evidence.json`，完整 raw/vendor prices、native logs、bundle 仅本地。

| 案例 | 有效事实/价格范围 | 实际 native Run ID | 核对 |
| --- | --- | --- | --- |
| FB → META rename | 2022-06-06–14，6/9 同一 Class A 换代码；7 个真实 sessions | `941665ef-55ef-4b52-9baa-33d697e88679` | 一笔交易，native SID 连续 / reconciliation PASS |
| NVDA 10:1 split | 2024-06-05–10，6/10 ex-date，6/7 原始参考价 1208.88 | `dbc16a0f-9d8b-4623-94f7-c97fb0bf8054` | 原生股数/成本与 feature 因果连续；无虚假 90% P&L；PASS |
| ATVI cash acquisition | 2023-10-12 最后交易，10/13 common-share gross right $95，评价至10/16 | `2f069ac5-cb30-491c-acde-22d913a2f634` | native cash/holdings/终止权利会计与 adapter PASS |

rename 免费源仅提供 FB 3 日、META 2 日，缺 6/9–10；这批公开价格被拒绝，**没有拼接或 forward-fill**。真实 rename native test 使用原有获授权本地 broker snapshot 的 7 个真实 bars，范围内无 split；保留 supplier historical identity 未独立认证的 residual risk，不据此认证全研究区间。

NVDA case 截止 6/10，未跨 6/11 dividend，不以它认证通用 dividend accounting。ATVI consideration 来自 [issuer SEC 8-K](https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b)，审核了 common-share entitlement 与排除项；rename 依据 [NASDAQ ECA2022-125](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-125)，split 依据 [issuer FAQ](https://investor.nvidia.com/files/doc_downloads/2024/06/nvidia-2024-stock-split_faq_investors.pdf)。黄金案例的内部权益变化不作为策略表现。

## 8. 来源 inventory、许可与剩余风险

| 来源 | 固定版本 | 角色和决策 |
| --- | --- | --- |
| [rreichel3/US-Stock-Symbols](https://github.com/rreichel3/US-Stock-Symbols) | `157439344501b2020cc2ae37addd6f628fa00699` | 历史 snapshot observations；人口完整性未官方认证，raw local，redistribution unverified |
| [YLiu95/delisted-equity-data](https://github.com/YLiu95/delisted-equity-data) | `37b4198b6c5cc4a4354aad6f71c2aeac631703b2` | secondary claims，不能直接写法律 delist；license 未核清，raw local |
| [Quant-Lodge/ticker-reference-data](https://github.com/Quant-Lodge/ticker-reference-data) | `a3eb36f951f9796c60c0a4c6bb70f13e50d9da6b` | discovery/secondary identity，非自动 merge；raw local |
| SEC/issuer/NASDAQ official evidence | `config/pit_trust_evidence.json`，10 raw SHA-bound documents | 13 证券范围映射、15 events；公开披露不等于 blanket redistribution permission |
| [DoltHub post-no-preference/stocks](https://www.dolthub.com/repositories/post-no-preference/stocks) | `vt6qeesk27k07492k5jc5b7p04mf0s6o` | CC-BY-SA-4.0；raw OHLCV/action/query/license evidence；审核接受或 quarantine，禁止 live ticker joins |
| 原有本地 broker research snapshot | immutable DuckDB hash，下表 | 已获授权本地研究，非公开重新分发，split-only 与 vendor identity 风险继续披露 |

免费源跨 rename 的缺日、未知分类/identity、源 gaps、vendor raw vs adjusted、完整 action coverage 都不能由 HTTP 200 消除。retry 仅限连接/timeout、408/429/部分 5xx，尊重 Retry-After；403 不重试绕过；不覆盖认证 artifact，failed/truncated/invalid payload 留 quarantine。

## 9. 关键 hashes 与旧库保护

| Artifact | SHA-256 / 版本 |
| --- | --- |
| Master source version | `509fe269e2e84a257f9b6d3116063f8a7d3f52ee8dec0adb236c8a192b95293d` |
| Master CSV | `a6f1362eaa38ed8a0daf00273b858c4c9dbf5f476de35688868ff6fd86564569` |
| Semantic universe fingerprint | `96004bbb8fb71f9e9ddee528be1f4de46d7a2b3918d86404c33051454465ff04` |
| Eligible feature input | `9a407c1c22f4b3e4100631c761ec258b8851f048028d12b517ffb1fe3522ad62` |
| Installed PIT feature DB | `8d5b8ee4af9b0f97b3bfc1de7295681c52e12d69fa2c52f4a808f3c0d6fcabc4` |
| Installed external prices DB | `90d458e4396c58a017402f76efc6f3addf4ed51734bc1a815c957dbd99605a2c` |
| Final dependency semantic | `03118eee3cebb3cab78b86949cac39ab0a36b0a222322ca1e1cea66707a7e45e` |
| Final dependency JSON bytes | `8dd55b0ef9a2d5e9901fb518995b7a48a61ab15a0f5c3e202c56e580f8057889` |
| Original dependency semantic | `2ec183549bf40eefdc8d12024c5dc2eafde00c90e3e6bbe8331bc74db41235b1` |
| Final frozen PIT signals semantic | `0bb64f67d781e1076cb6ff545ac2f53b255848a330246104beef5c886cbc1c1b` |
| Final gate source run.py | `89763b47b522d937b6ce7cad8009c13dec3fa036a11c2c73625dbc242a57c9a8` |
| Corporate-action DuckDB | `950f07e58fdd7945ce7eb6b243a79bcbc10641c40952e3a3571fca23dddbec5f` |
| Corporate-action events semantic | `caef0ea3b87a899ab55c547ed34410d3715a3491aa8b1686ee3c171b0953ebb9` |
| Current bundle manifest | `c10561fc1d901ba7fd4cc563f6ab32bcf1097b8593e6635d7118514547c37a15` |
| Current map/factor/zip index | `0d7e41588a7a179a89b34e862315cec2add415c4e9ba074be3ab3f7cb9ee7979` |
| Current signal snapshot file | `4f1a7f503c023dd067e266a0b7086f1c6933c913072df2722baa17bcb0272b22` |
| Current source prices CSV | `b371192b2e50bb407930780460f7f9ef5abbebccb1f77a504b0ec512b0d19808` |
| Current native result | `17e4fe80f7aa661712e6d0c4625cccb64dfbaabd967b06ad5b60eae17e845161` |
| Current normalized result | `acc6f4a43a230e638d00f43b03bcbd479944acde9df9901656071b253c605fd5` |

[机器可读验收证据](../evidence/pit-final-evidence-2026-10-07.json) 保存实际指标、gate counts、源文件 hashes、队列/网络结果与本地 receipt hashes。各 real native case 的 map/factor/actions/price/index、native/raw/normalized hashes 见已提交的小型 fixture。未生成正式 PIT native dataset，因此该正式 Run 的 map/factor/native result hash 不伪造。

| 旧数据库 | 入场与结束 SHA-256（相同） |
| --- | --- |
| market.duckdb | `0043f66ea4ac75c14d1a65e2765cb314d8cc19299f64abe390fd58e30caad60d` |
| phase2-research-v2-frozen.duckdb | `71361753f5d593ba43c090a984b299cc24f309e9345aae0f2c5615bc73341c7e` |
| phase2-research.duckdb | `b2565184a372c6ce7d5b448acebad3dfbad0bf51c77b785f5d0a342352d364c3` |
| phase2-source-snapshot.duckdb | `f6081cfc1a8bbe5856a5a3659be7ae6dfc3f864cb865ce2d12e2fd67200d0fd9` |

本任务入场 2026-10-07 11:08:14 Asia/Shanghai。正常 DailyUpdate 在此前 08:30:02–08:36:09 已新增 12,531 bars、updated 0；入场 market hash 已含该更新，mtime 08:35:06。原先专项的旧 hash 不能用来回滚正常行情。本次结束 hash/mtime 与本任务入场相同，研究库只读，没有直接写入旧库。前两份验收报告亦未修改。

## 10. 测试、API / UI 与复现

完整本地测试：**377 passed，1 条既有 websockets deprecation warning，82.92s**，`STOCK_RADAR_TEST_LEAN=1`；最终小幅页面标签修改后追加静态耦合测试 **10 passed**，`node --check site/dist/lab.js` 通过。不是 hosted CI 证明。

测试覆盖既有未来上市/退出边界/rename/reuse/转所/common vs ADR，新增 full-population/unpriced closure、raw/partial/no-price gates、source/license/manifest/physical DB/queue mutation、factor/map mutation、因果 feature 的未来修改隔离、native split/reverse split/cash/rename、PIT PASS 与 Current native parity、最终 normalized accounting。PASS fixture 是完整的**合成认证人口**，不能替代真实 formal population。

LEAN source commit `82810ea63d5542f05dc58f9d1db0557cf174d0ea`；launcher SHA `9e61821fc8b70f00f24060da5c5ab7e9ee7f1f3ce68dbdf216d8168a94ed7c5a`；engine SHA `d456963b1d7f3cbc864a9c4eb62fd9afb70e43dedcb6a44eadf90d62ae7c664c`；Python SHA `0817a2a657a24c0d5fbb60df56960f42fc66b3039d522ec952dab83e2d869364`；本地 installation patch SHA `f73e89086ed1f44f7c3897c6b4cca6df6f456d88127fd9524b502283fe3ed9e0`。

新版 API 使用独立、前台工具管理的 8766 端口验证，`engine`、两种真实 `run`、`pit-readiness` 均 HTTP 200，global scope 与 Run readiness 分离。尝试重启既有 8765 服务及背景启动被自动审批拒绝，仅返回 `blocked by policy`；没有终止或替换该旧进程，生产服务须在正常重启后加载新实现。

本地网页 `http://127.0.0.1:4174/lab.html?smoke=1` 实际浏览器验证：页面正常、连接成功，Current completed 与 PIT BLOCKED 历史行显示 exact strategy、engine=LEAN、PIT version；点击 PIT 行显示 immutable dependency hash 和审核 metadata，点击 Current 行能读取真实组合结果。初次连接阶段有暂时 disconnected，服务就绪后恢复；稳定状态没有相关 console error。8765 原进程仍旧版，不能把独立 8766 验证说成已经重启线上服务。新版全局/Run API 合约验证另存本地 `api-qa.json`。

复现入口：

```powershell
$env:STOCK_RADAR_TEST_LEAN = '1'
.venv/Scripts/python.exe -B -m pytest -q
.venv/Scripts/python.exe -B scripts/run_pit_acceptance.py
.venv/Scripts/python.exe -B scripts/resolve_pit_run.py --dependency data/pit/run-dependencies/03118eee3cebb3cab78b86949cac39ab0a36b0a222322ca1e1cea66707a7e45e.json --queue data/pit/final-acceptance/resolution-final.sqlite3 --limit 1000
.venv/Scripts/python.exe -B scripts/verify_pit_native_goldens.py
```

最后两个真实数据入口需要本地原始证据/冻结库/native installation；GitHub 没有上传价格 dump、大型数据库或本地许可证不明的原始文件。不要在只有 Git clone 而无原始数据的环境声称已复现正式区间。

最终状态：**Final engineering pipeline complete; formal PIT portfolio remains blocked by specific unresolved data dependencies.** 开放项包括本次人口完整性、6,418 个身份原因、435,803 个价格缺口、6,422 个事件完整性声明、raw/feature basis、SID collisions，以及一般 dividends/conversion/OTC/unknown terminal 的可信处理；继续列在唯一总账，不销项。

所有历史实验都是 retrospective research validation。原 Historical Test 不改称 Fresh OOS，Fresh OOS 仍等待真正冻结后新到数据。本轮无正式 PIT portfolio performance、无 bias-free 宣称、无参数优化。
