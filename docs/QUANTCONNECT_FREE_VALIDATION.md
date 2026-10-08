# QuantConnect Free Cloud 操作说明

2026-10-08：用户已本人登录，Codex已运行两份真实smoke。四份实际下载文件已导入，完整parser验收两份smoke均PASS。首日Layer1引擎Completed，完整数据比较尚未验收。后续批次及参考数据明细导出因平台实际Terms 2.6警告暂缓。详见[实际重测报告](../reports/qc-cloud-smoke-validation-2026-10-08.md)。

> 当前限制：以下stage/import/detail流程为原工程复现说明，后续外部参考数据比较暂缓执行。QC最新2.6条款及实际构建警告见报告；应优先在平台内完成比较，或先明确允许导出的输出范围。

## 下载步骤（已完成，保留供复现）

无需重新登录或重建项目。在现有项目的 **Backtests Results** 中选择对应回测：

1. `SRQC-smoke-mapping`：最终版本编号 `3158f5e575fa21e150ff36e066659c55`。
2. `SRQC-smoke-split`：最终版本编号 `730eb8a3ad8052280ce66a16b25cd8ec`。
3. 各点 **Logs → Download Logs**，再点 **Overview → Download Results**。保存到下述results目录；解析和对比由Codex处理。显示时间以QC网页为准，不作为研究as-of日期。

以下保留从零操作说明供复现。无需提供密码、API Token或信用卡。

## 首先运行两份 smoke

