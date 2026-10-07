# Stock Radar PIT 最后研究级收口验收 · 2026-10-07

**结论：PARTIAL / BLOCKED。剩余问题仍可能改变历史 Core 与整个 Top3，未达到第一次真实 Research-Grade PIT Native LEAN 的放行条件。**

本轮只处理 Core 竞争者、真实 Scanner 候选和可能持仓，不以全市场身份或缺价清零为目标。完成决策审计与局部补充，尚未完成“证明 residual 不影响 Strategy 2”的目标。所有下列组合差异空白均保留 NOT_RUN。

## 基线、冻结与证据

开始时 main 为 `525ea01fc950540283457488598a01477c8d4908`；收尾重新 fetch 并 fast-forward 至 `b798167fbed8341f21f6cf0c30e843a51f4fa5f6`，保留远端文档目录整理。按用户指定保留本报告的根目录路径，其派生 JSON 与 P0 队列放在 evidence/；没有新建第二份当前总账。

已读取旧 [Research-Grade](acceptance/pit-research-grade-acceptance-2026-10-07.md)、[source breakthrough](acceptance/pit-source-breakthrough-acceptance-2026-10-07.md)、[clearance](acceptance/pit-clearance-acceptance-2026-10-07.md) 与唯一总账，重新核对原始 store、A/B/C、Core、身份、行动与 readiness。旧 Research closure semantic hash 为 `f1b4b2db60ee52a5d8f13426c9a6cd5750b337d0bd96bf05746960b92db0ac3a`；原来源 Dolt pin `vt6qeesk27k07492k5jc5b7p04mf0s6o`，CC-BY-SA-4.0。新 raw 仅留本机，无原始行情再分发。

规则 `pit-research-decision-v1` 与物理输入在新分析之前冻结，semantic hash `a75524ab1dc07db301e9ced0385f80b78f437d4ed7bac4c8a90e891111098406`。旧 A/B/C Scanner label 已知，不能声称盲测；本轮未看新 Native 收益，更没有按收益修改阈值。Core 仍是历史普通股、前一 session ≥$5、126 完整 sessions、最近 20 均额 ≥$20m、每个已观察近期 session ≥$5m，前一 session 排名 cap 1000。Strategy、窗口、次日 Open、TP5%、SL−10%、最长10sessions、费用、滑点、max_new 与资本约束均未修改。

预先冻结门槛：每日 true competitors ≤3、C/D Top3 槽重合 ≥98%、完全相同日 ≥95%、缺失导致 Top3 变化上界 0、实际候选身份/执行缺口/重大风险/未处理 split-terminal 均为0、敏感性主指标绝对差≤5pp、普通分红最终组合收益影响≤0.1%。门槛没有在分析后放宽。

## Core 排名核验与排除证明

初始 unknown 为 52–111/日。完整20个近期 observations 可计算精确 dollar-volume 排名，但缺失 volume **没有有限上界**，不以经验最大值填补。

最初得到 2,438 个条件排名排除（security/date）。复查发现其中“已知合格”集合仍包含身份未确认者；仅使用研究级身份通过且价格资格完整的排名竞争者后，只保留 **622 个身份安全排名排除**，重新打开 **1,816 个条件排除**。不把条件结论包装成 Definitely Out。

另外，最近已观察 session 低于原 $5m floor 给出 6,424 个日期级排除；已知新上市类不足126sessions、真实零成交量给出 288 个日期级证明。它们只对列出的 security/date 有效，不是永久删除整只股票。最终尚可能入池的原 unknown 为 **29–72/日**、**1,346 个不同 ID**。另有 **288–311/日已知 Core 成员身份尚未充分确认**；身份清楚且价格符合规则的全排名集合只有 978–1,197/日。不能给出无条件的“确认 Core 939–978”下界：该数字依赖全部已知成员确实合格。

以下 cutoff 是冻结的观察人口下的流动性值，不是已确认无误的法律身份排名：

