# 测试数据说明 v0.1

- TD-RT-001：`tests/test_ledger.py`以临时目录生成固定合成预测/目标，用于 TC-RT-001 至005；部署 mode=REPLAY，与真实数据库隔离，不作为模型效果证据。
- TD-RT-002：已有真实 HTTP 历史样本 `D:\mycode\chyg-market-assistant\samples\history531.json`。只用公开名称/代码及价量字段作独立源比较，不读取其 ticket 值、不复制无关源；本模型不使用该历史训练。
- TD-RT-003：本项目原始 `2026-10-28/1分钟K线.csv`，SHA256见证据基线；未来原模型回归只读使用，不改写。其与HTTP不能因同品种名而混合。
- TD-RT-004：本轮 `candidate-531-page.json`，真实HTTP公开响应131行；能证明服务响应和品种名，不能单独证明实时持续性/最终性。

原始材料保留。缺数、迟到、异常输入由可复现合成夹具产生并明确标记，不伪装真实故障或实际行情。

- TD-RT-005：`http-evening-freshness.json`、`http-minute-observation.jsonl`及summary，真实HTTP源晚盘只读时序观察，未用于模型输入或命中率。
- TD-RT-006：`runtime/dde/inspection-20261028T203424132026.json`为用户桌面修复版探测的实际新记录：无有效Link、候选连接未建立、未读取内容/数据/执行事务；区别于此前Codex侧自检文件。

## TD-RT-007：HTTP适配器真实读取及引导

`docs/evidence/20261028-preflight/http-adapter-live-check.json`、`http-bootstrap-retry.log`、`http-adapter-bootstrap.json`。当前适配器实际取得31根及6000根；包含超时和一次HTTP Date不新鲜的拒绝。原始ticket等非行情字段丢弃。数据只用于观察/引导，不计预测和命中率。CLI正式冻结引导另存`runtime/http-research/bootstrap.json`，不是原CSV。

## TD-RT-008：HTTP不合格边界事件

`http-boundary-records.json`列实际11条原行和前根；`runtime/http-research/bootstrap.json`固定原始事件、有效窗口及规则尾状态。只能将已明确的同价相邻单价边界行隔离，不修改数值或合并量额。模型/原生规则不改；对其他边界形态拒绝。

## TD-RT-009：独立验收夹具与LIVE快照

`tools/acceptance_cases.py`在runtime临时目录创建REPLAY、SYNTHETIC账本；271根左右的交替价历史和明确的平盘/三连价路径供原模型内核验证，13条手算记录为6HIT/4MISS/1FLAT/1PENDING/1UNSCORABLE。输入/输出均非实时命中率。

`tools/audit_forward.py --self-check`验证独立算术及损坏证据拒绝；`--output 新目录`只读取生产库并创建一致性证据副本。`docs/acceptance/runs/http-v0.4-candidate2/observation-20261028T2255/`为本轮真实快照，时间以report.json为准。进程存活另外由工具会话核实，审计脚本不会以状态文件推断存活。

## TD-RT-010：补充三场景

数据生成方法完整保存在tools/acceptance_supplement.py。全部为临时REPLAY/SYNTHETIC；交易日到期使用明确的2026-10-30至11-03逻辑日期，非未来真实行情。复算器夹具的真实模型概率是本地计算，不是前向研究成绩；错误元数据/目标只注入隔离副本。完整输出candidate3-supplement.log可核对。

calendar-static-check.json仅记录已选两份行情源码的有界只读检查，未定位目标官方日历接口。其他市场的图表样例未用于本品种，不声称客户端没有其他接口，不认证节假日。

## TD-RT-011：用户提供的上市说明图片

原图、SHA256、字段采纳范围和周历核对在docs/evidence/20261028-calendar。用户明确“休市时间可以看这个”。图片代码YJHGHC，仅采纳交易时间，当前预测目标二期/531保持。法定节假日没有具体日期，不做通用假日/调休导入。

