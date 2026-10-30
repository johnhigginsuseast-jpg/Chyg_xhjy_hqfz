# 初始需求追踪 v0.1

阶段：开发；v0.1及CR-RT-001/002/003均已确认，详见baselines。下表“新功能结果”保留为完整需求独立验收状态；组件开发检查见执行记录，不能替代真实AC。

| 需求 | 验收 | 计划影响位置/材料 | 新功能结果 |
|---|---|---|---|
| FR-RT-001 | AC-RT-001 | 来源绑定及逐根对账；原预测来源检查的最小扩展 | NOT_TESTED |
| FR-RT-002 | AC-RT-002 | 本工作区 HTTP 采集 | NOT_TESTED |
| FR-RT-003 | AC-RT-003, AC-RT-010 | 输入校验、完整性与源修订；复用 data_loader | NOT_TESTED |
| FR-RT-004 | AC-RT-004 | 复用原 labels/features/predict；前缀对比 | NOT_TESTED |
| FR-RT-005 | AC-RT-005 | 发布/输入截止证据及预测唯一键 | NOT_TESTED |
| FR-RT-006 | AC-RT-006, AC-RT-008, AC-RT-011 | SQLite 预测/结果/事件及结算 | NOT_TESTED |
| FR-RT-007 | AC-RT-007, AC-RT-008 | 统计查询、状态守恒、置信区间 | NOT_TESTED |
| FR-RT-008 | AC-RT-009, AC-RT-010 | 源状态、重放、恢复与补数据边界 | NOT_TESTED |
| FR-RT-009 | AC-RT-012 | 控制台交互 | NOT_TESTED |
| NFR-RT-001 | AC-RT-013 | 本机真实全链路延迟测量 | NOT_TESTED |
| NFR-RT-002 | AC-RT-009, AC-RT-011 | 异常、重启、一致性备份恢复 | NOT_TESTED |
| NFR-RT-003 | AC-RT-014 | 文件边界/可信加载/原接口回归 | NOT_TESTED |
| NFR-RT-004 | AC-RT-015 | 真实前向逐项独立验收及如实效果报告 | NOT_TESTED |

本轮已执行的静态调查和旧接口历史 RULE_SKIP 检查见 [调查证据](../evidence/20261028-preflight/client-inspection.json)，仅用于判断实现路线。不是新功能测试，也不是旧工程全量重新验收。

## 当前实现映射

| 需求 | 现有代码/检查 | 尚欠证据 |
|---|---|---|
| FR-RT-001/002/003 | http_feed.py、native.py、dde.py；HTTP身份/字段/时间策略及独立引导检查；保留原生对账、DDE证据 | v0.4 HTTP研究版持续完整根/发布闭环；原生官方接口缺口保留 |
| FR-RT-004 | model.py；原模型真实概率/跳过回归 | 最终实时接口候选的完整前缀与时序检查 |
| FR-RT-005/006 | engine.py、ledger.py；发布/迟到、有效目标、状态和修订用例 | 真实发布回执→目标完成闭环 |
| FR-RT-007/009 | ledger.py、__main__.py；6/10主统计、Wilson、最近记录、今日按发布时间归组 | 固定候选真实终端/样本统计验收 |
| FR-RT-008/NFR-RT-002 | engine.py、ledger.py；重启/缺数/备份/失败回归 | 最终源真实断线恢复及持续前向 |
| NFR-RT-001/003/004 | 四线程环境、受限路径、15保护文件哈希不变 | 实时p95/60锚点及最终边界独立验收 |

测试计划、用例、数据、缺陷、执行、追踪、总结均已分别维护。AC-RT-001至015完整验收仍NOT_TESTED，必要真实源依赖BLOCKED，未以开发单测置换。

## candidate2当前独立检查映射

逐项依据：`../acceptance/runs/http-v0.4-candidate2/run.md`。上文初始NOT_TESTED表为原始状态，不覆盖本次实际检查结论。

