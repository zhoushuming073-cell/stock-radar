# Stock Radar QuantConnect Free Cloud 准备验收 · 2026-10-07

**2026-10-08更新：工程准备完成；两份真实Cloud smoke完整下载已导入，parser验收均PASS，smoke门禁解锁；首日Layer1引擎Completed但回执未验收，后续受平台导出范围限制。Layer1 pilot引擎Completed、数据未验收，Layer2/3 NOT_RUN，原Research-Grade PIT仍PARTIAL / BLOCKED。**

用户已本人登录。Codex已完成项目写入、Cloud构建及FB/META、NVDA两份真实回测；不是本地fixture。此前嵌套结果窗口阻止自动下载；用户现已提供四份真实下载文件，完整回执、输入/代码哈希及原生Results JSON已由parser验收。详见[Cloud重测报告](qc-cloud-smoke-validation-2026-10-08.md)。不购买套餐，不依赖API Token。

## 最新基线与保护边界

开始fetch/fast-forward后基线为 `412c5e464e617cf9f15b71f96ad4d481b94b9e4e`。收尾再次fetch/fast-forward至 `80b6d95`，读完新增的[LEAN/PIT只读定位](../audit/pit-lean-blocker-localization-2026-10-07.md)；该提交只改文档，生产代码与冻结数据一致。保留[唯一总账](../journey-2026-09-30-0651-📌当前总账.md)、[最后研究验收](pit-research-final-acceptance-2026-10-07.md)及最新[evidence](../evidence/pit-research-final-evidence-2026-10-07.json)的原结论。

重新读取而非硬编码当前数字：每日29–72 potential unknown Core competitors，1,346 distinct competitors；C实际327候选UID、1,264 signals，106身份未决、12执行security/session缺口、10重大事件/价格审查UID。正式真实PIT Native及reconciliation均NOT_RUN；七项门禁均未获新的PASS。既有研究API/Native门禁未替换，Current结果不作PIT基线。

10月7日准备基线的24项保护哈希保存在 `quantconnect-validation/protected-verification.json`。10月8日复核23项冻结数据库/证据/规则一致，实时market.duckdb因既有每日任务独立更新；当前[核验记录](../evidence/qc-protected-verification-2026-10-08.json)保留前后哈希与任务归因。原PIT closure semantic hash仍为 `f1b4b2db60ee52a5d8f13426c9a6cd5750b337d0bd96bf05746960b92db0ac3a`。本专项未修改策略、参数、原数据库、原接受store、原冻结证据与生产LEAN路径；既有每日任务的实时行情更新未回滚。仅新增独立目录、测试和文档导航。

## 已交付与实测

| 项目 | 状态/范围 |
|---|---|
| `quantconnect-validation/projects/smoke-mapping` | 单文件自包含：FB→META、MSFT/SPY、历史数据/身份接口 |
| `quantconnect-validation/projects/smoke-split` | 单文件自包含：NVDA 2024拆股、MSFT/SPY、typed历史接口 |
| `snapshots/` | 14个源码生成快照；函数/默认值/公式不人工重写，仅导入路径迁移与选定原函数提取 |
| `frozen/inputs.json` | 本地Core、逐日P0、历史身份事实、冻结C信号、规则/源码/生成器哈希 |
| `campaign.json` | 2 smoke + 235 Layer1 + 235 Layer2 + 1连续Layer3，共473个固定计划 |
| `quota-audit.json` | 470份日项目全部审计；最满含默认notebook23文件；最大文件上限30,010字节 |
| `local.py` | prepare、stage、verify、quota、实际回执import、分层compare、执行差异与明细合并 |
| `cloud/protocol.py` | 8,000字节派生日志预算；begin/end、序号、输入/源码哈希、缺日、重复及原始数据字段检查 |
| `schemas/`与`evidence.py` | 结构化官方证据；原始响应/HTTP回执哈希、发布时间、CIK/class、实际QC身份回执校验 |
| 本地测试 | 原有468项保留；新增39项，共507 passed（含Native LEAN），83.78秒；harness定向39 passed，4.71秒 |
| 真实Cloud | 两个实际编号、五项检查、完整回执和哈希均已验收PASS；首日Layer1引擎Completed / 后续HOLD_PLATFORM_EXPORT_SCOPE；Layer1 pilot Completed但未验收，Layer2/3 NOT_RUN |

全套只有既有websockets deprecation warning。实测是本地工程/fixture回归；不意味着真实Strategy2 PIT组合已经运行。小smoke已实测历史行情、身份、映射和拆股访问；大范围QC运行的CPU、内存和人口覆盖仍须pilot核实。

