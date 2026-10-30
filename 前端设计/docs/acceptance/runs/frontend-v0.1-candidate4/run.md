# 前端v0.1候选4独立验收记录

结论：**BLOCKED，未通过，不予正式交付**。20项中17 PASS、3 BLOCKED（017、018、020）。本轮为固定候选的独立核验尝试，不表示S3出口或S5已通过。

需求/标准：用户确认的v0.1，确认原话及原始摘要见[confirmation](../../../baselines/v0.1/confirmation.json)。[固定候选](../../../candidates/frontend-v0.1-candidate4.json)的15个代码/QA文件摘要复核一致。产品运行代码与候选2/3完全相同；候选4只补QA工具，不修改现有系统。

## 实际环境与范围

- Windows、既有Python3.12.14；标准库测试16项，50.356秒全部PASS。独立补充4组检查全部PASS。
- 图形界面记录来自ChatGPT内置浏览器IAB，不能当Windows原生Edge/Chrome证据。三尺寸为CSS视口测试，不声称实体手机测试或完整WCAG认证。
- API基准：10,000预测/600 bars/50趋势点上限/100行、连续50次请求，p95=1.270355秒。IAB首屏1.772秒；指定浏览器首屏NOT_TESTED，故018整体BLOCKED。
- 真实当前账本对账截面：2026-10-29 19:54:01.537 Asia/Shanghai（POLL13629），65计分、42命中、23未命中、1待结算、2无法计分。动态账本后续会变化，本记录不是当前报价或效果结论。
- 真实零预测/单统计点只读历史回放分别取原POLL1298/4218对应截止，实际POLL ID以JSON为准；显式REPLAY，不冒充当前LIVE。原Ledger仅在前端证据副本实例化，并在各自as_of复核。
- DEMO手算、异常、数据库忙、修订和稳定性数据只写前端runtime。现有采集器、模型、规则和生产账本未被本前端修改。

## 逐项结果

PASS的浏览器功能观察范围限IAB。原生浏览器资格在017统一保留，原生首屏在018单独保留；不会因其余项PASS宣布全平台或整体通过。