## TD-RT-012：2026-10-29真实新分钟与前向闭环

`docs/evidence/20261029-live/source-observation.sqlite3`及live-minute-proof.json：本候选10:55/10:56/10:57连续分钟的形成中价量修订、raw_ts、接收时钟、后继源记录和2秒宽限。来源/原始单位保持HTTP独立绑定；无合成行写入LIVE。

`docs/acceptance/runs/http-v0.4-candidate3/observation-20261029T1058/`为10:58:14一致性副本和报告；publication-chain.json提取4条真实发布/结算，2 HIT/1 PENDING/1迟到UNSCORABLE。少于500计分样本，不能外推效果。saved-input-profile.json是该保存真实输入的离线计算剖析，不是额外前向样本。power-events.json只保留系统电源事件元数据，未读取账户或客户端私有数据，不由其推断整个中断根因。

## TD-RT-013：实际含已计分预测的备份恢复

`runtime/http-research/backups/candidate3-first-scored.sqlite3`与新恢复目录restored-first-scored；完整SHA256和五张表逐行摘要在`docs/evidence/20261029-live/scored-backup-restore.json`。实际11预测/11回执/10有效，恢复统计3 HIT/6 MISS/1 PENDING/1 UNSCORABLE。恢复副本只查询，不作为新的LIVE部署或额外效果样本。

## TD-RT-014：连续性手算与晨盘真实副本

手算数据在tools/audit_continuity.py的self_check：有效/跳过/有效应同序列，有效/漏发/有效应分段，迟到已记录尝试保留。周历边界来自用户图片绑定。自检日志docs/evidence/20261029-live/continuity-selfcheck.log。

真实副本位于candidate3/continuity-20261029T112750及continuity-20261029T113255；每目录包含ledger.sqlite3、report.json和执行工具原文，工具SHA256为5e65397f0d2836ef6e758c994c3a71f8c6f2b3c10d827a8c495b347f589c7297。11:33报告36个处理根、序列长度3/20，10:59有效根未发布，11:13/11:20/11:27补回根属规则跳过；没有完成后价格上下文修订。数据仅用于验收，不向LIVE增加样本。

## TD-RT-015：启动生命周期及下午恢复

process-lifecycle-probe.json/check.json及runtime中的明确SYNTHETIC_PROCESS_LIFECYCLE_PROBE标记仅验证本地15秒子进程，不写市场库。independent-launch.json/liveness.json记录真实PID6456、启动时间、路径、Python内部日志绑定与已退出启动器；independent-launch-data-check.json保留旧五表行校验和0无回执预测。independent-recovery-summary.json保留默认权限停止拒绝、时间类型比较修正及获准重启的真实过程。

before-independent-launch.sqlite3为切换前实际一致性备份，含32预测及旧部署行。candidate3/observation-20261029T160752及continuity-20261029T160752为新真实副本：32条模型复算一致、最新采集段0，不与历史最长20拼接。所有路径/数字以JSON实际字段为准，不把生命周期测试标记当行情样本。

post-turn-interruption-process.json、post-turn-interruption.json及gap.json为真实中断回合后的PID身份/轮询记录，703.066秒休市空档明确保留。candidate3的observation/continuity-20261029T190756为37条真实预测及新晚盘连续5副本；原始源码/元数据随报告保存，不写合成预测或重建过去发布。
# 2026-10-29 candidate4 数据

TD-RT-016：tests/test_transport_cadence.py模拟时钟与FeedError，仅REPLAY夹具，0真实网络/模型/成绩。首次缺enabled_at_ms的夹具ERROR原文保留，补齐后才进行真实故障断言。

TD-RT-017：candidate3-settled-final.sqlite3含旧部署109预测、105可计分、4迟到、0待结算。candidate4引导由原同源完整前缀延伸为6371已完成根，保留原始规则起点、父引导及备份摘要；仅暖机，不导入旧预测成绩。