冻结C信号semantic SHA-256：`afa1c1d3bc2d05cded3b6874089358f0c1dc81433964a9dbb9ccb9b3a01f002c`。信号仅含因果日期/可用时刻、UID/历史ticker、rank/score、策略版本、reference close、ADV及allocation weight，剔除labels和future outcomes。它们被明确标为 `FROZEN_DIAGNOSTIC_C_NOT_FORMAL_PIT_RELEASE`，不会旁路正式门禁。

初版全日期配额审计发现重复发行人证据会超Free文件数，现按每个不同CIK保留最早两份独立dated observations；不同CIK和首次可用日期均保留，完整原参考文件仍绑定哈希。可用日复用原 `effective_day`，收盘后公开的事实不回填当天。未通过缩减研究规则或股票人口迁就配额。

## 三层验证的实质与限制

Layer1的QC Core只接受QC当日Fundamental历史人口、历史Symbol.ID、QC RAW历史OHLCV和Security Master。直接使用本地冻结 `core_membership` 函数：历史普通股，前一session价格≥$5，126完整sessions，20日均额≥$20m，已观察近期日额≥$5m，cap1000。历史股票池回调仅捕获人口，不订阅数千股票，降低Free内存压力。日期/行情缺口不填充，不用今天的名单补历史。

本地UID与QC SID通过有日期的ticker定位，再用当时可用CIK/class或证据绑定的SID验证；ticker一致不是自动身份一致。重复episode、不同class、缺身份字段保留Conflict/Unknown。身份无法确认时报告交集/Jaccard/Top1000重合上下界，未确认部分的only计数是上界，不能伪装为精确集合差异。目标是本地Core对QC Core，Full/Core Top3不再作为主要数据质量门槛。

每个本地unknown竞争者输出分类、排名和条件位图。QC有明确规则失败或已知排序在cap外才可Confirms Out；QC未覆盖或缺数据始终Unknown。Confirms In还要考虑所有未测QC竞争者可能排在前面的最坏排名。950–1050作为预先固定的边界展示范围，不是修改Core cap。摘要带冲突哈希和25个样本；需要完整清单时用预先固定32桶补取，不把样本视作完整核验。

Layer2使用生成的相同特征函数、因果split处理、Elasticity、FullStrategy2Plugin和evaluate_selection。先在QC全历史可交易普通股cohort进行横截面Elasticity评分，再限制QC Core，避免只在1,000只股票内另算百分位。比较eligible/selected count、selected名单、Top3/Top5、rank与日期/身份。QC拆股因子用于QC特征，不借用本地action清单，也不使用含未来因子的默认调整历史。

Layer3消费同一冻结信号，运行连续窗口，复用本地execution policy源码，保留$1m、max_new3、max_positions30、equal_cash、1倍杠杆、ADV2%、最大仓位约1/3、最低仓位1%、10bps滑点、相同费用、next Open、TP5%、SL−10%、最多10sessions和entry gap范围。云端记录真实Native订单/现金/持仓，不构造假行情或人工terminal payout。需要完整327个UID的历史SID binding才可stage可运行包；已有本地身份验收且实际QC首次信号日CIK/class一致者由bindings命令自动复用，只有未决或冲突项调查官方资料；正式PIT本地基线仍待现有门禁放行。

执行模型差异明确披露：Open基准来自09:31交付的09:30分钟Open，订单时间不倒填；原本地采用flat Open proxy，QC分钟持仓标价会影响预算；QC原生split/dividend/delisting可不同于本地已支持的特定terminal convention；源码trade return不分配普通分红，而Native组合现金含分红。差异须量化，不能静默调参。原生Results/Orders/Trades提供派生交易结果；不足的fill/exit细节可用128个固定输出桶重跑同一连续窗口，并要求fill/trade/session哈希与主回执一致。按日期拆Layer3并重置组合被禁止。

## 要求的16个答案

