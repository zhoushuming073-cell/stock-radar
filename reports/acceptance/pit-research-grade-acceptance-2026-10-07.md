# Stock Radar Research-Grade PIT 验收 · 2026-10-07

**状态：PARTIAL。研究级验收、独立原始价格表、动态 Core 与 A/B/C 实测已落地；真实 Research-Grade PIT Native LEAN 尚未执行。**
原因是身份、重大事件、缺价与未知竞争者仍可能影响选股，不是继续要求每只普通股取得法律级认证。

## 1. 冻结合同与旧标准

先同步 GitHub main `fcd7609` 并阅读唯一总账/最近验收。规则在下载/收益分析前冻结；没有因为结果修改价格门槛、流动性门槛、持仓周期、TP/SL或研究窗口。
Strategy 2 `full_strategy2_v1@1.0.0`，现有完整默认参数；Validation 2024-09-30–2025-09-08，评价截至2025-09-22；暖启动最早2023-12-12。已有10 bps slippage/next_open/费用/资本/退出规则保持。
原严格闭包 `2538efd79fdc64f5479f4345256f4d077e709d475c84a0452be9baa87256febf` 保留：6,421 个证券、4,176 个信号、2,023,436 required、435,678 缺价。Identity blocker 6,416；严格行动覆盖未审查6,421；Terminal PASS，其余上游FAIL。
新原始研究闭包 `f1b4b2db60ee52a5d8f13426c9a6cd5750b337d0bd96bf05746960b92db0ac3a`：2,023,415 required、183,757 缺价、4,284 新信号。新旧闭包/数据文件/验收分开，没有把旧RUN重新解释为研究级PASS。

## 2. 身份与实际接收价格

Level A **2,597** 自动研究级身份PASS；B **664**；C **3,160**。5个既有严格认证身份另保留；研究身份未解决 **3,819**。
A要求dated CIK同一issuer、名称兼容、稳定ticker、历史普通股描述、无reuse/重大事件/异常连续性；跨日期筛选只使用当日已知观测。全窗风险分类只用于验收，不能反向删除过去成员。
C包含多issuer/episode、受保护reuse链、ADR/类别疑点、拆股/消失/疑似终止。当前Class描述缺少第二类别绑定也保守进入C；C不是已证实错误的数量，也不意味着以后每只都要购买法律资料。BBBY/BYON/OSTK、FB/META维持身份隔离。
Dolt固定 `vt6qeesk27k07492k5jc5b7p04mf0s6o`、CC-BY-SA-4.0：445 sessions、4,798,261 行实际OHLC；17个暂时失败的日期在同版本补齐，失败原件保留。每日COUNT与JSON aggregate长度一致，避开接口行上限。
接受 **906,095** 行，属于 **2,521** 个A类且无来源分歧的证券；补回旧缺口 **66,236** 行，即旧322,439候选中实际研究级接收66,236。旧严格数据库没有安装这些行，严格缺口仍435,678。
原始行情、accepted prices、诊断feature DB均独立保存；执行不用旧split-adjusted价格，未拼接两种价格口径，没有forward fill、假价格或合成终止价。accepted表日期为DATE、其余字段兼容既有daily_bars接口。
全范围831个证券在local/Dolt重叠日出现>3%价格分歧，其中76个A类也隔离；这可能是复权或来源差异，不能直接认定哪方正确。已扫描3,169个极端成交量、1,145个非split样跳变、308个split-like跳变；均为异常行数。Dolt IEP/PHG存在0分母split因子，未用于特征修正。

## 3. 三层缺口与动态 Core

| Scope | 证券/候选 | 未解决身份 | 价格/执行缺口 | 重大审查 |
|---|---:|---:|---:|---:|
| 全历史人口 | 6,421 | 3,819 | 新闭包183,757 | 2,488 |
| A身份验收层（全窗验证层，非历史过滤器） | 2,597 | 0（条件身份PASS） | 源raw缺2,119；accepted所需行未接收29,297 | 0事件命中；分歧另隔离 |
| 实际A诊断候选 | 1,050 IDs / 4,284 signals | 529 | 52 / 35,506 possible execution sessions | 275 |
| 实际B诊断候选 | 780 IDs / 3,235 signals | 196 | 5 / 26,685 possible execution sessions | 176 |
| 实际C诊断候选 | 327 IDs / 1,264 signals | 150 | 22 / 10,345 possible execution sessions | 36 |

