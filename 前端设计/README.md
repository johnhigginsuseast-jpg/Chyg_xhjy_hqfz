# 行情预测监控网页 v0.1

中文深色只读仪表盘：系统/行情状态、分钟K线与量、下一有效根预测、累计/今日统计和预测记录。现有模型、采集器和账本保持独立。候选4已完成Windows Edge补测，全部20项必需验收PASS；不代表采集器存活或模型效果通过。

## 本地启动

1. 双击 [启动监控网页.cmd](启动监控网页.cmd)。保留控制台窗口。
2. 浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。此服务只读当前HTTP跨源研究账本，不启动采集。
3. 关闭该控制台或Ctrl+C停止网页服务；不会停止原采集器。端口占用只报错，不关闭其他进程。

命令行（在本目录）：

```powershell
& '..\market-direction-ml\.venv\Scripts\python.exe' -B -X utf8 server.py --mode live --port 8765
```

依赖既有Python3.12，无需安装npm/框架或新Python包。仅本机回环地址，不支持公网或局域网发布。浏览器不直接访问数据库，静态服务没有文件浏览能力。

## 演示与真实数据

双击 [查看演示网页.cmd](查看演示网页.cmd)，访问 [演示页面](http://127.0.0.1:8766)。全页标明“演示数据”，独立数据仅写在本目录runtime；不会写真实库。演示为固定样本，随时间会标记轮询过期，不假装持续接入真实行情。

LIVE是账本数据模式，不是新鲜度保证。页面连接成功、采集进程存活、行情更新是不同问题；无可靠进程证据就显示未知。旧轮询仅显示上次状态，不能推定仍在运行。网页不启动、停止或重启采集器。

API错误时保留有时间标记的旧快照，超过10秒明确标过期；不自动切到演示。首次失败没有可用数据时不显示虚构计数。

## 查看与统计

- 时间统一Asia/Shanghai。源K线开始/结束标签、该版本获取时间、最近成功获取及页面刷新分开显示。最后源K线可能尚未确认完整；隔离的边界事件不画成分钟，不补休市数据。
- 图中保留源分钟记录，模型有效根另按原规则；h=1是下一有效根，不保证下一自然分钟。规则跳过没有概率；低置信度等待仍保留原方向。
- 主命中率、今日、状态数量和Wilson区间来自只读服务的原账本口径；前端只格式化，0分母显示“暂无可计分样本”。少于500计分样本仍提示效果样本不足；不代表模型有稳定优势。
- 日期/结算状态只筛选记录，累计与今日口径不变。详情只展示已有回执、价格、规则状态、版本与摘要，不生成模型理由。实际方向由已记录目标收盘与基准收盘比较得到。
- 图表较早/较新、显示根数和“最新”控制查看范围。查看历史时刷新不自动回到最新；有新预测时提示手动返回。

## 测试与证据

```powershell
& '..\market-direction-ml\.venv\Scripts\python.exe' -B -X utf8 -m unittest discover -s tests -v
& '..\market-direction-ml\.venv\Scripts\python.exe' -B -X utf8 tools/verify_live.py
```

第二条需要真实网页服务已启动，生成前端目录内的证据副本后与原Ledger比较，绝不在真实库上调用有写入的Ledger构造。tools/ui_fixture.py只用于独立DEMO浏览器故障测试，不是采集器或生产入口。

[项目状态](docs/project-status.md) · [已确认需求](docs/requirements/dashboard-v0.1.md) · [独立验收标准](docs/acceptance/dashboard-criteria-v0.1.md) · [确认记录](docs/baselines/v0.1/confirmation.json)

[测试计划](docs/testing/test-plan.md) · [用例](docs/testing/test-cases.md) · [数据](docs/testing/test-data.md) · [缺陷](docs/testing/defects.md) · [执行](docs/testing/executions/development-v0.1.md) · [追踪](docs/testing/traceability-v0.1.md) · [总结](docs/testing/test-summary.md) · [AI修改记录](AI_CHANGELOG.md)

当前自动检查与真实联调证据位于docs/evidence，浏览器实际结果和未测项另列。演示测试通过不替代真实联调，前端通过也不替代原预测系统和模型效果验收。


## 当前验收入口与边界

[候选4逐项验收](docs/acceptance/runs/native-edge-20261030/run.md) · [固定摘要](docs/candidates/frontend-v0.1-candidate4.json) · [测试总结](docs/testing/test-summary.md)。

16项独立回归、4组补充检查及原生Edge布局/键盘/颜色通过；API p95=1.270355秒，Edge一万条DEMO首屏上界1.229秒。20项全部PASS，旧失败/BLOCKED/IAB记录不覆盖或改标。

真实历史0预测和单统计点的截图是显式REPLAY回放，手算/状态/异常测试是DEMO；都不是当前LIVE行情。所有数字和截图有截止时刻，不能将旧截面当作当前成绩。

tools下的UI/手算/历史回放工具以及验收目录中的故障探针仅用于本地测试，不是正式启动入口。正常查看只用上方两个cmd。网页进程与原采集器独立：即使网页关闭，原系统状态仍须独立确认。

启动cmd为手动控制台入口；看到“无法启动：本地端口不可用”时按该错误处理，不关闭其他程序来抢占端口。无需安装任何新依赖。没有新增下单、登录、资金、训练或云发布功能。

[最终交付清单](docs/delivery/frontend-v0.1.md)。交付包须解压回“前端设计”，与已有系统和Python工程相邻；不是独立采集程序。
