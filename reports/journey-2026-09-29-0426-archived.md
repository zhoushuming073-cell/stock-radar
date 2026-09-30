> **Status: 🗂️ ARCHIVED**
>
> **Role:** Historical mixed planning/research record. Surviving open items were migrated into the current active journey. Do not execute this file as a current backlog.
> **Current status:** `reports/journey-2026-09-30-0651-active.md`
>
# Stock Radar Journey — 2026-09-29

> 本日志只记录本次新增计划与研究基础设施方向；既有的插件边界、As-Of 因果回放、PIT 限制等问题继续以 reports/journey-2026-09-30-0651-active.md 为准，不在这里重复展开。
>
> 基线：main @ 1d6026b1e4ac03d14c1c15f769f19b3a3fe0b691

---

## 1. 三策略研究后的数据导出需求

今天已经出现了“同一天跑多组策略、准备写正式研究报告”的实际需求。

当前单个 Run 的核心结果保存在：

~~~text
data/strategy-lab/runs.sqlite3
~~~

它足以恢复单次 Scanner / Backtest 的：

- run metadata
- strategy/version
- resolved config
- research hash / data fingerprint / code fingerprint
- Scanner metrics
- candidate snapshots
- causal features
- diagnostic scores / probabilities
- forward labels / censoring
- Backtest equity / trades / events

因此，runs.sqlite3 仍然是本地不可变运行证据的重要来源。

但后续正式研究不能只依赖“把一个 SQLite 文件交出去再临时分析”的方式。

### 计划：建立 Research Export Bundle

未来每次多策略实验应支持导出一个独立研究包，例如：

~~~text
experiment_2026-09-29_xxx/
├── manifest.json
├── experiment_summary.csv
├── runs/
│   ├── <run_id_A>/
│   │   ├── run.json
│   │   ├── metrics.json
│   │   ├── candidates.parquet
│   │   └── candidates.csv
│   ├── <run_id_B>/
│   └── <run_id_C>/
├── comparisons/
│   ├── topk_metrics.csv
│   ├── candidate_overlap.csv
│   ├── regime_breakdown.csv
│   └── risk_summary.csv
└── provenance/
    ├── hashes.json
    └── environment.json
~~~

CSV 方便人工查看；Parquet 用于完整、较大的 candidate-level 数据；JSON 保存配置、元数据、审计和 hash。

导出包必须是“实验级”而不是“单 Run 级”，以支持：

- 多策略比较；
- Train / Validation 对照；
- 多参数实验；
- candidate overlap；
- Precision / Lift / Event Precision / Event Lift；
- MFE / MAE / falling-knife；
- regime stability；
- censoring；
- filter funnel；
- 后续自动生成研究报告。

### 报告目标

后续正式报告不只展示收益率或一张图，而应能够回答：

~~~text
策略是否提高 favorable forward outcome 的密度？
Train → Validation 是否保持？
Event 指标是否稳定？
风险画像是否恶化？
三个策略选中的股票有多大重叠？
哪些候选是某策略独有？
不同市场环境下是否稳定？
~~~

研究限制、数据偏差和审计信息必须与结果一起导出，不能只保留漂亮指标。

---

## 2. 未来寻找“历史每日盘前 NASDAQ 数据库”

新增数据方向：

> 寻找一份可用于历史回放的、按交易日保存的 NASDAQ 盘前市场数据源/数据库。

目的不是直接预测单只股票，而是给未来 Scanner / Backtest 一个“历史今天是否适合交易”的市场环境判断变量。

概念上：

~~~text
历史交易日 t 的盘前 NASDAQ 状态
        ↓
Host-owned causal market context
        ↓
是否适合当天继续承担高 Beta / 科技股风险
        ↓
Scanner / model context
~~~

未来需要调研的内容包括：

- 历史覆盖起止时间；
- 盘前时间粒度；
- 是否能明确到 timestamp；
- 是否包含 Nasdaq-100 / NASDAQ 相关指数或期货代理；
- 数据是否经过后续回溯调整；
- 数据许可证与成本；
- 是否允许本地历史研究；
- 缺失日与异常日处理；
- 时区 / DST；
- 数据发布时间与可用时间；
- 是否能做到严格 as_of_timestamp 截断。

### 核心要求

历史日期 t 的模型只能看到当时盘前已经发生的数据。

不能因为数据库今天已经完整，就把当日开盘以后、收盘以后或后续修订的数据混入“盘前判断”。

未来这条数据线应由 Host 构造成因果特征，而不是让策略插件任意读取原始数据库。

可能研究的特征方向：

- premarket return；
- premarket realized volatility；
- gap / overnight risk；
- Nasdaq 相对 SPY / Dow 的强弱；
- risk-on / risk-off regime；
- 盘前异常波动；
- 与 ES / NQ / YM 的联合 context。

该数据源目前只是未来规划，不影响现阶段 Scanner 研究继续进行。

---

## 3. 建立真正的 Experiment Platform / System