A身份层935,392 required，raw已观察不等于全部accepted：2,119真缺/区间缺口，加来源分歧等隔离形成29,297未接收。初始旧信号范围raw可用性缺182,786；新signals/真实feature binding闭包缺183,757，两个分母不能混计。B/C执行缺口按各自选定信号重算，未复用A的执行区间。
Core冻结规则：普通股、前一交易日价格≥$5、126完整历史sessions、最近20session平均dollar volume≥$20m、每个已观察近期session≥$5m；按前一session平均dollar volume排名，ID打破同分，cap1,000。没有加入历史基本面。
Known FALSE可以因过去已知价格/流动性不达标排除；UNKNOWN不得当FALSE。即使其他历史缺失，某个已知近期session低于每日流动性底线仍可证明规则不符；这是同一冻结规则的三值逻辑，不是缺价删除。
235个信号日每天暂定 **1,000** 只，共 **1,448** 个不同已入池ID；另有每日 **52–111** 个unknown竞争者，合并实际/unknown共 **3,044** ID。已入池ID全required缺4,604；加入possible unknown后缺173,212。
这是可重建的高流动性Core原型。身份/事件的“高可信”验收尚未全部通过，不把原型称为正式高可信Core。未知证券可能改变前1,000及Strategy排名，不能仅因已知集合连续稳定就豁免。

## 4. Membership、重大事件与普通分红

九项检查分别留证：历史主源PASS；历史次源PARTIAL；已知future listing/区间异常0（PASS，真实IPO日期缺证另披露）；每日population 5,166–5,213、>5%突变0（PASS）；exchange覆盖PARTIAL；disappearance、随机抽样、later-disappeared抽样仍PARTIAL；sensitivity FAIL。
66个dated CIK目录停在2025-02-28，Nasdaq目录22个版本完成235日比较；不能替代NYSE/AMEX后半窗验证。50个随机ID按预先规则hash排序，抽样不依赖是否有价格；另50个消失episode保留早期入池，不把消失直接称为法律退市。
风险驱动 **2,521** 个 `research_no_material_action_pass`，无需逐股法律负事件证明。**2,488** 个证券需进一步重大风险审查，其中包括603个split事件命中、1,327个消失episode以及价格异常的重叠集合。这不是2,488个已确认重大公司行动。
多模态扫描包括固定Dolt split/dividend、dated主源symbol/name/exchange生命周期、FINRA OTC（局部覆盖）及raw价格跳变。已知重大split/merger/terminal仍沿用严格factor/身份/经济处理；负扫描不等于供应商全事件认证。
普通现金分红独立测量：A已知selected signals可能覆盖21个issuer/ex-date事件；以最大1/3 entry-equity配置合计潜在现金yield预算 **7.1565%**。ex-date开盘买入不计该次股息；未把现金预算冒充真实组合收益上界。
其中大额distribution另入重大审查；实际最终equity影响还需要持仓/资金/再投资路径。不能证明低于已冻结0.1% portfolio-return容忍度，当前没有使用普通分红豁免。若以后有完整且小于容忍度的测量，研究门禁允许明确列名ordinary cash事件的披露例外，禁止把split或terminal放进豁免名单。

## 5. A/B/C实测与Current比较

同一Strategy/参数/window/evaluation/因果feature公式；每个profile按自身当日人口重新计算既有Elasticity百分位。A全PIT人口；B按当时已知身份更严格筛选（缺价保留在审计）；C冻结Core原型。B没有用全窗A风险标签删除过去成员。
下表“命中率”是次日Open开始10session内High触及+5%，不是盈利交易胜率。Path success是先+5%后-5%，同日先后不明保持censor。MFE/MAE是完整可标记候选平均值。
| Profile | 候选 | Censored | +5%命中率 | Path success | 平均MFE | 平均MAE |
|---|---:|---:|---:|---:|---:|---:|
| A | 4,284 | 18 | 69.3155% | 48.2915% | 13.6564% | -11.2521% |
| B | 3,235 | 3 | 67.8218% | 48.7751% | 13.1073% | -10.8243% |
| C | 1,264 | 4 | 65.0000% | 46.8222% | 10.6685% | -10.2453% |

Jaccard：A/B **61.6989%**、A/C **17.9923%**、B/C **11.8042%**。A/C命中率差4.3155pp、MFE差2.9879pp；这些可测差值均低于对应5pp阈值，但候选集合明显变化，且共同缺失人口没有界定影响。完整sensitivity不能PASS。Core的主动缩池也影响overlap，不能把差异全部解释为数据库错误。
48,946个stock/date的未审定split后特征窗口显式不可用，相关forward split窗口censor；只对已验证官方split使用因果调整。没有把raw split跌幅当成假亏损。由此形成的未知selection影响尚未bounded，诊断率不能升级为正式结论。
已有Current Scanner：6,981 candidates，+5%命中率68.2424%；raw A为69.3155%，差 **+1.0731pp**。观测并没有显示PIT命中率明显下降；但成员/资产类型/身份暖启动/价格口径都不同，不能单独归因于幸存者偏差。
已有Current Native return **-6.5778%**、DD **-47.7494%**、640 trades、fees $207,619.74。PIT Native return/DD/trade count/average trade/fees均 **NOT_RUN**；差值未测，没有替代模拟器或新“正式收益”。

## 6. 研究级门禁与数据库耦合

| Gate | Status |
|---|---|
| Causal integrity | FAIL |
| Research identity | FAIL |
| Research membership | FAIL |
| Research price | FAIL |
| Material corporate actions | FAIL |
| Terminal | PASS |
| LEAN Input | FAIL |
| LEAN Native Execution | NOT_RUN |
| Result Reconciliation | NOT_RUN |

