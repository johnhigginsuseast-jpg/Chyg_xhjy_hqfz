# 行情研究监控网页v0.1本地交付

候选frontend-v0.1-candidate4，[已确认基线](../baselines/v0.1/confirmation.json)、[15项固定摘要](../candidates/frontend-v0.1-candidate4.json)与产品代码不变。[最终20项验收全部PASS](../acceptance/runs/native-edge-20261030/run.md)。

源码、HTML/CSS/JS、只读Python服务及两个cmd在本目录工程；[README](../../README.md)提供启动、停止、模式及故障说明。交付包为本文件同目录frontend-v0.1-candidate4.zip，包后SHA/清单/运行端点另存package-manifest.json和package-check.json，不把压缩成功当运行通过。

将包解压回现有工程“前端设计”，与“系统设计”和“market-direction-ml”相邻，复用既有Python3.12，无新依赖。双击“启动监控网页.cmd”，浏览器打开http://127.0.0.1:8765；新终端已实际验证。关闭控制台或Ctrl+C只停止网页，不停止采集器。此包是既有工程配套目录，不是跨电脑的独立安装器。

演示入口8766始终标DEMO，测试工具只用于隔离验证。包不含runtime、虚拟环境、原生产账本或自身；docs内SQLite是明确带时间的只读证据副本，禁止当作生产库。

16项独立回归、4组补充检查、原生Edge三视口/颜色/键盘/详情通过；API50请求p95=1.270355秒，Edge一万条DEMO首屏上界1.229秒。七类材料入口见[测试总结](../testing/test-summary.md)及[追踪](../testing/traceability-v0.1.md)。旧失败/阻断/DEMO/REPLAY/IAB证据保留原时间与范围。

最终查核源POLL截止2026-10-30 11:04:50，页面正确标过期/未知；31条计分不证明模型有效或盈利。今日真实跨分钟到结算另见[独立观察](../acceptance/runs/observation-20261030T1022/run.md)。未改模型、规则、交易日历、采集或生产账本；原系统资格独立。

未测实体手机、其他电脑、云部署或多仪表盘并发，不作这些资格承诺。一次性9:30自动化9已删除，仅保留8765只读网页供查看。

交付状态：S5完成。归档全部文件与安装目录一致、CRC通过，包后HTML/JS/CSS/API均200；详见同目录package-manifest.json和package-check.json（这两个包后记录随ZIP单独提供）。