随着多组实验数量增加，单个 Run 页面和手工比对会很快不够用。

如果一次实验包含：

~~~text
多策略
× 多参数
× Train / Validation
× 多个 evaluation setting
~~~

运行时间可能从分钟延伸到数小时甚至更长。

因此未来需要把“Experiment”升级成一等实体，而不是若干 Run 的临时集合。

### Experiment 应拥有自己的身份

建议至少记录：

~~~text
experiment_id
name
research_question
created_at
git_commit
dataset snapshot
strategies
parameter grid
evaluation grid
split policy
run_ids
status
progress
experiment hash
notes
~~~

### 长时间实验需要的平台能力

未来 Experiment Platform 需要考虑：

- 队列；
- 并发上限；
- 每个 variant 的实时状态；
- 总体进度；
- ETA 仅作为估计而非研究证据；
- cancel；
- restart/recovery；
- 浏览器刷新后恢复；
- 单个 variant 失败但整个实验仍能审计；
- worker 日志；
- artifact hash；
- 完成后自动汇总；
- 实验级 Compare；
- 一键导出完整 Research Bundle。

### 研究层面的要求

Experiment Platform 不能只做“批量跑参数”。

它还应帮助控制 researcher degrees of freedom：

- 保存所有尝试过的 variants；
- 不只保存赢家；
- 记录预先提出的 research question；
- 记录参数搜索空间；
- 明确 Train / Validation / Fresh OOS 的使用边界；
- 避免 Test 被实验搜索直接使用。

---

## 4. UI 继续优化

当前单一 Web UI 架构继续保留。

后续 UI 优化重点从“能运行”转向“适合长期研究”。

### Scanner

优先继续优化：

- 核心指标首屏层级；
- Observation vs Event 指标切换；
- candidate inspector；
- candidate-level causal feature / diagnostics 展示；
- filter funnel 完整阶段；
- censoring 可见性；
- run audit；
- Research Export 入口。

### Experiments

这是下一阶段 UI 重点。

需要逐步支持：

- experiment cards；
- 运行中总体进度；
- variant matrix；
- 多策略比较；
- Train / Validation 并列；
- completed / failed / cancelled 状态；
- experiment-level metrics；
- long-running job monitoring；
- 导出按钮；
- 报告生成入口。

### Compare

未来 Compare 不应只比较 Backtest 总收益，还应能够比较 Scanner：

~~~text
Precision@K
Lift@K
Event Precision@K
Event Lift@K
MFE
MAE
falling-knife rate
censoring
regime stability
candidate overlap
~~~

UI 改进不得改变底层 research semantics。

---

## 5. 持续 Bug Mining

下一阶段仍然需要持续主动挖掘 bug，但避免“为了重构而重构”。

既有已知研究正确性 backlog 不在本日志重复。

新增的 bug mining 重点转向系统性边界。

### 长时间 / 多实验运行

重点检查：

- worker 并发竞争；
- SQLite WAL contention；
- queued/running 状态丢失；
- 浏览器刷新后的状态恢复；
- API 返回旧状态；
- process crash 后 zombie run；
- cancellation 边界；
- 重启服务后 run provenance 是否仍一致；
- experiment 部分失败时汇总是否错误。

### 数据导出

重点检查：

- 导出是否遗漏 candidate rows；
- JSON float / null / bool 序列化一致性；
- CSV 与 Parquet 是否同一语义；
- metrics 是否和原 Run hash 对得上；
- experiment summary 是否错误混合不同 evaluation 定义；
- Top-K 不一致时是否错误直接比较；
- 导出后是否能验证 artifact integrity。

### Scanner / Compare

继续寻找：

- UI 与后端指标定义不一致；
- event 与 observation 混淆；
- censored row 被误算进 denominator；
- 不同 success_rule 的 run 被错误横向比较；
- 不同 label_version / feature_version 被放进同一汇总而无提示；
- historical legacy run 被新语义重新解释。

### 因果性

后续仍需通过独立 contract test 防止新 feature 引入未来信息。

特别是未来加入：

~~~text
NASDAQ premarket
ES / NQ / YM
rolling ML
~~~

之后，必须继续做 as-of / timestamp 级因果审计。

---

## 6. 近期路线

当前建议顺序：

~~~text
1. 继续保存并分析现有三策略实验
2. 设计 Experiment-level Research Export
3. 建立更完整的 Experiment Platform
4. 优化 Scanner / Experiments / Compare UI
5. 持续 bug mining 与 artifact integrity 检查
6. 调研历史每日盘前 NASDAQ 数据源
7. 后续接入 ES / NQ / YM 与盘前市场 context
8. 再进入更大规模、长时间的系统实验
~~~

其中“历史盘前 NASDAQ 数据库”与 PIT Security Master 是两个不同问题。

前者主要用于：

> 历史当天的市场环境 / 是否适合承担风险。

后者主要用于：

> 历史当天真实存在且可研究的股票 universe。

二者后续需要分别审计。