| # | 问题 | 本轮答案 |
|---|---|---|
| 1 | Free足够第一轮吗？ | 足够准备及运行小smoke；Layer1逐日pilot按Free配额设计。全期性能/账号实际数据访问尚待Cloud实测。 |
| 2 | 需要付费吗？ | 当前不需要，不购买或升级。 |
| 3 | Free可完成什么？ | 网页Python项目、Cloud历史回测、Security Master/corporate-action smoke、派生结果下载；三层验证按既定分块和条件推进。 |
| 4 | 哪些自动化需要Paid？ | 官方API/LEAN CLI cloud push/backtest通常需要Quant Researcher组织；本轮不用。付费不自动授予原始数据再分发权限。 |
| 5 | smoke需要哪些文件？ | 每个项目仅复制其projects目录的main.py，manifest留本地；默认notebook可保留。 |
| 6 | 文件配额合格吗？ | 全470个日期包检查通过，最满含notebook23文件，最大≤30,010字节；smoke main.py约16KB。 |
| 7 | Layer1怎么核验Core1000？ | QC自己的历史人口/RAW数据/身份，执行同一个冻结Core函数，再与本地Core做身份安全比较。 |
| 8 | 29–72 unknown怎么处理？ | 逐日全名单分类Out/In/Borderline/Identity-Lifecycle Conflict，另保留Coverage Unknown；不存在不等于Out。实际剩余数量待Cloud。 |
| 9 | Layer2如何确保策略同源？ | AST生成原特征、评分、插件与adapter，输入/源码/快照哈希检查；没有第二份手写Strategy2公式。 |
| 10 | Layer3如何确保相同信号？ | 单一1,264条冻结C输入、signal_hash检查、SID绑定、连续完整组合窗口；本地正式PIT未放行时不借Current比较。 |
| 11 | 用户网页操作？ | 已登录且两份smoke由Codex实际运行。若手工接管下载，只需Logs→Download Logs、Overview→Download Results；解析由Codex完成。 |
| 12 | 如何导回结果？ | 下载日志及Results JSON到忽略目录，绑定实际Backtest ID执行import；分层compare拒绝缺日/重复/不匹配hash。 |
| 13 | 如何避免QC原始数据导出？ | 历史数据留在云内；仅输出条件、counts/hash/mismatch IDs及实际回测订单/交易。无逐bar日志、无Object Store写入、无QC行情文件入Git。 |
| 14 | 哪些触发官方调查？ | identity/lifecycle冲突、QC In而本地unknown/out、本地Core而QC有规则失败、真实候选冲突、执行缺口与重大事件/价格冲突。不同OTC/ADR范围先标定义差异。 |
| 15 | 预计AI人工案例数？ | UNKNOWN。没有真实QC筛选结果，不把1,346或106直接作为人工任务数，也不把空回执队列说成零残差。 |
| 16 | 数据库阶段何时结束？ | 全日期Core差异有界且可解释；决策相关P0证据解决；同源策略候选/实际可能下单稳定；真实同信号PIT Native与QC执行已核对；material actions影响量化且不实质改变结论。仍需既有生产证据/门禁，不要求两个数据库100%相等。 |

Free配额、网页回测与Tier权限根据本轮查看的[资源文档](https://www.quantconnect.com/docs/v2/cloud-platform/organizations/resources)、[组织功能](https://www.quantconnect.com/docs/v2/cloud-platform/organizations/tier-features)及[Object Store权限](https://www.quantconnect.com/docs/v2/cloud-platform/object-store)设计。QC Fundamental universe包含历史退市证券，但排除ETF、ADR与OTC；因此范围不一致不能自动指证本地错误。[官方人口说明](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes)；[历史股票/拆股接口](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/asset-classes/us-equities)。

## 下一步与停止点

先取得并导入已完成的mapping与split完整日志/Results JSON；随后首日Layer1，优先回答unknown竞争者，按冲突生成官方调查；之后Layer2和已验证SID/正式本地基线下的Layer3。本轮没有继续清洗全市场，也没有按将来的QC结果预先豁免P0。

操作入口：[QUANTCONNECT_FREE_VALIDATION.md](../../docs/QUANTCONNECT_FREE_VALIDATION.md)。单一状态是 **Cloud完整smoke回执门禁PASS / 首日Layer1引擎Completed、数据未验收 / 后续HOLD_PLATFORM_EXPORT_SCOPE / Layer2–3 NOT_RUN / PIT BLOCKED**。


平台构建日志曾于QC显示时间4:37:56及4:37:59对 `qc_part_01.py` 发出Terms 2.6警告；随后构建成功并运行完成，但成功构建不等于输出许可。核对[当前QC条款](https://www.quantconnect.com/terms)（v1.4，2026-10-02更新），2.6涵盖参考数据及可重建/近似数据的派生输出，验证用途没有大小或目的豁免；2.6(e)允许自有源码及正常策略回测概要结果。现有身份/P0明细导出流程暂停，后续日期批次也暂缓，需在QC内完成比较或由平台明确具体输出范围。本轮不下载新的QC参考数据或发布身份明细。此限制来自实际平台警告及公开条款核对，不是smoke技术失败。
