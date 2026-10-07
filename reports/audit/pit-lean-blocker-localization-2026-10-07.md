# LEAN / PIT 阻塞只读定位 · 2026-10-07

> **状态：只读定位完成；真实 PIT Native 执行仍 BLOCKED。**
> 核对基线：main @ 412c5e464e617cf9f15b71f96ad4d481b94b9e4e。日期采用 Asia/Shanghai。
> 本文是代码与现有验收证据审计，不是新的运行验收，不创建第二份 backlog。
> 当前状态和后续工作以 [唯一当前总账](../journey-2026-09-30-0651-📌当前总账.md) 第 3.2 节为准。

## 1. 结论与验收版本边界

旧报错发生在请求构造阶段，当前版本的阻塞发生在原生 LEAN 执行前的数据门禁。未发现执行失败后自动重跑 Current Snapshot 或将 PIT 结果改写为 Current 结果的分支。

原始入口 reports/pit-acceptance-2026-10-07.md 已迁移至 [acceptance/pit-acceptance-2026-10-07.md](../acceptance/pit-acceptance-2026-10-07.md)。其中 314 passed 是第一轮本地验收记录，不能将其当作当前版本唯一证据或本次测试结果。

本次没有修改代码、策略、参数、数据或门禁，没有启动 Scanner、全期评价、原生 LEAN 或 pytest，没有生成终止支付或新的组合结果。后续提交只发布本文及导航链接。

## 2. 旧报错的准确触发点

在验收对应的历史安装修复版本 99c9282：

