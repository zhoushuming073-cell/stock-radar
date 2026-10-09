# Quant + Vision 双阶段标注 v3：本机操作说明

## 当前状态

真实历史候选、左图和右图已生成，工程可开始人工试用。D1/D2 工程通过，D3 数据与 UI 就绪；首次用户主观反馈仍待完成。未训练模型，未证明 alpha。

正式入口：**http://localhost:8123/quant-review/v3/human/**。沿用已有本地 Label Studio 登录账号，和旧项目使用同一个服务。独立路由和数据库，不覆盖旧 Pilot。测试入口 `/quant-review/v3/smoke/` 不用于正式判断。

若服务未启动，在仓库根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_vision_label_studio.ps1
```

已有服务监听 8123 时无需再启动。服务仅监听 loopback，不上传图像或标签。

## 首批只做 10–20 张

1. 先看左侧截至 T 收盘的价格与成交量，必要时放大并点击 Recent candles。
2. 回答 Observe：观察 / 不观察 / 不确定。
3. 独立回答 Entry：当前可买 / 等回落或进一步确认 / 不买 / 不确定。“可买”只是 T 时意向，尚不知道 T+1 开盘。
4. 选置信度；原因可多选，也可不选。
5. 点击 Save blind。只有服务器持久化成功，才可点击 Reveal future。
6. 右侧独立图展示 T+1 至 T+10，灰线为 T 收盘参考，蓝线为假设下一交易日开盘参考（不可评估时无蓝线）。两图纵轴独立，左图不变。
7. 可填写事后复核原因和备注，点击 Save review。它不是盲态训练标签。
8. Next / Previous / Skip 可导航。刷新后已保存标签保留；再次显式点击 Reveal 可恢复右图与复核。Skip 不会揭示未来。

Undo 只撤销尚未保存的表单。揭示前修改会新增盲态修订；揭示后修改必须填写原因，并作为 `post_reveal_revision`，绝不替换首次盲态判断。重复图若其另一任务已揭示未来，会标为 contaminated retest，不计入干净一致性。

同一账号跨 smoke/human 的揭示也保守计入曝光。验收已揭示的 10 张唯一图（11 个正式任务）会标记并后置；仍有 290 张未曝光唯一图，正式入口优先显示这些图。曝光不代表机器测试答案成为人工标签；正式区仍是 0 条。

做完 10–20 张先反馈：图是否清晰、Observe/Entry 是否有意义、最近蜡烛是否可判断、揭示操作是否顺手。不要被右侧盈利与否反过来强迫修改首次判断。不要默认补完全部 330 张。

## 私有合同与保存

| 通道 | 版本/内容 | 访问边界 |
| --- | --- | --- |
| Q | fuzzy-shape-v1；A 强势/B 回撤/C 衰竭/D OHLCV 承接代理/E 转强/F 过度延伸 | 私有表，不显示机器分数 |
| X_left_num | x-left-num-v3；60/126×5 float64 OHLCV，原始/规范化/NPY hash | 截至 T 的冻结数值输入 |
| X_left_svg | x-left-svg-v3；shape-wrapper-blind-svg-v3，SVG/geometry hash | Stage A，仅相对百分比标尺，无代码/日期/未来 |
| H_blind | h-blind-v3；Observe、Entry、置信度、原因、任务 hash、修订 | 持久化 SQLite；首次判断不可覆盖 |
| H_review | h-review-v3；复核原因/备注 | 需已揭示，独立存储 |
| Y_future | y-future-v3；10-session，T+1 open 相对参考，+5%/−3% | 私有离线生成，仅授权 Stage B 响应 |

产物在 `.local/vision-dual-stage-v3/`；不在 Label Studio `data/` 文件根目录内，不能通过普通静态 URL 读右图。`annotations.sqlite3` 保存原始事件与全部修订；`manifest.json`、Q、左右 SVG、numeric 均为私有。认证、CSRF、用户、origin、task hash 和 revision 联合检查，GET 不会改变揭示状态。

Export 输出自己的版本化标签/事件，不含 OHLCV、身份或 Y。保存 JSON 后回收：

```powershell
.venv\Scripts\python.exe scripts/import_dual_stage_labels.py PATH_TO_EXPORT.json --origin human
```

回收器校验当前权威历史，保留按原始 hash 归档的 JSON，并分别写 blind/review/post_reveal_revision Parquet。重复导入不增加标签；错版本/错任务/错选项/伪造或陈旧事件拒绝。Smoke 单独目录，不能导入 human。

## 验证与可选机器图像导出

```powershell
.venv\Scripts\python.exe scripts/prepare_dual_stage_vision.py --verify-only
.venv\Scripts\python.exe scripts/replay_dual_stage_vision.py
```

构建命令拒绝覆盖已存在的 bundle。后续新批次需要明确版本目录，不覆盖原标签。无需重导旧 Label Studio 项目。

SVG 是人类缩放输入，普通 CNN 不直接消费 SVG XML。可选 `scripts/rasterize_dual_stage_left.cjs` 用 Sharp/libvips 固定 640×480、72 dpi、编码设置；只读左图和 manifest，记录依赖与 PNG hash，重复绘制字节比对，拒绝覆盖不同结果。设置 `STOCK_RADAR_SHARP_MODULE` 为现有 Sharp 模块路径，或通过正常 Node 依赖解析提供 Sharp。本机验证版本 Sharp 0.35.5 / libvips 8.18.7；不同字体/渲染依赖可能改变像素，不能静默混合 renderer 版本。

浏览器验收脚本 `scripts/smoke_dual_stage_vision.cjs` 使用现有 Playwright（可通过 `STOCK_RADAR_PLAYWRIGHT_MODULE` 指定模块），真实 Chrome、已有本地凭据，只写 smoke。已有 smoke 历史时拒绝重跑覆盖；本轮失败调试历史已隔离保存。

## 必须理解的限制

- 样本是宽松 Quant 选中的历史候选域，不是完整市场随机样本；不能由此宣称全美股召回率或 alpha。
- 295/300 的跨 ID 发行主体别名仍未核验；unknown membership 被排除。四个后来消失/被收购的可信锚点不等于完整退市覆盖。
- Y 是相同冻结来源的 vendor-basis 相对收益代理，零费用/零滑点，不是已认证的可执行 PIT 成交。10 日内缺价/零量/身份或价格门禁拒绝会 censored/unavailable；split/embargo 越界不读取。双阈值同一日为 ambiguous，仅保留 adverse-first 敏感性。
- 本轮 234 available、19 ambiguous、31 unavailable、16 censored；不造缺失收益。47 个 not_evaluable 仍可供观察形态，但不可当成可用未来真值。
- 正式人工反馈之前不训练 Vision-H/Vision-Y、不搜索 Fusion、不使用 Test/Fresh、不跑正式 QC。