| Rank | 全期日 cutoff 最小值 | 最大值 |
| --- | ---: | ---: |
| 950 | $47,922,136.50 | $79,336,731.66 |
| 1000 | $44,014,329.26 | $72,334,607.13 |
| 1050 | $40,456,274.34 | $65,555,432.81 |

950 对 1000 的相对差中位数为 9.9489%；1050 对1000为 -8.8112%。逐日 cutoff、确认口径、未知名单与证明保留在 `data/pit/research-final/identity-safe-bounds/`，已知人口条件排名保留在第一阶段文件，不覆盖旧报告。

## 局部事实核验与持仓补充

[Tempus IPO 公告](https://www.tempus.com/news/pr/tempus-announces-pricing-of-initial-public-offering/)限定 TEM 新上市 Class A 最早2024-06-14；[Lineage IPO 公告](https://ir.onelineage.com/press-releases/news-details/2024/Lineage-Announces-Pricing-of-Initial-Public-Offering/default.aspx)限定 LINE 新类最早7月25日；[Smurfit WestRock 上市完成公告](https://investors.smurfitwestrock.com/regulatory-news/news-details/2024/COMPLETION-OF-LISTING/default.aspx)限定新 SW ordinary shares 从7月8日起；[Six Flags 合并完成文件](https://www.sec.gov/Archives/edgar/data/1999001/000119312524173290/d818752dex991.htm)限定新公司 FUN common 从7月2日起，与原 Cedar Fair LP units 分开；[NANO Nuclear IPO 公告](https://ir.nanonuclearenergy.com/news-releases/news-release-details/nano-nuclear-energy-announces-pricing-initial-public-offering)限定 NNE 最早5月8日起。只有文件已公开且发行人/新类绑定匹配、可能历史不足126sessions的日期被排除。公告的预计首日取最早可行日期，延迟上市只会缩短历史，不会让该排除失效。

LINE/SW 使用 publisher HTTP200 raw payload；TEM HTTP429、FUN SEC HTTP403 未被当成已取到原文，改用联网工具已返回的官方页 normalized receipt，并保留哈希与证据类型。失败原响应继续存档。TLN 是从 OTC TLNE 上市至 Nasdaq，不能把 Nasdaq 日期当 IPO 删除既有历史；[Talen 上市说明](https://ir.talenenergy.com/news-releases/news-release-details/talen-energy-corporation-announces-expected-listing-nasdaq)仍属别名连续性 P0。GAP 有[官方 GPS→GAP、CUSIP不变公告](https://www.gapinc.com/en-us/articles/2024/08/gap-inc-to-change-ticker-symbol-to-gap%E2%80%9D-on-august-)，但本轮未因 ticker 名称相似就安装历史 splice。

SMR 所有历史 observation episodes 名称均为 NuScale Class A common，已观察 CIK 只有1822966；首次信号前有22份 dated issuer observations。与[2023年官方 S-3](https://www.sec.gov/Archives/edgar/data/1822966/000182296623000158/nuscales-3.htm)绑定，明确区别股票与权证；[2024年补充招股书](https://www.sec.gov/Archives/edgar/data/1822966/000182296624000146/nuscale-424b5xnov2024.htm)提供后续复核。Dolt 与 Alpaca SIP raw 的10个缺失执行日都具有正成交量、合法 OHLC、各 OHLC 差≤3%。接受独立 holding-only 补充层，旧 UID 持仓连续性仅延至2024-12-23；未向后倒插新 membership、未合并全局 master、未重算未来筛选。

CLSK 2024-11-08 Alpaca 的13.57平价记录 volume=0、trade_count=0，是 **quote/mark，不能成交**。[11月15日官方8-K](https://www.sec.gov/Archives/edgar/data/827876/000095017024127680/clsk-20241115.htm)复核停牌及11月11日恢复；该后发文件仅供事后验证，不参与11月8日的先验选股。GH 2024-05-23同样为零量 mark，不用于凑126个完整交易session或加入 D。没有虚构可交易价或零损益终止。

生命周期审计改为逐个可能持仓session检查是否有合法 dated mapping，不把 PLTR/IREN 的中间区间末日当法律退市。AEVA/QXO等有持仓覆盖者也只纠正该误计，不因而清除其他身份风险。剩余 C 的12个执行日期：

- CLSK / `OBS-a1c0530da7a351c3a6489a62`：2024-11-08。
- MSTR / `OBS-eb84bd642dc37c865ac66f5e`：2025-08-13, 2025-08-14, 2025-08-15, 2025-08-18, 2025-08-19。
- SMLR / `OBS-f13ad149402d639e23232419`：2024-12-19, 2024-12-20, 2024-12-23, 2024-12-24, 2024-12-26, 2024-12-27。

## 实际候选、事件与价格范围

| Profile | 候选 ID | Signals | 未解决身份 ID | 执行缺口 / 所需 session | material review ID | 来源冲突 ID |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 1050 | 4284 | 306 | 42 / 35506 | 88 | 104 |
| B | 780 | 3235 | 78 | 5 / 26685 | 51 | 44 |
| C | 327 | 1264 | 106 | 12 / 10345 | 10 | 10 |
| D | 327 | 1264 | 106 | 12 / 10345 | 10 | 10 |

分母按候选可能入场后10sessions与退出边界的并集计数，并裁剪至2025-09-22。第一阶段误计的9月23日依赖及其原文件仍保留，最终采用上述分母。C feature 原始行覆盖0缺口；A/B为29/14，不等于所有特征、横截面 ranking、身份与事件都可用。

C 的10个 material review目标为 SATS、NVAX、CPRI、ROOT、SRRK、AKRO、NVTS、CLSK、MSTR、SMLR；前7个是极端价格不连续/疑似split待查，不直接称为确认行动。MSTR与SMLR是2个实际持仓 mapping gap，CLSK是停牌执行问题。完整 ID/date/evidence 见 [P0 队列](evidence/pit-research-final-priority-2026-10-07.json)。不要转回全市场2,488个 material-risk IDs 清洗。

## Decision Stability 与 missingness

Slot overlap 定义为 Σ当天共有ID数 / Σ当天两边最大槽数，空空日不进入槽分母但进入相同日统计。Top3 为 Scanner 排名前3，不是已观察真实新买入；组合已有持仓时可能选择第4名以后，因此价格与身份审核保留全部实际候选。

| Pair | Top3 slot overlap | 完全同集合日 | 完全同顺序日 | 有选择日 / 空空日 |
| --- | ---: | ---: | ---: | ---: |
| AB | 63.9175% | 28.0851% | 28.0851% | 231 / 4 |
| AC | 19.9115% | 2.5532% | 2.5532% | 231 / 4 |
| BC | 13.7931% | 2.5532% | 2.5532% | 229 / 6 |
| CD | 100.0000% | 100.0000% | 100.0000% | 205 / 30 |

A/C Top5 overlap 18.4404%；C/D Top5 100%。D使用与C完全相同235份日人口、策略合同和特征，借用C的真实Scanner结果并附等价证明，**没有独立重新运行Scanner**。本轮没有新增已同时证明身份、126历史和流动性合格的边界成员，D只是resolved-only控制，不是成功收敛实验。

Best/Worst/Excluded 每日选择ID已实际计算并保存在 score-stress.json：Best保持可见决策；Worst在同cap下移出流动性末尾成员，将未知候选评分置于合法上界100，保留已有分数；Excluded只排除有证据者，未知集合不被删除。压力实验235天可变化、最多3槽/日、累计705槽（其中替换已有519槽）。未知特征的共同可实现性未证，因此不把实验视为真实错选次数或实测损失。

更宽的实际算法界限还包括未知成员对横截面 Elasticity percentile 的作用：一个未知竞争者也可能改变已知候选资格。故日候选数的保守范围仍是0–1000，selected/rank最大变化可覆盖全部Top3/Top5；这不是可靠很小的上界。hit rate和path success无法收紧至优于[0,1]，没有虚构其Best/Worst收益、MFE/MAE或OHLCV。MFE/MAE只在已标签样本可比，不能补未知远期价格使结果看似稳定。

| Profile | Candidates | +5% touch | +5 before −5 path | Mean MFE | Mean MAE | Falling knife |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 4284 | 69.3155% | 48.2915% | 13.6564% | -11.2521% | 54.4304% |
| B | 3235 | 67.8218% | 48.7751% | 13.1073% | -10.8243% | 52.9703% |
| C | 1264 | 65.0000% | 46.8222% | 10.6685% | -10.2453% | 50.2381% |
| D | 1264 | 65.0000% | 46.8222% | 10.6685% | -10.2453% | 50.2381% |

touch/path 是未来价格label，不是TP5/SL−10实际组合胜率；A/B/C label censoring分别18/3/4。数量、排序、资格和样本集合共同改变，差异不能全部叫幸存者偏差。当前Scanner 6,981 / touch68.2424%；按显示symbol比较Current与A/B/C的Top3重合为 55.6196% / 40.7194% / 13.6888%，并非经法律身份验证的 ticker reuse join。A touch 比Current高1.0731pp不能隔离偏差来源。

## Dividend 暴露与七门

| Profile | 可能持仓除息事件 | 入场权益现金预算 | 最终组合收益上界 |
| --- | ---: | ---: | --- |
| A | 21 | 7.1565% | 未界定 |
| B | 18 | 4.2947% | 未界定 |
| C | 23 | 4.6752% | 未界定 |
| D | 23 | 4.6752% | 未界定 |

预算将每个issuer/ex-date唯一事件按最大1/3配置和可能最低入场价计，不是相对固定初始资本或最终权益的可靠组合收益上界。没有真实安全持仓路径时不授予普通分红例外；RKT大额分配单独严格审核。没有把普通dividend无限扩大到无关证券。

| Gate | 最终状态 | 直接阻塞理由 |
| --- | --- | --- |
| Causal integrity | FAIL | unresolved inputs can still change historical decisions |
| Research identity | FAIL | candidate_identity_unresolved exceeds frozen threshold |
| Research membership | FAIL | effective Core competitors exceed frozen budget; remaining missingness can change Top3; decision outcome sensitivity incomplete or unstable |
| Research price | FAIL | candidate_execution_gaps exceeds frozen threshold; ranking feature/benchmark scope incomplete |
| Material corporate actions | FAIL | candidate_material_unresolved exceeds frozen threshold; ordinary dividend effect not reliably bounded |
| Terminal | FAIL | known_split_terminal_unresolved exceeds frozen threshold |
| LEAN Input | FAIL | real frozen native inputs not verified; decision-scoped upstream gates incomplete |

本轮 Terminal FAIL 对应2个可能持仓身份映射间断，而非声称发生2次法律退市或2次未确认拆股。旧 strict known-terminal accounting PASS仅覆盖当时已登记事件，与本轮更宽持仓连续性审查口径分开。

## 20项直接答复

### 1. 开始还有多少 Core unknown competitors？

235 个信号日，每日 52–111 个。这是旧 Core 资格未知名单，不是已确认应入池但漏掉的股票。

### 2. 最后真正可能改变 Core 1000 的还有多少？

身份安全的保守集合仍为每日 29–72 个、全期 1,346 个不同 ID；另有每日 288–311 个已知 Core 成员身份尚不充分。22–61 是假设已知成员全部合格时的条件数字，不能用于正式放行。

### 3. 每日 Top3 稳定性多少？

A/B 63.9175%；A/C 19.9115%；B/C 13.7931%；C/D 100%，但 D 没有新确认合格成员，属于退化比较。

### 4. 实际 Strategy 候选还有多少 identity unresolved？

A 306/1,050；B 78/780；C/D 106/327。实际候选都来自生产 Scanner；低风险批量过关，类别或发行人碰撞继续拒绝。

### 5. 实际候选还有多少 execution price gap？

A 42/35,506；B 5/26,685；C/D 12/10,345 个 security/session。上述覆盖包含独立 SMR 持仓补充层；尚未发布的 Native 输入仍不能交易。

### 6. 实际候选还有多少 material action unresolved？

A 88；B 51；C/D 10 个需要处理的候选 ID。这是价格跳变、持仓映射间断、停牌或未核实行动的 review 集合，不是 10 个已确认公司行动。

### 7. 普通 dividend 真实影响多大？

C/D 有 23 个可能持仓除息事件，入场权益口径现金暴露预算为 4.6752%；无法可靠换算为最终组合收益上界。RKT 单次金额/可能入场价为 5.4795%，必须独立审核大额分配。ordinary_dividend_bounded_exception 未授予。

### 8. Remaining missingness 最大可能改变多少 daily selections？

保守合法评分区间压力实验可替换每天全部 3 个选择槽；235 天均存在变化空间，累计 705 槽，其中已观察 Top3 被替换 519 槽。未证明这些最坏输入可以同时实现，因此这是未能收紧的上界实验，不是实际错选或收益损失。

### 9. A/B/C/D sensitivity 是否收敛？

否。A/C Top3 仅 19.9115%；C/D 相同源于同一缺失集合及同一入池名单。A/C +5% touch 差 4.3155pp、MFE 差 2.9879pp、MAE 差 1.0068pp、falling knife 差 4.1923pp，尚不足以证明遗漏证券不改变决策。

### 10. Research Membership 是否 PASS？

FAIL。主历史 population 连续与局部二源核查保留；有效竞争者超过冻结预算 3/日，缺失集合能改变 Top3。Vendor-Grade Membership 继续不完整。

### 11. Research Price 是否 PASS？

FAIL。C 可见候选 feature windows 的原始行覆盖为零缺口，但持仓仍有 12 个无可执行行的日期、10 个候选 ID 来源不一致，而且未知竞争者影响横截面排序。benchmark 覆盖通过不等于全价格门禁通过。

### 12. Research Identity 是否 PASS？

FAIL。C/D 实际候选剩余 106；不再使用全市场 3,819 作为本轮放行的直接分母。

### 13. 是否第一次运行真实 Research-Grade PIT Native LEAN？

否，NOT_RUN。真实 full_strategy2_v1@1.0.0 的七项条件未满足；没有 Current fallback，也没有合成组合替代正式实验。

### 14. reconciliation 是否 PASS？

真实 Research PIT 组合 reconciliation 为 NOT_RUN。新测试确实调用真实 Native 引擎并核对 fixture 的 normalized result，但 fixture 通过不能冒充本项目 Strategy 2 数据验收。

### 15. Current vs PIT 真实组合差异是多少？

无法计算：PIT 组合尚未运行。保留 Current 的 640 笔交易、56.7188% 胜率、平均净单笔 -0.1720%、总收益 -6.5778%、回撤 -47.7494%、手续费 $207,619.74、turnover 92.8456、期末 1 个开放持仓、SPY +16.2228%。这些是旧 Current 参照，不是本轮新收益。

### 16. Full PIT vs Core PIT 有什么差异？

Scanner A 4,284 vs C 1,264；Core 少 70.4958% 候选。可见样本的 MFE、MAE、falling knife 有差异，尚无可比 alpha、波动、组合回撤、费用或周转；不能把 label 统计当作组合成绩。

### 17. Core 1000 是否值得成为长期研究 Universe？

值得保留为对照实验，尚不能建议替代 Full。Core 明显改变 Top3 并减少机会；数据更容易审计不构成策略更优的证据。

### 18. 剩余 residual risk 是什么？

P0-A：29–72 个/日可能竞争者与已知 Core 身份风险；P0-B：106 个候选身份、12 个执行日期、10 个候选价格来源冲突；P0-C：10 个事件/价格 review ID、2 个持仓映射间断 ID、CLSK 停牌、RKT 大额分配与未界定现金收益影响。无关小票的旧全市场缺口只保留记录。

### 19. residual risk 是否足以改变策略结论？

目前不能证明影响很小；选股上界仍覆盖整个 Top3，A/C 决策差异明显。不能把“可能改变”说成已测得真实收益差异，也不能授予 bounded residual exception。

### 20. 下一步研究策略，还是继续补数据？

继续补明确影响决策的数据，按公开 P0 队列处理历史别名/同一上市类连续性、实际持仓停牌与事件和二源价格冲突。禁止恢复逐只清洗 6,421 只，也不按收益修改 Core 或门槛。七门通过后才立即冻结新真实输入并运行、核对 Native。

## 集成、测试与保留边界

新增模块直接使用既有闭包loader、日期日历、生产Scanner产物、Research hash与真实Native测试入口，没有改变策略模块、旧行情接口或Current程序。decision.py提供候选范围门禁与显式无fallback拒绝；新证据通过独立CLI审计。**现有API/UI与正式Native path继续验证原 frozen research gate，尚未发布一个新的PASS路由。** 不能把调用方手写 findings 作为生产放行证书；将来真实放行还必须验证物理新closure、存储补充层、信号、公司行动、输入hash及完整Native reconciliation。本轮实际 gate 明确拒绝。

新增32项测试，覆盖Core不能入池证明、真正resolved边界插入、Top3集合/顺序/空日、未知共缺导致C/D误稳定、横截面资格效应、Best/Worst不填价格、候选身份/价格/行动独立门禁、无关全市场residual不阻塞、先验阈值、分红非组合上界、no Current fallback、真实Native fixture集成与normalized核对、IPO历史/未来公告约束、零量quote拒绝成交、真实mapping覆盖与中间区间结束。专项32通过；完整原生引擎开关开启后的 **468 passed / 82.25s**，1项既有websockets弃用警告。真实Strategy 2 PIT Native与orders/fills/fees/cash/holdings/final-equity/trades/open/split/terminal/daily-equity核对保持NOT_RUN。

原始DB、global master、原PIT feature store、accepted raw store、旧source artifacts与已有研究报告均保留；protected-files重新哈希全部通过，旧research物理依赖验证仍有效。未操作常驻8765服务。纠错attempt-1（Core从feature限定人口重建导致OKLO两日差异、DATE/TIMESTAMP序列化错误）与输入版本保存在本机attempt目录，失败记录未被覆盖。最终Core从原raw mapping复算，OKLO问题是SPAC→common分类窗口/feature口径差异，未编造IPO日期。

复现本机已冻结证据（如源字节变化，版本校验拒绝覆盖）：

```powershell
& .\.venv\Scripts\python.exe -B scripts/audit_pit_research_decisions.py
& .\.venv\Scripts\python.exe -B scripts/resolve_pit_decision_scope.py
& .\.venv\Scripts\python.exe -B scripts/finalize_pit_decision_acceptance.py
& .\.venv\Scripts\python.exe -B scripts/certify_pit_core_bounds.py
& .\.venv\Scripts\python.exe -B scripts/write_pit_final_report.py
$env:STOCK_RADAR_TEST_LEAN='1'
& .\.venv\Scripts\python.exe -B -m pytest -q
```

后续数据工作只按 [P0 队列](evidence/pit-research-final-priority-2026-10-07.json)推进，不改变冻结阈值。最新 [机器证据](evidence/pit-research-final-evidence-2026-10-07.json)含逐阶段物理hash；大体量逐日数据与合法来源raw留在本机 data/pit/research-final。未证明成功之前，RESEARCH-03继续OPEN/PARTIAL。