- [manager.py L521–525](https://github.com/zhoushuming073-cell/stock-radar/blob/99c9282/src/radar/lab/manager.py#L521-L525) 的 RunManager._prepare_runs 在 engine 为 lean 且 universe_mode 为 point_in_time 时直接抛出 ValueError：
  `LEAN PIT terminal/corporate-action support is not yet validated; use Current Snapshot`。
- 这是硬编码禁令，不是 LEAN 原生能力探测结果。请求准备失败，尚未提交 Run 入队，也没有进入 worker、integration.execute 或 normalize。
- [历史 local_api.py L597–599](https://github.com/zhoushuming073-cell/stock-radar/blob/99c9282/src/radar/local_api.py#L597-L599) 将该类 ValueError 返回为 HTTP 400。字符串中的 use Current Snapshot 是操作建议，不等于执行层已完成自动回退。

因此，只看到 worker 在 LEAN 分支前会加载 master 和 terminal，不能推断这一次旧请求已抵达该分支。

## 3. 当前四层定位

| 层次 | 直接代码证据 | 判断 |
| --- | --- | --- |
| 请求构造 | [manager.py L536–556](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/lab/manager.py#L536-L556) 构建冻结信号和 local_dependency，保存 pit_dependency / run_pit_readiness，保留 blocked attempts | 旧无条件禁令已被替换；允许保留带阻塞证据的请求 |
| 终端与输入放行 | [integration.py L29–39](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/lean/integration.py#L29-L39) 加载闭包，普通 PIT 调用 require_ready，research-grade 调用 require_research_ready | 当前拒绝发生于执行前证据门禁 |
| Corporate-action 适配 | [actions.py L61–77](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/pit/actions.py#L61-L77)、[algorithm.py L104–178](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/lean/algorithm.py#L104-L178) | 改名、审核过的正反拆股和特定美元现金收购权益已支持；一般分红、换股并购、未知回收等仍有 blocked 边界 |
| 结果处理 | [result_adapter.py L18–80](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/lean/result_adapter.py#L18-L80) 核对原生权益、现金、持仓、订单、费用，失配抛错 | 未发现自动 Current 重试或成功结果替换；NOT_RUN 不是已得到替代结果 |

当前普通 PIT 调用顺序：

请求准备 / 冻结闭包 → 入队 → worker 输入校验 → integration.require_ready → execution_inputs → prepare_bundle → invoke → normalize → finish_run。

[worker.py](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/lab/worker.py) 复核 terminal fingerprint、覆盖范围、master、feature store 等；部分本地输入异常可以更早拒绝，但不是旧字符串的触发点。

[terminal.py L180–185](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/lab/terminal.py#L180-L185) 在 terminal 两文件均不存在时返回 None；读取旧 terminal provider 不等于新的 Run corporate-action 闭包已通过。

[run.py L247–341](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/pit/run.py#L247-L341) 对普通 PIT 检查 Identity、Membership、Price、CorporateAction、Terminal、LEAN Input 六项。任一失败使 require_ready 抛出 `LEAN PIT run BLOCKED`，在生成原生输入和 invoke 前停止。身份、价格、行动问题也会连带使 LEAN Input FAIL，不能据此单独归因为 exporter 缺陷。

## 4. 已记录的实际阻塞与适配边界

以下数值来自已提交报告，未在本次重算本地数据：

- [最终工程验收](../acceptance/pit-final-acceptance-2026-10-07.md) 记录 Run 级门禁和有界 native rename / split / cash-entitlement 会计验收；完整正式请求被拒绝，未调用 native，无 Current fallback。
- [最新研究决策验收](../pit-research-final-acceptance-2026-10-07.md) 记录每日 29–72 个可能改变 Core 的未知竞争者；Core 实际候选仍有 106 个身份未决、12 个执行日期缺口及 10 个事件/价格审查目标。
- 最新决策范围七门均 FAIL：Causal integrity、Research identity、Research membership、Research price、Material corporate actions、Terminal、LEAN Input。真实 Strategy 2 PIT Native 与 reconciliation 均 NOT_RUN。
- 最新 Terminal FAIL 对应两个可能持仓身份的 mapping 连续性问题，不能解释为确认发生两次法律退市或拆股。
- 通用分红和换股并购仍未完成适配；research-grade 普通分红例外需要证据绑定且满足收益影响上界，并非默认豁免。最新报告未授予该例外。
- Native 黄金案例及 fixture 通过不代表真实全期 Strategy 2 PIT 数据已经放行。

### 两套研究门禁不能混同

[research.py L220–329](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/pit/research.py#L220-L329) 验证已有 frozen research audit、rules、closure 和物理证据；integration 的 research-grade 分支调用它。

[decision.py L131–166](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/src/radar/pit/decision.py#L131-L166) 是最新候选 / 竞争者范围诊断门禁。最新报告明确说明：该 CLI 诊断未替代既有 API / Native frozen research release path，尚未发布新 PASS 路由。不能把调用方手写 findings 或单个 ready 值当作生产放行证书。

## 5. Current 切换仅发生在独立的 Clone 新草稿分支

[lab.js L357–378](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/site/dist/lab.js#L357-L378) 在 Clone 时，如果原 Run 为 PIT 且当前 PIT 选项不可用，会将新草稿切为 current_snapshot，显示提示并等待用户点击 Run Selected。它不会改写原 Run、自动执行或替代 PIT 结果。

[Run Selected L341–347](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/site/dist/lab.js#L341-L347) 失败时只显示错误，没有 Current 重试。API 在请求未提供 universe_mode 时采用 current_snapshot 默认值；这也不是显式 point_in_time 请求失败后的自动回退。

## 6. 最小处理点（建议，未实施）

1. **旧硬编码禁令无需再修。** 若本地仍返回完全相同的旧字符串，应先核对运行目录、源版本和服务进程。旧进程未加载新代码是合理推断，本次未访问本机服务，不能确认，也没有重启。
2. **当前数据门禁保留。** 只按现有 P0 队列补足影响决策的身份、持仓执行行、映射连续性和事件 / 价格冲突，然后生成新冻结证据与闭包。不能用修改 LEAN 参数、伪造 payout、填价或改 PASS 标志解除阻塞。
3. **未来决策范围放行的最小接点在队列与 integration 之间。** 如后续发布新 release，必须绑定新物理 closure、行情补充层、信号、rules、audit 和输入 hashes，复用现有执行与核对链；不能直接以诊断 findings 放行。当前门禁失败，不实施该 release。
4. **Clone 可独立收紧。** 如要求复制时严格保留 universe 语义，可在 PIT 不可用时停止复制或要求显式选择新模式。这不会解除真实执行阻塞，未在本次新增 backlog 或改代码。

建议归属于当前总账的既有工作范围；本文不将数据可信度边界改写成新的通用软件故障。

## 7. 未来修复后的最小回归范围

本表是发生相关修改时的定向范围，不是本次执行记录。无需为本文重跑 314 项测试或 master 验收。

| 范围 | 必须观察到的行为 | 现有基础 / 最小补充 |
| --- | --- | --- |
| Manager → worker → integration | PIT 模式与闭包哈希完整传递；拒绝时 invoke 调用为零；无 Current Run、无成功结果 | 补一条跨层拒绝测试；现有门禁单测不代替此证据 |
| 数据门禁 | 身份、执行价、行动及持仓 mapping 缺陷分别准确阻塞 | test_critical_dependency_fail_safe；test_each_actual_candidate_defect_remains_blocked 及相关候选范围用例 |
| 证据冻结 | closure / audit / rules / 补充数据 / map / factor 变更后拒绝 | 复用 dependency、physical DB、frozen research acceptance、map/factor mutation 用例；仅对新增补充层追加绑定测试 |
| 行动会计 | 只验证实际修改的 rename、split/reverse_split 或 cash 情形；无重复拆股、无 last close 替代 consideration | test_native_pit_pass_actions_and_reconciliation 对应参数案例 |
| 无回退与结果核对 | 拒绝或 normalize 失配不改用 Current、不保存成功结果 | test_no_silent_execution_fallback、test_no_current_fallback_when_scoped_native_gate_fails；如改 normalize 则补失配用例 |
| Clone（仅在修改时） | PIT 不可用时不静默切换模式、不自动提交，原 Run 不变 | 该交互的定向测试 |

现有定义位于 [test_pit_run.py](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/tests/test_pit_run.py)、[test_pit_research_grade.py](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/tests/test_pit_research_grade.py)、[test_pit_decision_scope.py](https://github.com/zhoushuming073-cell/stock-radar/blob/412c5e464e617cf9f15b71f96ad4d481b94b9e4e/tests/test_pit_decision_scope.py)。

真实策略数据未来放行时，必须完成真实 native orders / fills / fees / cash / holdings / final-equity 及行动会计核对；fixture PASS 不能替代真实验收。

## 8. 本次核对与证据限制

- 直接读取固定基线的报告、当前总账、manager / worker / LEAN / PIT / API / UI 源码与相关测试定义，并对照历史 99c9282 的 manager 和 API。
- 314 / 377 / 468 等数字仅引用历史本地验收，未作为本次测试结果；本次 pytest、native 和 master 验收均未运行。
- 未读取未提交的本机大数据库、raw receipts、实时进程或实际请求，未独立确认部署状态或重算缺口。
- 代码触发位置直接核对；实际数据数量与历史运行结果采用对应报告，不声称独立复现。
