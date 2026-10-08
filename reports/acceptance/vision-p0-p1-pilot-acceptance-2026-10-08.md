# Vision P0/P1 — 真实本地 Pilot 验收（2026-10-08）

**结论：P0 PASS；P1 INFRASTRUCTURE PASS；可以开始用户本人盲态标注。**

正式 Human Ground Truth **NOT_STARTED**，模型训练 **NOT_STARTED**。本报告只验收基础设施，不能据此宣称视觉策略有效、模型赚钱、Ground Truth 完成、Fresh OOS 或 QC 视觉检验通过。

## 1. 数据和实现版本

- 测试实现提交：`efc092aa6e042e21e56365a0e6c878b8332ba803`，分支 `vision-p0-p1-infrastructure`，PR [#5](https://github.com/zhoushuming073-cell/stock-radar/pull/5)。报告和用户说明随后单独提交。
- GitHub 实际 main 经重新核验仍为 `79e42e9296be167b6f925004f0802fa384b4ce72`；原分支为 `2327bc37a99abf7beafe0e44a5429cd843d75336`。原生 fetch 最初网络失败后，经 GitHub 连接器取得实际 Git 对象，逐一核验 SHA 并保留原19个提交；提交修复时原生 push 已恢复。
- 唯一输入：冻结的 **Research Infrastructure v1** 公开读取 API；没有建立另一套真实行情库。
- Infrastructure semantic hash：`74b765911a8a4f18b2074cd8d9e529b25b54afade15309a148b0ca43340b80be`。
- Shape dataset version：`0ee4ddb99d115c467e75967c87a68cb3a55e6357c35f0e298946a5bfa3b51035`。
- Vision config：`vision-research-p0p1-v2`；seed `20261008`；PNG renderer `mplfinance-blind-v2`；label schema `human-vision-v1`。
- 原始 canonical OHLCV 与 normalized window 各250份，独立保存在本地 Parquet；不把 PNG 当唯一模型数据。
- 相同输入、config、seed、renderer 在本机重复生成，manifest、pair、task JSON、PNG 哈希与完整 bundle receipt 一致。

完整哈希及依赖版本见 [Pilot machine receipt](../evidence/vision-p0-p1-pilot-2026-10-08.json) 和 [Tests machine receipt](../evidence/vision-p0-p1-tests-2026-10-08.json)。

## 2. 实际数量与多样性

以下分布以 **250张 unique 图**为口径，重复图不增加独立样本数。

| 项目 | 实际值 |
| --- | ---: |
| Unique Single / 独立 security | 250 /250 |
| 故意重复任务 | 25（10%） |
| Single 任务总数 | 275 |
| Pair | 125 |
| Train / Validation | 175 /75 |
| 60 /126 sessions | 146 /104 |
| confirmed /probable membership | 206 /44（82.4% /17.6%） |
| unknown | 0 |
| READY /READY_WITH_MINOR_UNCERTAINTY | 129 /121 |
| 隐藏 disappeared/acquired anchors | 4 /4（2 disappeared +2 acquired） |
| Historical Test /Fresh OOS | 0 /0 |

| 年份 | Unique 图 |
| --- | ---: |
| 2021 | 23 |
| 2022 | 51 |
| 2023 | 52 |
| 2024 | 74 |
| 2025 | 50 |

Pair 自身覆盖 Train63 /Validation62，60窗口63 /126窗口62。四个既有隐藏 anchors（旧 BBBY、TWTR、ATVI、SPLK）全部实际参加抽样，标注页面不显示身份；无需替代案例。

抽样 v2 明确采用 split/year/window 分层轮流取样、每个 security 一张唯一图；pair 也在 split/window 之间轮流生成。该改动修正原有排序对年份和 pair 组别的集中，并升级 config 版本。重复任务混入正常顺序，使用相同外观的 opaque ID，避免标签者从编号识别重复。

**偏差仍然存在：** 这是冻结本地合格窗口总体中的250个 security 试点，不代表完整美国股票市场。2021覆盖较少，Train占70%；四个 anchors证明已消失/被收购股票确实进入样本，不能证明总体幸存者偏差已消除。通用 PIT 仍为 Tier1，不提升数据库等级。

## 3. 泄漏、数据和视觉质量

- Future outcome 读取为 **0**；Strategy2 score 读取为 **0**；没有根据后续涨跌挑图或修改 Strategy2。
- 可见 task JSON 严格限定：Single 的 opaque ID与 image URL；Pair 的 opaque ID与A/B URL。没有 ticker、security ID、CIK、公司名、日期、年份、绝对价格刻度、ranking 或未来收益。
- 私有 manifest 与 task 严格一一对应；foreign task、未知字段、重复任务、错误 image URL、self/same-security pair 均拒绝。
- 本地 verifier **PASS**：275个 image binding 哈希、250张唯一 PNG、500份 canonical/normalized window；数据源只读且生成前后哈希不变。
- 肉眼抽查 **20张 Single +10组 Pair**，包含两种窗口、四个 anchors及趋势/下跌/横盘/高低波动示例；选择只用窗口内 OHLCV，不读未来走势、不赋予偏好标签。
- 原 mplfinance v1 默认布局会裁切边缘蜡烛。已升级 v2，固定960×720画布和白边，重新生成全部 Pilot并重新验收；蜡烛、影线、成交量清楚，图像无身份文字/价格标签。
- canonical OHLCV hash 保持研究真相；原冻结 SVG renderer 没有替换或改语义。模板仅限制单图显示宽度并把理由多选横排，便于桌面标注。

## 4. 本机环境、实际 UI 和标签回收

主研究环境 Python3.13.7；原 uv 环境缺 pip，使用 ensurepip 本地补齐后执行 `pip install -e ".[dev]"`，没有全局升级。实际安装版本记录在 machine receipt。

Label Studio **1.23.2** 安装在独立 `.venv-label-studio`（Python3.11.9），`pip check` PASS，未混入主 `.venv`。启动脚本核验真实Python路径；服务只监听 `127.0.0.1:8123`，local-files document root仅为项目 `data/`。项目级 Local Files 存储授权仅覆盖 Pilot `images/`，不执行 Sync。修复了1.23版本中仅设置环境变量会导致图片404的问题；没有扩大目录权限。私有随机登录凭据、SQLite、浏览器 session 和所有图像均被 Git 忽略。

Browser plugin 未提供，因此使用安装好的 Chrome headless + bundled Playwright，1440×1000桌面窗口，实际点击控件、提交、换图、撤销/重做、修改、刷新读取，再从 Label Studio 官方API导出 JSON。

| 验收 | 实际结果 |
| --- | --- |
| Single | 10任务，图片加载、4种偏好、多理由、3种置信度、保存和下一张 PASS |
| Pair | 10组，A/B同时显示且同尺寸、4种偏好、3种置信度、保存和下一组 PASS |
| 修改 /撤销 | 两种项目均撤销、重做；已保存标签修改后刷新仍保留，PASS |
| 导出 /导入 | Single10 +Pair10，各自JSON→独立Parquet，PASS |
| Smoke namespace | `smoke-vision-v1`，`SMOKE / NOT HUMAN GROUND TRUTH`，与正式标签隔离 |
| 正式项目 | Single275任务 /Pair125任务，已导入，**人工标注均为0** |

最后一个已完成任务触发的 `next_task` API404是队列耗尽的预期回复，不是图片或页面错误。最终检查页面JS错误0、图片错误0。

真实导入发现 Pair-only 结果误调用 Single `overall_setup` 一致性统计；已修复并添加回归测试。Single smoke含一组 original/repeat，两个不同task ID绑定同一盲图，并可形成一致性映射/混淆分布；**这是机制验收，不是用户一致性结论**。Pair 不产生 Single 自洽率。

## 5. 门禁 A–F

| Gate | 证据 | 结果 |
| --- | --- | --- |
| A 全项目测试 | **632 passed，0 failed，0 skipped**，94.19秒；本机 `STOCK_RADAR_TEST_LEAN=1`；1个既有websockets弃用警告 | PASS |
| B 真实 Pilot | 250unique +25repeat +125pair；真实冻结入口 | PASS |
| C Bundle verifier | cardinality /hash /mapping /split /membership /metadata /窗口截止检查 | PASS |
| D Single UI | 浏览器10任务，保存、下一张、撤销、修改 | PASS |
| E Pair UI | 浏览器10组，双图、保存、下一组、撤销、修改 | PASS |
| F 导出导入 | 两类分别导出10条，分别导入隔离smoke输出 | PASS |

完整测试保留原595项、分支原9项及本轮28项。新增覆盖合同篡改、未来/身份字段、错误哈希、Test/Fresh/unknown拒绝、重复映射、pair多样性、裁切边界和Pair-only导入统计。

Native LEAN仅作为原项目回归测试运行；本轮没有执行新的QC视觉验证、模型训练或视觉回测。没有修改冻结 infrastructure、PIT/Shape语义、数据库、生产LEAN或QC smoke。

全部门禁通过后，PR#5已从Draft转Ready，重新核验实际main仍为 `79e42e9...`、PR head为 `1f9ab7b...`，通过普通GitHub merge API（含expected head校验）成功合并；未绕过保护。实际merge commit为 **`8f20a8bb843801b3b9bd61fc5f8d2a9fd835a99d`**，本机已fast-forward到该合并版本。研究计划和唯一当前总账在合并后更新。普通push网络间歇失败的文档提交通过连接器逐一核验tree SHA并用expected_sha保护分支更新，未覆盖新提交。

## 6. 现在怎么开始

**可以。任务已在本机导入，不用你再找JSON。**

1. 在 stock-radar 文件夹运行 `scripts/start_vision_label_studio.ps1`（本机已经安装，无需 `-Install`）。
2. 打开 `http://localhost:8123/projects/1/data`，登录账号/密码见本机 `data/vision-research/label-studio/local-login.json`，点击 **Label All Tasks**。
3. 先做 **50张 Single**，按你自己的直觉选偏好、理由和置信度。
4. 再到 `http://localhost:8123/projects/3/data` 做 **25组 Pair**，然后暂停，让 Codex 做第一次分布和一致性检查。
5. 不进入名称含SMOKE的验收项目；不查ticker或后来走势；不确定就选“看不懂/难判断”。

其他机器导入所需模板、JSON、本地图片授权和两类导出命令见 [操作说明](../../docs/VISION_LABELING_INFRASTRUCTURE.md)。正式标签只由用户本人产生；Codex负责生成、核验、保存、导出和质量汇总。

最终阶段：**Human Ground Truth Labeling READY / NOT_STARTED；Vision Model Training NOT_STARTED；Historical Test UNTOUCHED FOR THIS MODEL；Fresh OOS NOT_RUN；QC Visual Validation NOT_RUN。** P2须等待用户第一批真实标注和一致性/分布检查，当前不进入。