| 标准 | 结果 | 实测与范围 | 原始证据（相对本目录） |
|---|---|---|---|
| AC-WEB-001 | PASS | 启动cmd新进程、HTML/JS/CSS/API均200；独占端口冲突报错。网络清单仅本地资源和浏览器内置data图标。 | startup-smoke.json; ../../../evidence/development/launcher-conflict.json; ../../../evidence/browser/local-network-inventory.json |
| AC-WEB-002 | PASS | 固定URI mode=ro、query_only实际写入拒绝；方法/路径/SQL/Host/Origin负例通过。原受保护源码/配置和15个模型文件无摘要变化。 | regression.log; supplementary.log; ../../../evidence/live-check-1793274849189969500/report.json |
| AC-WEB-003 | PASS | 真实531/品名/HTTP跨源研究/模型/部署已对照；错误部署、错误LIVE模型绑定被拒绝。 | regression.log; supplementary.log; ../../../evidence/browser/live-api-dom.json |
| AC-WEB-004 | PASS | 7类浏览器矩阵及9类状态边界接口检查；进程始终未知，STOPPED仅作历史记录，未知码保持原码。 | regression.log; ../../../evidence/browser/scenario-matrix-final.json |
| AC-WEB-005 | PASS | 上海时间、源时间/获取/业务截止/页面成功刷新分列；真实旧截面明确REPLAY，过期缓存不推进成功时间。 | regression.log; historical-replay-check.json; ../../../evidence/browser/offline-final.json |
| AC-WEB-006 | PASS | 600根真实OHLCV逐字段相等；240默认/600上限、隔离/形成中/空图、原始单位和无填补已检查。 | regression.log; supplementary.log; ../../../evidence/live-check-1793274849189969500/report.json; ../../../evidence/browser/hand-counts-dom.json |
| AC-WEB-007 | PASS | up/down、0.5/wait、skip、pending、late/旧预测与目标未知已核对；当前和历史标签明确。 | regression.log; ../../../evidence/browser/scenario-matrix-final.json; ../../../evidence/browser/live-detail-api-dom.json |
| AC-WEB-008 | PASS | 手算13条的页面n=10、6/4/1/1/1、60.00%；wait在主分母；原Ledger统计/Wilson完全一致。 | regression.log; ../../../evidence/browser/hand-counts-dom.json; ../../../evidence/browser/hand-counts-page.jpg |
| AC-WEB-009 | PASS | 原账本真实0预测截面以REPLAY单独显示，无假0%；午夜、无回执和跨日结算与原summary相等。 | regression.log; historical-replay-check.json; ../../../evidence/browser/real-zero-replay-dom.json; ../../../evidence/browser/real-zero-replay.jpg |
| AC-WEB-010 | PASS | 真实历史0/1点不画趋势，当前多点有线；6/10修订7/10，过去统计点未回填；原summary逐点对齐。 | regression.log; revision-check.json; historical-replay-check.json; ../../../evidence/browser/revision-before.jpg; ../../../evidence/browser/revision-after.jpg; ../../../evidence/browser/real-one-point-replay-dom.json |
| AC-WEB-011 | PASS | 120条完整分页ID无漏重，同发布时间稳定排序；日期+状态组合与独立期望相等，筛选不改全局统计。 | regression.log; supplementary.log; ../../../evidence/browser/filter-pagination.json |
| AC-WEB-012 | PASS | 真实已计分明细追到原预测/回执/结算；无MODEL_INPUT显示未记录，修订2可见，其他部署ID拒绝404。 | regression.log; ../../../evidence/browser/evidence-recheck.json; ../../../evidence/browser/missing-trace-detail.json; ../../../evidence/browser/revision-after-dom.json |
| AC-WEB-013 | PASS | DEMO显著标记且独立写前端runtime；真实数据故障注入时LIVE缓存保留、首次失败无假数据、恢复不转DEMO。 | regression.log; ../../../evidence/browser/scenario-matrix-final.json; ../../../evidence/browser/live-failure-no-demo-final.json; ../../../evidence/browser/live-failure-no-demo.json |
| AC-WEB-014 | PASS | 400/503、非法JSON/缺字段、实际断网/5秒超时/数据库忙与恢复均留证；旧响应反例未覆盖新请求。 | regression.log; ../../../evidence/browser/api-400-dom.json; ../../../evidence/browser/failure-recovery-final.json; ../../../evidence/browser/offline-final.json; ../../../evidence/browser/offline-recovered-final.json; ../../../evidence/browser/database-busy.json; ../../../evidence/browser/database-recovered.json; ../../../evidence/browser/timeout-after-fix.json; ../../../evidence/browser/response-order.json |
| AC-WEB-015 | PASS | 未完成POLL前13条、完成后14条；诊断STOPPED可晚于业务截止。真实原汇总/趋势/600 bars/DOM/明细均对齐。 | supplementary.log; ../../../evidence/browser/evidence-recheck.json; ../../../evidence/live-check-1793274849189969500/report.json |
| AC-WEB-016 | PASS | 十轮独立新状态、11种快照、26次响应；图表/悬停/筛选/第二页/详情/焦点保持，锚点偏移0px、请求重叠0、loaderId仅1。 | ../../../evidence/browser/ten-updates-stability-final.json; ../../../evidence/browser/evidence-recheck.json; ../../../evidence/browser/keyboard-escape.json |
| AC-WEB-017 | BLOCKED | IAB三尺寸无页面水平溢出，图高340px；抽测正文/控件文字最低8.02、控件边框3.19，键盘/Esc通过。但基线指定的Windows Edge/Chrome实机项未完成。 | ../../../evidence/browser/final-layouts.json; ../../../evidence/browser/contrast-fixed-ratios.json; native-browser-blocker.json |
| AC-WEB-018 | BLOCKED | 50次API p95=1.270355s通过；IAB一万条首屏1.772s通过。指定Windows Edge/Chrome的首屏性能未测，不能将IAB值改标为Edge值。 | ../../../evidence/development/performance-1793274651556964400.json; ../../../evidence/browser/first-usable-10000.json; native-browser-blocker.json |
| AC-WEB-019 | PASS | 真实当前部署只读联调成立：本次65计分、42HIT/23MISS；当前结果追踪到原始行/回执；另一次DOM54计分截面也逐字段一致。仅为对应时刻证据。 | ../../../evidence/live-check-1793274849189969500/report.json; ../../../evidence/browser/evidence-recheck.json; ../../../evidence/browser/final-live-detail.jpg |
| AC-WEB-020 | BLOCKED | 同候选摘要、启动脚本、README、七类测试材料和本独立记录已齐备；017/018门禁未过，因此不打正式交付包，不宣布S5。 | ../../../candidates/frontend-v0.1-candidate4.json; startup-smoke.json; run.json |

原始路径也见机器可读[run.json](run.json)。证据文件中的PASS限所述时刻、模式和范围，不混合DEMO/REPLAY/LIVE成绩。

## 失败保留与修复复核

候选1性能p95=2.693899秒未通过，日志仍保留；更早2.7326365秒首败也保留。候选2增加按完整原文区分、有上限的解析缓存，不缓存业务计分；修改原文/返回值污染保护和版本修订均复测通过。Windows端口共享问题通过LocalServer独占绑定修复，第二实例拒绝且首服务仍200。

首个启动探针在等待cmd退出时超时，保留[startup-harness-first-failure](startup-harness-first-failure.txt)。随后核对实际端点、脚本摘要和精确启动时间，只停止本探针的服务/cmd；后检3个自建进程和监听均消失，见[startup-smoke](startup-smoke.json)。没有通过结束其他程序解决端口冲突。

[缺陷账本](../../../testing/defects.md)列出001至017产品缺陷关闭证据；浏览器URL识别为ENV-WEB-001，不伪装成产品修复。原工程2份.md变化单列，受保护源码/配置和15个原模型文件摘要无差异。

## 未过门禁与后续

[原生浏览器阻断](native-browser-blocker.json)：用户已打开localhost并显示地址栏，Windows Computer Use仍无法可靠识别Edge URL而中止；可控浏览器清单仅IAB/MCP Apps。未绕过安全限制。需要控制面能可靠识别本地地址后，再在已确认Edge/Chrome环境补测017和018；之后核对候选摘要与020。不能用说明、用户点赞或IAB截图代替该必需门槛。

原模型效果与原采集系统资格继续独立。本前端不提高或追认其预测效果，不保证盈利。


有效最终图像见[桌面完整截图](../../../evidence/browser/final-rendered-full.jpg)、[390视口](../../../evidence/browser/final-rendered-390.jpg)、[360视口](../../../evidence/browser/final-rendered-360.jpg)。均经实际图像查看，不代表Edge/Chrome。[截图工具首败与复核](capture-review.json)单列，不用拼接失败图片支持通过结论。
