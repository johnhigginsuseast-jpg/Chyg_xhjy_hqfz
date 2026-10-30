# 实际测试执行记录 v0.1

环境：Windows，既有Python3.12.14，无新增依赖。命令在前端目录执行，前缀为 ../market-direction-ml/.venv/Scripts/python.exe -B -X utf8。基线确认见docs/baselines/v0.1。

| 轮次/命令 | 实际结果 | 原始证据 |
|---|---|---|
| 初轮 -m unittest discover -s tests -v | FAIL：字段校验、Windows连接清理和p95=2.7326365秒等 | ../../evidence/development/unit-first.log |
| 修复后完整10项 | PASS，25.429秒；p95约0.68秒，原Ledger历史点/修订/今日对齐 | ../../evidence/development/unit-after-fixes.log |
| 候选1完整12项 | FAIL，70.316秒，p95=2.6938994秒；其余通过，不覆盖首败 | ../../evidence/development/candidate1-regression.log |
| 候选2完整14项 | PASS，24.936秒，p95=0.511098秒；增加解析缓存/独占端口 | ../../evidence/development/candidate2-regression.log |
| 候选3完整16项 | PASS，43.102秒，p95=1.207069秒；增加午夜/无回执/外部署和状态边界 | ../../evidence/development/candidate3-regression.log |
| 候选4独立16项 | PASS，50.356秒，p95=1.270355秒 | ../../acceptance/runs/frontend-v0.1-candidate4/regression.log；../../evidence/development/performance-1793274651556964400.json |
| 候选4 tools/acceptance_checks.py | 4组PASS，未完成/完成POLL、晚诊断、完整分页组合筛选、实际query_only、默认240/空图/错误模型绑定 | ../../acceptance/runs/frontend-v0.1-candidate4/supplementary.log |
| 候选4 tools/verify_live.py | PASS；真实65计分/42HIT/23MISS，49趋势点、600根行情、原行/回执/结算、源码/模型保护全部一致 | ../../acceptance/runs/frontend-v0.1-candidate4/live-check.log；../../evidence/live-check-1793274849189969500/report.json |
| 原始真实API/DOM证据复核 | PASS：计数/百分比/列表ID同snapshot，真实MISS详情可追到原预测/回执/结果；非当前快照不能当当前数值 | ../../evidence/browser/evidence-recheck.json |
| 新终端启动cmd/访问/退出 | PASS，静态及API均200，精确核实后只停止自建进程；首个清理探针超时另保留 | ../../acceptance/runs/frontend-v0.1-candidate4/startup-smoke.json |
| IAB浏览器实际执行 | 手算13条、7状态、真实零/单点REPLAY、修订、400/503/非法数据/断网/超时/数据库忙/恢复、稳定性、三尺寸/键盘/颜色均有DOM和截图 | ../../evidence/browser；逐项入口见独立验收run.md |
| Windows Edge实机 | BLOCKED：两次URL安全识别中止；当前可控浏览器只有IAB/MCP Apps。未用IAB替代，也未再次索取相同手动操作 | ../../acceptance/runs/frontend-v0.1-candidate4/native-browser-blocker.json |

原版应用HTML/JS/CSS与候选4摘要一致；候选4产品运行代码与候选2/3一致。可复用的旧UI证据限于同摘要组件，候选4另重跑七状态/异常/真实故障/零样本/修订等关键链路；原API/统计/性能独立重跑。

完整20项判定见[独立验收](../../acceptance/runs/frontend-v0.1-candidate4/run.md)：17 PASS、3 BLOCKED。没有正式交付或模型效果通过结论。

## 2026-10-30 原生Edge最终补测

此前BLOCKED为历史时刻；本轮同候选TC005/006/007/008全部PASS：三视口、颜色/键盘/详情、10,000条首屏上界1.229秒、新终端启动cmd、真实同snapshot的API/DOM/原账本副本。20项最终PASS。见[本轮原始记录](../../acceptance/runs/native-edge-20261030/run.md)。

临时session25157/61695停止，按README新session86515保留只读服务；未操作采集器。没有功能改动，不重复已通过且摘要未变的独立回归。
