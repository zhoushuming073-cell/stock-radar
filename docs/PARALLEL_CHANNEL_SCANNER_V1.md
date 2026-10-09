# Parallel Channel Scanner v1 · 月/周震荡通道与日线回踩初筛

Status: **experimental, source-only implementation**. No learned weights, no historical market-wide efficacy, no production deployment, no broker orders.

## 研究定义

从截止决策交易日 T 的 **split-adjusted daily OHLCV** 构建 12/16/20/26 周、9/12/15/18 月的历史视图。月线**或**周线存在较清晰、横盘至缓慢上升的上下平行价格边界即可取得结构资格；若月线/周线均不合格，则拒绝。接着按最近 20 个交易日检查上升—回调小周期，以及当天是否靠近通道下沿。

长期主升涨幅和历史最大回撤**不设门槛，不计入评分**。反复测试的区间下沿/上沿、价格是否在通道内来回、向下破位和上方空间才是主要依据。边界不是数学的确界，而是容忍少量假突破的统计包络。

## 核心算法（纯过去信息）

1. 对每个候选周期使用 log 价，在每个过去窗口中对 `(log(high)+log(low)+log(close))/3` 计算 Theil–Sen 风格的 **成对斜率中位数** `b`，再计算去趋势 `log(low)-b*t` 的 14% 分位数作为下边界截距，`log(high)-b*t` 的 86% 分位数作为上边界截距。`L(t)=exp(l+b*t)`，`U(t)=exp(u+b*t)`。真实上下边界斜率可独立诊断，不强制认为真实高低点天然平行。各窗口独立拟合，不调未来收益。
2. 用 `log(high)` 和 `log(low)` 的 5-bar 局部极值找已确认拐点；每侧相距至少 3 bar 的接触才算不同测试。距拟合边界不超过通道宽度的 18% 算一次容忍区内的测试。结合时间顺序记录 L→H→L / H→L→H 的交替次数，避免简单横盘中随机噪声被误作多轮震荡。
3. 硬约束：宽度 log 口径 `[0.10, 0.85]`；整个窗口拟合的漂移在 `[-20%, +30%]`；高/低独立斜率差累积不得超过 0.60 个通道宽度；上下边界各至少有 2 个已确认测试；至少 2 次相互交替；至少 70% 收盘处于通道±10%容忍区；最后不能显著跌破下沿或跑到上沿之外。通道质量初始阈值 58/100。
4. 质量分：横向程度 18%、两端斜率一致性 18%、边界测试 26%、交替往返 23%、通道内收盘覆盖 15%。每项仅用 T 及此前数据；系数全部 **预设、未经收益优化**。选择质量最高的合格周/月窗口（同质量优先月线）。无合格通道仍返回所有窗口的失败原因，方便检查漏检。
5. 日线扫描最近 20 bar：先找此前低点→后续 4%–40% 上行，再识别距该高点回吐 15%–85%、且未破坏先前低点的回调。最近 3 根日 K 的高低点和收盘价只作下跌放缓/小幅企稳代理，永远不把单个阳线解释成真实资金承接。通道相对位置为 `(C-L)/(U-L)`；低位区为 `[-0.08,0.42]`。触发向下破位或急跌，则标为 `breakdown`，不能列为观察候选。
6. 输出 `qualified`（月或周线通道合格）、`watch`（日线靠近下沿且未触发破位/急跌）、`daily.stage`：`early_reversal`、`near_lower_wait`、`not_near_lower` 或 `breakdown`。`watch` **不是下单指令**，`early_reversal` 也不是确认获利机会。观察池排序为 75% 结构质量+25% 日线接近程度/小周期分；未发现通道时无分数。

## 本地运行

从仓库根目录，在现有 Python 环境安装项目依赖（当前 `pyproject.toml` 已包含 numpy、pandas、duckdb、PyYAML）。先保证本地日线库正常更新。**该脚本不会调用 Alpaca API，网络和券商密钥不是运行前提**。

```powershell
.\.venv\Scripts\python.exe scripts/scan_parallel_channels.py --asof 2026-10-08 --top 50 --out data/research/parallel-channel-v1/report.json
```

可限股票复核（不是默认名单）：

```powershell
.\.venv\Scripts\python.exe scripts/scan_parallel_channels.py --asof 2026-10-08 --symbols HIMS CELH BNTX CRSP UBER TOST BEAM PDD --top 20
```

可通过 CSV 验证数据入口（列必须为 `symbol,date,open,high,low,close,volume`）：

```powershell
.\.venv\Scripts\python.exe scripts/scan_parallel_channels.py --csv data/my-bars.csv --asof 2026-10-08 --top 20
```

默认 `--db data/market.duckdb`，只读查询 `assets` 当前活跃美股和 `daily_bars`（每天最多取 430 个历史交易日）；仅在显式传入 `--symbols` 时跳过资产清单。无源日线下载、无数据库写入、无后台任务、无 LEAN 调用、无 UI/旧 Scanner 替换。JSON 含数据日期、每个候选窗口的参数/失败门禁和日线阶段。可用 `--out` 保存到 **gitignored 的 `data/`**。不要将具体历史证券/日期映射、行情或个人标签上传公开仓库。

## 研究边界 / 质量控制

- **IEX vs SIP、复权、退市与身份：**研究时必须沿用同一 split-adjusted price basis。项目 `daily_bars` 当前资产名单只能给当前观察池；历史回放并无 PIT/退市完备性保证。此命令不声称形成无幸存者偏差的样本外收益证据。发生拆股、身份改变、长间隔缺价时需先审计。默认拒绝最近 205 个交易日内间隔 >12 日的样本。
- **数据时点：**脚本只取 `date<=asof`，且要求样本最后一根真实日 K 与指定 `asof` 一致；月/周末根 K 是 T 时点的**部分周期**，不是未来完整收盘。拟合包括该部分 K 的高低点，后续回放不得将其替换成事后完整月/周 K。极值拐点必须等待左右各 2 根该周期 K，因此最新可能拐点不能冒充已确认测试。
- **潜在过拟合：**当前 5 个认可形态 HIMS、CELH、BNTX、CRSP、UBER；3 个边界不明显 TOST、BEAM、PDD（人类偏好，仅作为校准参考，**不是**训练集或收益标签）。不要把这八只调整到全通过/全拒绝后宣称统计发现。下一步通过新的盲态样本人工审核漏检/误检；报告按时间段、行业、市值、流动性、分布与失败原因分层。保存每次参数变更，禁止反复偷看 Test/Fresh。
- **交易与基本面：**近支撑可能继续下跌。只做量价形态选股，无法证明真实买盘或公司基本面健康；重大事件、新闻、做空挤压、财务问题、停牌、跳空及真实订单执行必须另设研究层。不要将研究评分当做预测概率。
- **验证状态：**仅完成合成数据上的功能/因果单元测试。未在用户私有 DuckDB 上跑完整美股全市场、未对 A/B 样本真实行情做独立验收；更没有训练 Vision、执行 LEAN、修改冻结基础设施或证明 alpha。

## 后续（需要独立授权）

在本地安全行情库进行有日期界限的历史候选生成、记录抽样覆盖和被排除原因；人工评审新盲样本，评估通道有效性和稳定性；再单独对比现行 `fuzzy-shape-v1` Quant 基线，确保使用一致的 PIT eligible universe 与 Train/Validation 切分。用户明确验收后再决定是否把此模块接入 Web Scanner 或替换 v3 标签候选生成过程。不直接重写 `AGENTS.md`、`codex/tasks/ACTIVE.md` 或现有通过验收的研究合同。