| 需求 | 当前结果 | 依据与尚欠 |
|---|---|---|
| FR-RT-001 | PASS（v0.4研究版） | AC001；原生同源门槛不追认通过 |
| FR-RT-002/003 | NOT_TESTED（完整真实范围） | AC002/003/010尚欠真实新根/最终性及日历到期 |
| FR-RT-004 | PASS | AC004原模型、热身、开盘、跨时段规则 |
| FR-RT-005 | NOT_TESTED | AC005真实发布为0 |
| FR-RT-006 | PASS（规定的回放场景） | AC006/008/011；真实闭环另由015约束 |
| FR-RT-007 | PASS（手算/隔离统计） | AC007/008；真实效果不由夹具推断 |
| FR-RT-008 | NOT_TESTED（部分已测） | AC009 PASS，AC010尚欠 |
| FR-RT-009 | NOT_TESTED（完整终端链路） | AC012真实成功与完整停止状态尚欠 |
| NFR-RT-001 | NOT_TESTED | AC013，0发布/p95暂无 |
| NFR-RT-002 | PASS（故障注入范围） | AC009/011，实际恢复与备份验证 |
| NFR-RT-003 | PASS | AC014，15原文件不变及可信加载正反例 |
| NFR-RT-004 | NOT_TESTED | AC015，0真实前向样本 |

整体仍未通过，不进入正式交付。

## candidate3增量

FR-RT-009/AC-RT-012：修复缺失模型版本显示，控制台REPLAY全状态及中断恢复PASS。AC-RT-010：两实际观察交易日到期补测PASS，权威休市/节假日核实仍NOT_TESTED。其他结果继承重新执行的candidate3固定检查，不把旧失败追认为通过。完整15项记录：`../acceptance/runs/http-v0.4-candidate3/run.md`；当前9 PASS、6 NOT_TESTED，整体NOT_ACCEPTED。

## 用户日历证据增量

FR-RT-008/AC-RT-010：用户图片及10080分钟核对补齐常规休市依据，结合已通过的缺数/实际观察交易日到期用例，该项PASS。当前10 PASS、5 NOT_TESTED，真实前向仍未通过。具体节假日例外未推断；目标和其他产品参数保持原绑定。

## 2026-10-29真实链路增量

FR-RT-002/003 → AC002/003 → TC006/010/015 → TD012的真实形成中/后继根证据及4条逐模型审计，PASS。FR-RT-005 → AC005 → TC005/015 → 真实3条按时/1条迟到发布及回执/目标，PASS；已知目标/无回执反例仍注明隔离回放。

NFR-RT-001/004 → AC013/015 → TC009/015，正式连续60锚点场景仍NOT_TESTED。10:58仅4条发布、2可计分，早期p95=56.339秒未达20秒；不能筛掉迟到或用累计条数替代连续性。当前13 PASS/2 NOT_TESTED，NOT_ACCEPTED，权威最新结论见candidate3/run.md。

NFR-RT-001/004 → AC013/015 → TC019 → TD014：新增独立连续性工具及手算自检PASS；11:33真实副本最长20，有1个有效根未发布，其他3个补回为规则跳过，正式60仍未满足。11:30全24条模型审计一致，p95=11.424秒且原56.339秒迟到完整保留；当前仍13 PASS/2 NOT_TESTED。

FR-RT-008/NFR-RT-002及连续运行前提 → TC020 → TD015：实际后台采集在启动命令退出后存活，旧表行全部保留，0无回执预测；范围不包括聊天宿主或机器重启。AC013/015仍NOT_TESTED；16:07全32条模型复算一致、p95=17.736秒，最新采集段0与历史最长20分开记录。

19:08增量：TC020实际用户中断回合后同PID仍存活，新晚盘预测分支运行；休市703.066秒空档单列。TC015/019 → observation/continuity-20261029T190756，37条模型复算一致、新晚盘连续5。AC013/015仍NOT_TESTED，13 PASS/2 NOT_TESTED；不将该回合试验扩展为宿主完全关闭或机器重启已测。
# 2026-10-29 candidate4 增补追踪

FR-RT-009/AC-RT-013：BUG-RT-009 → TC-RT-021 → transport-cadence-repro.log（2 FAIL/2 PASS）→ candidate4-regression.log（45 PASS）。修复后实机连续60与p95尚欠，不因单元测试关闭AC013。

AC-RT-014：原15文件保护摘要及candidate4固定清单/zip；AC015：旧109条独立保存，新部署不得继承成绩。当前逐项结果以candidate4/run.md为准。

