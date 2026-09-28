# Phase 3 开源组件审计

核对日期：2026-09-26。范围是组件选型，不代表已安装、集成或通过本项目回测验收。项目目前为 Python >=3.11、DuckDB + pandas 日线数据；Phase 2 把次日 Open 当作进场参考，并要求独立处理成本、缺失行情、样本切分和幸存者偏差。以下判断以各项目官方仓库的许可证、文档和发布页为依据。

## 决策摘要

| 组件 | 许可证与维护证据 | 本项目适配性 | Phase 3 决策 |
| --- | --- | --- | --- |
| [pluggy](https://github.com/pytest-dev/pluggy) | [MIT](https://github.com/pytest-dev/pluggy/blob/main/LICENSE)；pytest 项目维护，支持 Python >=3.10，官方示例使用 `HookspecMarker`、`HookimplMarker`、`PluginManager`。 | 适合为 StrategyPlugin 定义唯一 hook，并用宿主的 manifest 与运行时校验包住注册过程。它只负责调用与注册，不提供进程隔离、策略参数校验或回测。 | **USE DIRECTLY**：Phase 3B 已决定直接复用 pluggy；不再手写注册系统。 |
| [bt](https://github.com/pmorissette/bt) | [MIT](https://github.com/pmorissette/bt/blob/master/LICENSE)；[发布页](https://github.com/pmorissette/bt/releases)显示 2026 年持续发布，1.2.x 包含成本模型、公司行为和 pandas 兼容性更新。 | `Strategy` + `Backtest` + 价格 DataFrame 可承接组合选择、权重、调仓和交易成本。但本项目的 t 日收盘信号、t+1 日 Open 成交、缺失日线和整数股规则必须用小样本逐笔核验，不能由默认价格序列推定。 | **优先做隔离式适配原型**，用手算 golden case 对照成交日、价格、现金、费用、仓位；通过后再作为组合回测候选。 |
| [vectorbt](https://github.com/polakowo/vectorbt) | [Apache 2.0 + Commons Clause](https://github.com/polakowo/vectorbt/blob/master/LICENSE.md)，对“主要价值来自该软件功能”的有偿产品/服务设有限制；[发布页](https://github.com/polakowo/vectorbt/releases)显示 2026 年 1.x 更新。 | 向量化信号扫描、参数敏感性分析有用；`Portfolio.from_signals` 的默认执行语义不能直接证明符合次日 Open、容量/现金和真实成本模型。当前 [pyproject](https://github.com/polakowo/vectorbt/blob/master/pyproject.toml)还要求较新的 NumPy/pandas 组合，需单独验证依赖解析。 | **仅作可选研究工具**，不放入核心依赖或默认生产/展示路径；商业分发前复核许可证。 |
| [Optuna](https://github.com/optuna/optuna) | [MIT](https://github.com/optuna/optuna/blob/master/LICENSE)；[v5.0.0 发布说明](https://github.com/optuna/optuna/releases/tag/v5.0.0)表明近期维护，默认 TPE 行为有变化。 | 可搜索已冻结的策略参数，但不定义目标函数、时间切分、试验预算或防止测试集泄漏。SQLite storage/固定 seed 可帮助复现，仍应记录 Optuna 版本与 sampler。 | **延后到基线回测稳定后**；仅在 Train 调参、Validation 选型，最终 Test 保持一次性只读评估。搜索空间和目标需先由 Codex 确认。 |
| [QuantStats](https://github.com/ranaroussi/quantstats) | [Apache-2.0](https://github.com/ranaroussi/quantstats/blob/main/LICENSE.txt)；[发布页](https://github.com/ranaroussi/quantstats/releases)有 0.0.81 修复和报告测试。 | [`reports.html(returns, benchmark=..., output=...)`](https://github.com/ranaroussi/quantstats/blob/main/quantstats/reports.py)可消费已算好的日收益并生成 tear sheet；不是成交/仓位引擎。报告中的 win rate 等可能是收益期统计，不能充当逐笔交易胜率。 | **可选报告层**；先验算收益时间索引、基准对齐、风险自由利率、年化周期和关键指标，再导出 HTML。 |

## 建议的接入顺序与验收

1. 固定一个包含数据快照哈希、策略参数、成本假设、代码版本和随机种子的 run manifest。所有引擎只读同一输入，并输出标准化的 `orders/fills/positions/equity/daily_returns`，避免报告层反向决定成交逻辑。
2. 对 `bt` 做 2–3 个可手算的日线案例：t 日收盘信号、t+1 日开盘买入；跳空、缺失下一交易日、费用与整数股；逐笔差异必须解释。若默认算法无法严格实现，就保持自有薄成交适配层，不能把收盘价回测冒充开盘成交。
3. 在基线及固定 Train/Validation/Test 切分通过后，单独评估 Optuna 和 vectorbt 的效率收益。QuantStats 只读已验证的收益序列；报告同时列出成本、交易笔数、样本期和数据限制。

此处的“优先”指原型验证顺序，不构成策略有效性或许可证法律意见。

## 本地运行与界面候选

| 需求 | 成熟轮子与证据 | 建议 |
| --- | --- | --- |
| 启动、监控、取消本地任务 | Python 标准库 `subprocess` 负责启动并保存 `Popen` 句柄；[psutil](https://github.com/giampaolo/psutil)（[BSD-3](https://github.com/giampaolo/psutil/blob/master/LICENSE)）可补充 PID + 创建时间身份校验、子进程枚举、资源指标和 `wait_procs`。其[官方 API 文档](https://github.com/giampaolo/psutil/blob/master/docs/api.rst)也说明 Windows 的 `terminate()` 等同于强制结束。 | 首选 `subprocess` + 持久化 run id / PID / 启动时间 / 日志路径 / 退出码；真正需要跨进程树停止或资源监测时加 `psutil`。停止动作只针对该 run 自己启动且身份匹配的进程。 |
| 结构化配置差异 | [DeepDiff](https://github.com/qlustered/deepdiff)（[MIT](https://github.com/qlustered/deepdiff/blob/master/LICENSE)；官方仓库显示 9.1.0）可递归比较 YAML 解析后的字典、列表和数值。 | 初期用规范化 JSON + 标准库 `difflib` 生成可读 diff；若要求按字段标记增加、删除、类型/数值变化，再引入 DeepDiff。不要默认 `ignore_order=True`，策略列表顺序可能有意义；必须从 diff 中过滤凭据。 |
| 任务进度 UI | 历史调研曾评估 Streamlit 的进度组件和 [Rich](https://github.com/Textualize/rich)（[MIT](https://github.com/Textualize/rich/blob/main/LICENSE)）。 | 该建议已被单一 Web UI 架构替代。任务进度由 worker 记录 `stage/completed/total/updated_at`，Web UI 只轮询这些状态；spinner 不代表真实百分比。 |

进程状态文件或锁文件不能单独证明任务仍在运行：应结合 PID/创建时间和实际进程状态核验。百分比必须来自有明确分母的工作单元；无法测量时显示当前阶段和最近更新时间。