在 Projects 页面点击 **Create New Algorithm**，选择 Python。项目名分别使用 `SRQC-smoke-mapping` 和 `SRQC-smoke-split`。这与[官方项目流程](https://www.quantconnect.com/docs/v2/cloud-platform/getting-started)一致。

| QC项目 | 网页文件 | 本地文件（仓库根目录下） | 检查范围 |
|---|---|---|---|
| SRQC-smoke-mapping | main.py | quantconnect-validation/projects/smoke-mapping/main.py | 2022-06-06至06-13，FB→META、MSFT/SPY控制、原始历史和Security Master |
| SRQC-smoke-split | main.py | quantconnect-validation/projects/smoke-split/main.py | 2024-06-06至06-12，NVDA拆股、MSFT/SPY控制、typed历史接口 |

每份项目只需：打开本地对应的 `main.py` → 全选复制 → 网页 `main.py` 全选替换 → 点击顶部齿轮 **Build** → 点击顶部 **Backtest**。代码自动命名回测，不需要填写参数。默认 `research.ipynb` 可以保留。`upload-manifest.json` 留在本地，不上传。

回测结束后，在结果页 **Logs** 下载日志；在 **Overview** 下载结果JSON。文件保存到 `quantconnect-validation/results/`，分别命名：

```text
smoke-mapping.log
smoke-mapping.json
smoke-split.log
smoke-split.json
```

记下地址中的 Backtest ID。只导入下载的派生结果和实际回测订单；不下载QC行情数据库。界面下载位置依据[官方结果页说明](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results)。

## 本地导入（由Codex执行）

在 Stock Radar 仓库根目录的 PowerShell 中执行，把末尾 ID 换为实际值：

```powershell
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py import --project quantconnect-validation/projects/smoke-mapping --log quantconnect-validation/results/smoke-mapping.log --results quantconnect-validation/results/smoke-mapping.json --backtest-id 实际ID
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py import --project quantconnect-validation/projects/smoke-split --log quantconnect-validation/results/smoke-split.log --results quantconnect-validation/results/smoke-split.json --backtest-id 实际ID
```

解析器检查begin/end、顺序、哈希、实际结果JSON、smoke五项布尔检查。两份真正的PASS齐备后才允许生成可运行的Layer1/2项目。本地单元测试、预览包、失败或被截断日志都不能解锁。

## 第一份历史Core验证

先执行：

```powershell
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py stage --run layer1-2024-09-30
```

上传/复制 `quantconnect-validation/work/layer1-2024-09-30/upload-manifest.json` 的 `upload` 字典列出的全部 `.py` 文件。网页文件名与本地文件名完全相同。`main.py` 替换默认文件；其余文件在右侧 Explorer/Workspace 点新建文件，输入对应文件名，再粘贴内容。这是[官方文件管理](https://www.quantconnect.com/docs/v2/cloud-platform/projects/files)支持的路径，不依赖API上传。

点击Build、Backtest。下载日志及结果JSON为 `layer1-2024-09-30.log/.json`。导入时把smoke命令的project/log/results改为该run，再执行：

```powershell
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py compare --layer layer1
```

第一日只算pilot；缺少剩余234日会明确显示PARTIAL及missing_runs。后续日期预先固定在 `campaign.json`，依次stage，保持相同Core规则，不按结果调整日期或门槛。

每日记录含数量、交集下界、Jaccard上下界、Top1000重合下界、边界差异、完整unknown竞争者分类、冲突哈希和25个样本。身份未确认时，不把字符串重合作为确认交集。unknown行格式为 `[本地索引, 分类码, 原因码, QC排名, 条件位图]`，本地索引由同一包的manifest映射回UID；位1/2/4/8/16/32/64依次表示存在、完整126日、价格、20日均额、已观察日最低额、进入Core、950–1050边界。

分类码0/1/2/3/4分别为QC Confirms Out / In / Borderline / Identity-Lifecycle Conflict / Coverage Unknown。QC历史数据不足或不在Morningstar范围内，保留Unknown。原因码见 `cloud/membership.py`，不能把无数据解释成Out。

样本不代表完整冲突清单。需要完整详情的日期，按固定32桶运行：

```powershell
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py stage --run layer1-detail-2024-09-30-b00
```

桶号为b00至b31；每桶重算相同历史Core，输出相应派生冲突ID。所有桶须与主回执的QC membership hash一致。超日志预算直接报错，不截断后假称完整。

## Layer2：同源策略，不是另写公式

两份smoke通过后，生成首日：

```powershell
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py stage --run layer2-2024-09-30
```

同样按manifest列出的文件复制。输入只有本地比较基线与冻结规则；QC侧股票池、原始价格、拆股和特征数据都来自QC。特征函数、因果拆股处理、Elasticity、策略插件和选择adapter来自源码生成快照。先在QC全体历史可交易普通股上计算Elasticity横截面，再限制到QC Core。比较Core对Core的日候选、selected、Top3/Top5及排名。

结果按相同命名规则下载、导入，执行 `compare --layer layer2`。正式全日期推进前须验证pilot的实际运行时间/内存；本地文件配额合格不等于Cloud资源已实测。

## Layer3：冻结信号执行

1,264条C候选信号已冻结，标记为诊断输入，不是已经放行的正式PIT Run。Layer1实际回执导入后运行：

```powershell
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py bindings
```

程序复用已有本地身份验收：仅当本地C候选身份已经PASS、QC首次信号日的历史CIK/class及SID一致时，自动形成绑定。回执必须来自实际Cloud、属于当前源码/输入，且保留UID字典和证据哈希。不会要求重新人工审查全部327个UID；未决或冲突项才进入官方证据调查。调查后同一命令补入机器规则PASS的案例。

完整且无SID别名冲突的绑定放在私有 `results/accepted-bindings.json`，随后stage `layer3-frozen-C`。每项含SID、历史ticker、首次可用日、证据路径/哈希及验证标记；stage会重新检查实际QC回执或官方原始证据，不能凭标记直接放行。

Layer3是连续完整组合窗口2024-09-30至2025-09-22，信号至2025-09-08。不能按月份重置现金和持仓。云端消费同一信号，原执行policy来自源码快照，使用QC原生持仓/现金、RAW分钟数据和corporate actions。Open基准通过09:31收到的09:30分钟Open填单；订单时间不倒填。分钟持仓标价、分红与原生退市处理的模型差异必须对比，不能宣称天然相同。

除日志和结果JSON，还取回结果页的Orders/Trades CSV。QC原始行情、因子文件和全市场数据不取回。原始Downloaded Results保留订单；若缺逐fill/exit细节，预留 `layer3-detail-b000` 至 `b127`，每份仍执行整个连续窗口，只分桶输出实际交易派生记录。使用 `merge-execution-details --summary 主回执 --details-directory results目录` 合并；缺桶、重复、不同fill/trade哈希均不通过。

本地正式PIT Native仍NOT_RUN；`compare --layer layer3` 会显示 `BASELINE_NOT_RUN_NO_CURRENT_FALLBACK`。未来实际PIT结果用 `compare-execution --cloud-receipt 云回执 --results QC结果JSON --local-baseline 本地PIT派生封装JSON` 对比。封装必须声明真实LEAN、point_in_time、PASS、同一signal_hash及scoped gates通过，含metrics/orders/actions；Current结果不被接受。

## 工程检查与数据边界

```powershell
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py verify
.\.venv\Scripts\python.exe -B quantconnect-validation/local.py quota
```

Free配额按项目≤25个文件、文件≤32KB、约10KB日志适配；本工程预留默认notebook，限制24个上传文件/32,000字节，以及8,000字节派生日志。不写Object Store，不用收费API/CLI，不使用公开远程托管。[官方资源说明](https://www.quantconnect.com/docs/v2/cloud-platform/organizations/resources)；[Object Store权限](https://www.quantconnect.com/docs/v2/cloud-platform/object-store)。

`results/` 和 `work/` 被Git忽略。上传文件只来自本项目的生成清单；本地signals含自己的因果reference price/ADV，不是QC数据导出。QC输出仅限研究判断、身份冲突与回测交易结果。官方证据schema在 `schemas/official-evidence.schema.json`，PASS/FAIL由 `evidence.py` 的哈希、来源、时间和身份规则产生；不会自动改写原master。
