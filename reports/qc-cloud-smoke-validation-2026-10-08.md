# QuantConnect Cloud smoke 重测 · 2026-10-08

**两份真实 Cloud 回测的数据检查均显示 PASS；完整 Logs/Results JSON 尚未下载导入，整体 smoke 门禁仍为 PARTIAL。Layer1/2/3 NOT_RUN，正式 PIT 仍 BLOCKED。**

用户已经本人登录，并授权 Codex 重测昨天中断的 Cloud 工作。本轮在现有 QC Python 项目 `37482228` 写入生成脚本、构建并运行，没有使用 paid API/CLI、Object Store 或原始行情导出。机器证据见 [Cloud observations](evidence/qc-cloud-smoke-validation-2026-10-08.json)，工程范围见 [准备验收](qc-cloud-validation-readiness-2026-10-07.md)。

## 实际 Cloud 结果

| Case | 最终实际 Backtest ID | 引擎结果 | 完整网页短摘要 |
|---|---|---|---|
| FB→META，2022-06-06至06-13 | [3158f5e575fa21e150ff36e066659c55](https://www.quantconnect.com/project/37482228/3158f5e575fa21e150ff36e066659c55) | Completed，1.06秒，69,398 data points | history_access / stable_control / security_master / mapping / split_history 全true；status PASS |
| NVDA拆股，2024-06-06至06-12 | [730eb8a3ad8052280ce66a16b25cd8ec](https://www.quantconnect.com/project/37482228/730eb8a3ad8052280ce66a16b25cd8ec) | Completed，1.10秒，57,861 data points | 同五项全true；status PASS |

引擎版本 `2.5.0.0.18171`。最终两项 `SRQC_SMOKE` 短摘要可完整读取并解析，五项检查全部通过。完整 `SRQC1` begin/row/end回执写入Log，仍待实际下载验证；没有根据短摘要创建可解锁后续运行的 `quantconnect_cloud_download` receipt。当前来源明确为 `quantconnect_cloud_terminal_ui_observation`。

早期诊断版本实际编号 `7e369fbce9c8de4c6f7a057ea26e88e3`（mapping）与 `7e755bafd6b89a1a57daaf57ac1aba6b`（split）也观察到五项通过及end PASS，但Debug长消息被截短。该版本观察到code_hash `186354358c046fe78412d216ad3eb0bf1f6d42b8ad64efd56cd97d5310f8c752`，end body_hash分别为 `8bd5f76797b2b9af709ad699455603dcbfb9d047db5a0d73a5a6e4375421dcde` / `629ddd6dafcbb43ddd5560db1edaf28b21f2ff35f62bd764e3aa0c1f0d561f1d`。只作为旧版诊断观察保留，不认为已经重新计算完整body或验证当前freeze。

## 修复的历史身份问题

前一版用字符串 `add_equity('FB')` 订阅历史案例。实际Cloud终端却显示FB的2025年map/factor起始日期调整，说明该调用按当前同名ticker定位了不同证券。仅“引擎Completed”无法证明历史身份正确。

现在按回测起始历史日期调用 `SecurityIdentifier.generate_equity(..., mapping_resolve_date=first)`，构建 `Symbol`，再用 `add_security(Symbol, ...)` 订阅。执行adapter也对已验证SID使用该typed接口。解析日期固定为研究历史日期，不用今天的ticker名单替代。依据 [QC Security Identifiers](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/security-identifiers) 和 [官方generate_equity接口](https://www.lean.io/docs/v2/lean-engine/class-reference/py/QuantConnect/SecurityIdentifier/)。

该适配修复后的首次映射运行 `7d4fdb8f8872b6ada6298649b906f603` 引擎Completed，2025起始日期警告不再出现，但当时未取到日志，未据此声称PASS。随后通过Debug诊断确认五项检查通过。核对官方文档后，将完整回执保留在Log，Debug只输出小于200字符的摘要，并再次运行上述两个最终编号。此前回测记录保留为故障依据。依据[QC日志说明](https://www.quantconnect.com/docs/v2/writing-algorithms/logging)，Debug存在单条200字符及速率限制，不能作为长回执传输机制。

## 当前唯一阻塞

结果页位于嵌套iframe。浏览器控制对Logs、Download Results及回测列表内容的点击报告拦截或目标失效，键盘焦点也不可用。尝试结果直达链接及直接打开既有编辑器页面后，仍无法操作结果webview。Windows Computer Use初始化亦不可用。编辑器和Backtest工具栏可正常操作，因此真实Cloud运行已经完成。

尚缺两份完整下载Logs与两份Results JSON，不能执行正式import，不能验证整个输出body哈希。网页终端短摘要的PASS不替代完整begin/row/end回执验证。根据 [QC结果页文档](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results)，正常下载入口是 **Logs → Download Logs** 和 **Overview → Download Results**；保留在 [操作说明](../docs/QUANTCONNECT_FREE_VALIDATION.md) 供需要接管时使用。用户无需再次登录或提供凭据。

取得原始下载回执后，由Codex运行既有import命令；两份完整smoke验收PASS后才stage首日Layer1。当前本地解锁检查仍会拒绝缺失回执，不通过fixture或终端截短文本旁路。没有执行大规模QC股票池、策略候选或组合收益验证；P0人工案例数仍UNKNOWN。

## 本地验证与边界

原有468项测试保留，新增39项；完整Native-inclusive套件 **507 passed，83.78秒**，专项 **39 passed，4.71秒**。新增历史ticker复用回归直接执行smoke初始化，并要求按2022-06-06解析FB、使用历史Symbol订阅、RAW且不fill-forward。日志传输回归模拟Debug的200字符截断，确认完整Log仍能经parser验证，同时短摘要完整可读。只有既有websockets deprecation warning。

本轮复核24项保护文件，23项冻结数据库/规则/PIT证据的SHA-256一致。唯一变化是实时 `data/market.duckdb`：既有Windows任务 `StockRadar-DailyUpdate` 于2026-10-08 08:51:56启动，状态succeeded，新增13,899 bars；文件修改时刻08:55:21与任务窗口一致。[归因及前后哈希](evidence/qc-protected-verification-2026-10-08.json)。本专项未修改策略、参数、数据库、accepted stores、生产LEAN或既有PIT证据，也未回滚既有日更任务。工程freeze semantic hash为 `3bb8d78981ece5acf36189f964e74fa8e0c770ea00ff419848da516fd1a96caa`；C signal hash仍为 `afa1c1d3bc2d05cded3b6874089358f0c1dc81433964a9dbb9ccb9b3a01f002c`。C信号是诊断冻结输入，不是正式PIT release。

现阶段结论只覆盖Free账号的小窗口数据/身份/映射/拆股访问。它不能证明整个数据库无幸存者偏差，不能解决每日29–72 unknown competitors，也不能解除真实PIT Native与reconciliation的既有门禁。
