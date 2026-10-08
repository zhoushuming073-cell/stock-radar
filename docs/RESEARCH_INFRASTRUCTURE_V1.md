# Research Infrastructure v1

2026-10-08：`RESEARCH_INFRASTRUCTURE_V1_FROZEN`。本地数据库主动扩建结束，维护继续。当前事实由 [冻结配置](../config/research_infrastructure_v1.json)、[最终报告](../reports/research-infrastructure-v1-finalization-2026-10-08.md) 和唯一 [当前总账](../reports/journey-2026-09-30-0651-📌当前总账.md) 管理。

本地负责规则、形态、特征、视觉样本、图表及 exploratory 策略研究。QuantConnect Cloud 后续使用自己的历史 Universe、Security Master、行情和 LEAN，独立验证冻结策略。General PIT 保持 Tier 1，供深度调查与审计；Shape Research 为 READY。本轮正式 QC 策略验证、模型训练和 Fresh 收益评估均为 NOT_RUN。

## 唯一默认研究入口

```python
from radar.research.infrastructure import shape_research_universe_v1
from radar.pit.shape import tensor, render_svg

with shape_research_universe_v1(root) as db:
    universe = db.universe_on("2026-09-29", length=126)
    sid = universe.iloc[0].security_id
    window = db.window(sid, "2026-09-29", 126)
    x = tensor(window.normalized)
    svg = render_svg(window.normalized)
    # 显式敏感性：unknown 保持 unknown，不转为 false。
    sensitivity = db.universe_on("2026-09-29", 126, include_unknown=True)
    # benchmark 必须已按决策日截断；返回原有 (date, symbol) 索引。
    factors = db.strategy2_feature_window(sid, T, spy_close, qqq_close)
```

Strategy 2、新规则策略、视觉和历史图表研究默认使用这个入口的 Universe；禁止各自按当前存活状态筛历史股票。它不会自动替换生产 Scanner 的 provider，也不会绕过原始价、横截面排名、持仓生命周期或正式组合门禁。现有完整 Scanner 与规则代码保留兼容性；新增研究接口复用原尺度不变特征公式，绝对价格/美元成交额/排名必须由相应因果数据与原合同提供，不能从规范化价格伪造。

构造函数只验证小型配置/代码锁，不打开数据库；首次读取才打开固定 Shape core 或 Fresh sidecar。它不挂载 strict historical store，不扫描 archive。旧 `ShapeResearchDatabase` 保留为冻结历史 core 的底层接口；新研究代码使用本页入口获得修正后的 Fresh 规则。

## 固定数据及合同

配置固定两个版本目录、数据库 SHA256、源 manifest 和规则/代码散列，不根据目录名字挑选“最新版本”。`shape-research-v1` 合同固定来源、price basis、confirmed/probable 默认、身份边界、拆股、缺口与隔离、退出历史保留、时间切分及五通道视觉规范化。详见 [合同](../config/shape_research_contract_v1.json) 和 [底层数据说明](SHAPE_RESEARCH_DATA_LAYER.md)。语义 hash 排除本机路径、测试耗时及创建时间；文件物理散列独立记录。

core 是原 2026-09-28 行情快照；Fresh sidecar 从已经在本机的 Alpaca SIP split 日行情生成，经历史重叠比对后追加 2026-09-29–2026-10-07。保持单 ID、同一来源系列/口径，每一行保留原快照散列；5 个历史修订冲突 ID 的追加部分隔离。core、严格 accepted raw 和原始来源字节不变。

## Fresh OOS：输入准备与正式评估分开

F = 2026-09-29。决策日期必须 >= F；20/40/60/126 session 输入允许使用 F 前已发生的历史回看，且全部 <= 决策日。Train/Validation/Test 的冻结信号日期和既有 purge/embargo 保留；旧 Test 仍属 exploratory。标签和 forward outcomes 单独保存，不能进入五通道 tensor、特征或未来成员 metadata。基准数据超过决策日直接拒绝。

`window()` 可用于 Fresh 数据准备；`training_tensor()` 拒绝 Fresh。正式 `evaluation_window(..., freeze_receipt)` 还要求模型、参数、记录时间均早于 F（有时区），并核验实际文件 SHA256、禁止 Fresh 结果调参声明。该校验不能替代可信的历史存证，更不能证明任意手写时间是真的。本轮没有声称存在真实 pre-F 冻结记录，没有构造倒签记录，没有运行 Fresh 评估。

本轮为质量检查读取过 Fresh 输入/图形，因此不能声称“Fresh 数据无人看过”。未计算策略 Fresh 收益或标签。以后才冻结的模型，需选其真实冻结之后的新决策期评估，不能把 2026-09-29 强行算作该模型的首次未触碰 OOS。

## 可重复导出与维护

```powershell
.\.venv\Scripts\python.exe -B scripts/export_shape_window.py --root . --security-id OBS-00146dacdb863d60a6e3a105 --decision-date 2026-09-29 --length 126
.\.venv\Scripts\python.exe -B scripts/verify_research_infrastructure.py
```

导出 metadata 绑定 infrastructure semantic hash、身份/日期/来源及数值散列；先保存数字窗口，再产生图片。重复导出的 tensor/SVG 一致；metadata 和身份字段不进入 tensor。检查脚本只读取源库、写一个本地样本及回执，不评价收益、不训练模型、不下载数据。

允许的数据库维护是日更、真实研究/候选/持仓触发的局部修复、定期 QA 和来源失效修复。现有日更继续维护 market 源库；它不会静默覆盖这个冻结快照。采用新数据须显式生成版本、核验来源、测试并更新相应版本记录，保留旧冻结证据。不要因日更就重新运行全市场身份/生命周期补齐。

`inventory_database_assets.py` 仅建立清单；`record_database_cleanup_results.py` 仅记录已完成动作与保留项；历史 PIT 构建/调查脚本因源代码锁、测试或报告引用而保留，均需显式调用。它们没有加入主 CLI、启动、Scanner、日更或 LEAN 自动路径。`finalize_research_infrastructure.py` 是本次审计/冻结程序，未经新的测试回执不可替换正式冻结配置。

`archive/legacy-pit/` 是冷存储，不参与 package discovery、pytest、日更、Scanner、Shape 或 LEAN。原始证据中绑定绝对路径的资料保留在原 cold source 目录，以维持历史复现。失败未发布目录没有 manifest/current 指针，运行入口不能加载；政策阻止清理的文件保留并记录。

## 已知边界与后续研究

技术 ready 83.8733% 的分母是已观测普通股 ID/session，不是完整美国历史市场。研究资格已确认的 later-disappeared 证券仍缺 35.5142% session；3,463 个有成员历史潜力但价格/流动性资格未确认的片段单列。大规模重叠窗口也不是独立试验数。拆股图形规范化不能恢复严格 PIT 执行价格或终止证券财富，完整法律身份、公告发布时间、退出经济后果仍未齐备。

规则策略：本地 Train/Validation → 冻结信号和参数 → 有效的新 Fresh 决策期 → QC 独立数据与组合执行验证。视觉策略：历史数据 → 人工标注 → Train → Validation → 真实模型冻结 → 新 Fresh → 初期冻结信号交 QC 验证执行，成熟后再考虑 QC 数据独立推理。现在可以恢复研究与训练准备；数据冻结不代表 Strategy 2 已通过验证。
