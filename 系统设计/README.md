> 2026-10-29当前：candidate4，NOT_ACCEPTED。45回归+7独立+3补测通过，10 PASS/5 NOT_TESTED；修复网络超时后的额外等待，新部署实时成绩从零独立统计。旧candidate3已结清109条，65/105=61.90%，4迟到，全部模型复算一致；连续60尝试失败，不能用累计数通过。以[项目状态](docs/project-status.md)和[candidate4检查](docs/acceptance/runs/http-v0.4-candidate4/run.md)为准。下文candidate3的旧进度均为历史记录。

# 系统设计：实时行情预测与命中率

工作区：`D:\mycode\沧海易购1\系统设计`。当前是已批准的HTTP独立跨源研究，**开发回归通过，真实前向验收尚未通过，未正式交付**。

保留原1分钟h=1逻辑回归、三连跳两根、特征和阈值。用户已确认v0.1及CR-RT-001/002/003；确认原文和摘要在`docs/baselines/`。HTTP与训练CSV存在价量差异；本实验单独标记、单独记账，不混入原CSV、回放或历史成绩。原生同源实时路线的失败证据保留。

## 运行

双击[启动HTTP研究.cmd](启动HTTP研究.cmd)持续采集；双击[查看HTTP统计.cmd](查看HTTP统计.cmd)查看账本。每个来源只允许一个采集进程；若已有采集在运行，使用查看入口。控制台Ctrl+C停止。

也可在本目录执行：

```powershell
& '..\market-direction-ml\.venv\Scripts\python.exe' -B -X utf8 -m realtime --source http-research
& '..\market-direction-ml\.venv\Scripts\python.exe' -B -X utf8 -m realtime --source http-research --status
```

账本：`runtime/http-research/forward.sqlite3`；当前部署：`runtime/http-research/deployment.json`；固定引导及规则起点：`runtime/http-research/bootstrap.json`。一致性备份：在上述命令后使用`--backup runtime/http-research/backups/新的文件名.sqlite3`，拒绝覆盖。备份恢复时同时保存该部署配置、引导文件和对应代码；先停止写入进程，再将备份复制到新的恢复目录核验，不能直接覆盖正在使用的数据库。

原生缓存模式仍为默认`--source native`，使用原`runtime/forward.sqlite3`，不自动切换来源。它尚未获得持续落盘的实时数据。DDE保留[探测入口](探测DDE.cmd)，未取得有效行情连接；无需为了HTTP研究继续操作DDE菜单。

## 数据与计分

- HTTP固定531/印江花果红茶二期、period=0。保留raw_ts及原始量额；完整分钟结束标签显式为raw_ts+60秒，并同时要求后继源记录及2秒时钟宽限。形成中尾根不进入特征。
- 真实6000根中发现11条名义收盘边界的单价记录。仅当紧邻前根且与前收盘同价，才作为不合格分钟事件隔离；保留全部原字段和原因，不合并量额、不进入分钟模型。其他异常仍拒绝。详见[边界证据](docs/evidence/20261028-preflight/http-boundary-records.json)。
- 启动历史只暖机，首次或断线后不补发历史预测。h=1指下一有效根；wait仍有方向并计入主分母，RULE_SKIP没有概率。
- 真实持久化发布超20秒、未获回执或目标已知则排除计分。主命中率=HIT/(HIT+MISS)，另列FLAT/PENDING/UNSCORABLE、信号子集、覆盖率和Wilson区间；0分母显示暂无，少于500个计分样本显示效果样本不足。
- 价量单位差异未解释，概率未在新域校准；这项研究不证明模型有稳定优势。

## 当前证据

- [最新开发回归](docs/evidence/20261028-preflight/candidate2-frozen-regression.log)：原模型、账本、引擎、缓存、DDE及HTTP的自动检查；不是独立实时验收。
- [实际运行观察](docs/evidence/20261028-preflight/http-runtime-first-observation.json)：2026-10-28 22:28本机快照，独立部署已有6000条原始行情、0预测、0结算，数据库一致性ok，15个原模型保护文件未变。进程是否仍运行须重新核实，不能只凭快照判断。
- [HTTP历史计算冒烟](docs/evidence/20261028-preflight/http-offline-compute-smoke.json)：真实冻结HTTP窗口通过原模型概率分支，耗时约1.204秒，相关线程池均为4；未发布预测，不能代替真实p95。
- [项目状态](docs/project-status.md)、[需求](docs/requirements/realtime-v0.1.md)、[已批准跨源变更](docs/requirements/changes/source-v0.4-draft.md)、[独立验收标准](docs/acceptance/realtime-criteria-v0.1.md)。
- [测试计划](docs/testing/test-plan.md)、[用例](docs/testing/test-cases.md)、[数据](docs/testing/test-data.md)、[缺陷](docs/testing/defects.md)、[执行](docs/testing/executions/20261028-development.md)、[追踪](docs/testing/traceability-v0.1.md)、[总结](docs/testing/test-summary.md)、[AI修改记录](AI_CHANGELOG.md)。