Causal integrity FAIL表示高风险身份及重大事件输入的完整因果审核尚未完成；当前没有据此宣称发现了未来数据泄漏。已实现前一session的Core选股和dated输入约束，缺少审核证据仍不能认定PASS。
Terminal PASS只表示本闭包已知事件的处理检查通过，不证明所有消失证券没有未知经济终止；未知生命周期已计入Material/Membership审查。
旧strict readiness未删。新API `/api/lab/pit-research-readiness`、System卡和结果标签明确Research-Grade PIT；缺artifact/证据变更/gate失败直接BLOCKED。已有调用仍保持原默认vendor-grade行为；研究执行必须显式提供research-grade和冻结audit/rules，禁止Current fallback。
Raw source与feature artifact复用既有schema、identity feature公式、production Scanner/plugin adapter和LEAN bundle/normalize。新metadata绑定实际raw source、feature fingerprint和resolved dataset hash；不沿用旧PIT数据标识。当前页面仅显示研究级验收，未启用不合格的研究级运行入口。
生产8765服务未强制重启。隔离临时HTTP服务器实际读取新artifact、校验完整物理锁并返回200/研究级BLOCKED；现有常驻进程需正常重载才会加载新增API代码。未修改旧database/active master三个文件/原feature store/原plan，所有保护SHA与entry相同。
测试 **436 passed（85.81s，启用实际Native LEAN）**；源绑定最后修正后的专项 **67 passed（53.17s）**。覆盖low-risk、reuse、高CIK、split、future IPO、后来消失入池、missing exclusion、三值Core、未来终止不反删、重建、sensitivity、双gate、API/UI、普通分红豁免不能吞split、no fallback及实际Native fixture对账。Native fixture PASS不等于真实Validation投资组合PASS。

## 7. 直接回答15个验收问题

1. **旧严格blocker？** Identity6,416；required缺价435,678；action coverage6,421未审查；Membership/Price/Identity/Actions/LEAN Input FAIL；Terminal PASS。
2. **研究级还多少？** 3,819未解决身份；新raw研究闭包183,757缺价；2,488重大风险审查；Membership/causal scope/dividend影响仍未闭合。不是把这些不同单位加成一个总数。
3. **自动low-risk？** 2,597。
4. **high-risk？** C3,160；另B664。既有5个严格身份认证继续保留。
5. **322k中实际接受？** 66,236补缺行；独立accepted原始series合计906,095行/2,521证券。
6. **Research Universe真缺多少？** 新完整研究闭包183,757；A验证层raw缺2,119、accepted未接收29,297；Core已入池4,604、含unknown可能范围173,212；实际候选执行缺口见三层表。
7. **material blocker？** 2,488待判风险证券，包含真实split命中与异常/消失疑点；2,521低风险负扫描PASS；未把普通分红和split混算。
8. **Membership sensitivity稳定？** 未通过；集合overlap低，未知人口作用未bounded；可标记样本的命中/MFE/MAE差在5pp内不足以证明全范围稳定。
9. **动态Core？** 已实现历史因果原型，未把未通过高可信验收的原型升级为正式研究池。
10. **每日规模？** 暂定1,000；unknown竞争者52–111。
11. **第一次真实Research Native？** 没有，条件未满足；Native合成fixture验证了接口和对账。
12. **Current vs PIT？** Scanner命中差+1.0731pp；正式portfolio收益/DD/平均交易/fees差均未测。
13. **不同Universe结论稳定？** 原生组合未测；候选集合变化明显、共同未知未界定，不能宣称稳定alpha。
14. **Residual risk？** 未独立绑定class/issuer、source basis分歧、近期NYSE/AMEX人口交叉不足、52–111未知Core竞争者、183,757required raw缺口、重大/大额分配/未知终止、split窗口不可用、普通分红真实portfolio影响。
15. **足以阻止Strategy研究？** 不阻止继续做标记明确的研究和敏感性诊断；足以阻止当前第一次可归因的正式Research-Grade Native投资组合/alpha结论。还没有证明这些风险不实质改变选股和持仓，故不能放行。

## 8. 复现与下一项数据工作

固定规则后依次运行：`download_pit_research_prices.py` → `audit_pit_research_grade.py` → `build_pit_research_diagnostics.py` → `finalize_pit_research_evidence.py`。raw/license/失败响应/dated reference保存在本地ignored目录；哈希失配明确失败。要用新规则或改已冻结代码重做，请建立新的版本目录与闭包，保留本次结果。
下一步的数据价值集中在Core未知竞争者、实际候选身份/重大事件、来源分歧及缺价作用的量化；不再以全6,421逐股法律认证作为A类的要求。不扩大框架、不凭空采购、不凭结果修改Core规则。
完整derived计数与artifact SHA见 `../evidence/pit-research-grade-evidence-2026-10-07.json`；底层raw与数据库保持本地。唯一总账维持研究目标OPEN/PARTIAL。