尚欠连续60个真实可预测锚点、完整发布到未来有效根结算、真实端到端p95及15项独立验收。名义休市不代表已认证官方日历；不把历史计算概率或旧行情当成当前预测。

## 最新独立检查

当前为[candidate3](docs/candidates/http-v0.4-candidate3.json)。第一候选因锚点失效后永远PENDING、历史时点统计误计尚未发布记录而被拒绝，已保留[首败](docs/acceptance/runs/http-v0.4-candidate1/run.md)。前两候选失败证据保留；当前37项冻结回归、7个独立用例和3项补充检查通过，[15项独立检查](docs/acceptance/runs/http-v0.4-candidate3/run.md)为9 PASS、6 NOT_TESTED，仍未正式通过。

可独立复查当前账本：`python -B -X utf8 tools/audit_forward.py --output docs/acceptance/runs/新的证据目录`，请使用上述既有解释器。工具仅向新证据目录写一致性副本和报告，截止最后完成轮询以避开采集中间状态，不把空样本判成真实效果通过。当前仍需新增行情。

后续模型身份显示反例使candidate2也被拒绝；candidate3补齐model_version，状态入口展示部署/来源/模型摘要。37+7+3检查通过，[当前15项独立记录](docs/acceptance/runs/http-v0.4-candidate3/run.md)为9 PASS、6 NOT_TESTED；当前仍0真实前向预测，采集继续，不能据回放宣称实时通过。

[常规交易时段核验](docs/calendar-verification.md)：已按用户指定图片保存并逐分钟核对，周历与程序一致，AC010常规场景通过。当前10 PASS/5 NOT_TESTED；具体法定节假日依平台公告，图片其他规格不移植。代码无需改动，采集继续。

## 2026-10-29真实验收增量

用户恢复验收后已取得[真实分钟与逐条发布/结算](docs/evidence/20261029-live/publication-chain.json)，[10:58独立快照](docs/acceptance/runs/http-v0.4-candidate3/observation-20261029T1058/report.json)为4条预测、2 HIT/1 PENDING/1迟到UNSCORABLE，4条模型复算一致。仅2个计分样本，不能外推效果；wait保留在主分母，迟到不计分。

当前13 PASS/2 NOT_TESTED，未正式交付。还需连续至少60个真实可预测完整锚点和全量到期复算；早期p95=56.339秒，尚未达到20秒，首条慢记录保留。连续运行期间需保持本机唤醒和联网，不能由启动成功推断一直采集。模型、源及计分规则未改，最新状态见[项目状态](docs/project-status.md)。

11:30晨盘[独立快照](docs/acceptance/runs/http-v0.4-candidate3/observation-20261029T113002/report.json)：24条模型复算一致，主率50%（n=22），全样本p95=11.424秒、最大56.339秒；样本不足。新增[连续性检查](docs/acceptance/runs/http-v0.4-candidate3/continuity-20261029T113255/report.json)最长20，不能以累计24通过60门槛。可用既有解释器运行`tools/audit_continuity.py --self-check`或`--output 新证据目录`；只读生产库，工具原文/摘要随报告保存，不改产品。13 PASS/2 NOT_TESTED及未正式交付结论保持。

16:07[最新全量快照](docs/acceptance/runs/http-v0.4-candidate3/observation-20261029T160752/report.json)：32条模型复算一致，主率50%（n=30），p95=17.736秒，历史最长连续20。下午采集中断已如实记录；同一部署恢复为普通Hidden后台采集，PID及日志位置见runtime/http-research/collector-process.json。该文件只是定位信息，存活需核验实际进程身份及新POLL；已验证启动命令退出后的存活，未验证聊天宿主终止、机器重启或睡眠连续性。

当前可用“查看HTTP统计.cmd”查看账本；后台存在时再次启动会被同一单进程锁拒绝。没有服务、计划任务或开机自启，电脑仍需保持唤醒联网。停止或更换采集前先备份并核对本项目PID、启动时间及解释器路径，防止依据过期PID操作其他进程。完整[恢复证据](docs/evidence/20261029-live/independent-recovery-summary.json)保留；正式连续60及总体验收仍未完成。

19:08[晚盘独立快照](docs/acceptance/runs/http-v0.4-candidate3/observation-20261029T190756/report.json)：37条复算一致，54.29%（n=35），p95=17.736秒；[新晚盘连续5](docs/acceptance/runs/http-v0.4-candidate3/continuity-20261029T190756/report.json)仍未到60。真实中断回合后同PID已验证存活，另有703.066秒休市轮询空档，原因未知，不能把进程存活等同全程取数。产品/模型保持，13 PASS/2 NOT_TESTED，效果样本不足。
