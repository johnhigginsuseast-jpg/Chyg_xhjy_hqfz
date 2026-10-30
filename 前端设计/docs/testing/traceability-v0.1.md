# 需求追踪矩阵 v0.1（候选4）

对应[需求](../requirements/dashboard-v0.1.md)与[标准](../acceptance/dashboard-criteria-v0.1.md)，已由用户确认。结果见候选4独立验收；原生Edge补测完成，20项全部PASS。

| 需求 | 独立验收AC-WEB编号 | 实际实现位置 |
|---|---|---|
| FR-WEB-001 | 003、013 | data.py身份绑定、web/app.js研究标记 |
| FR-WEB-002 | 004 | data.py状态映射、web/app.js状态区 |
| FR-WEB-003 | 005、019 | data.py时标、web/app.js时间与过期 |
| FR-WEB-004 | 006、019 | data.py行情投影、web/app.js图表 |
| FR-WEB-005 | 007、019 | data.py已有预测投影、web/app.js预测区 |
| FR-WEB-006 | 008、009、015、019 | data.py原口径查询、web/app.js格式化 |
| FR-WEB-007 | 010 | data.py历史时点统计、web/app.js趋势 |
| FR-WEB-008 | 011、015、019 | data.py有界过滤、web/app.js记录 |
| FR-WEB-009 | 012、015 | data.py详情投影、web/app.js详情 |
| FR-WEB-010 | 013、014 | server.py显式DEMO、web/app.js连接恢复 |
| FR-WEB-011 | 014、016 | web/app.js请求与视图状态 |
| NFR-WEB-001 | 002、013 | server.py固定只读边界、测试 |
| NFR-WEB-002 | 008、010、015 | data.py事务/截止/一致性、测试 |
| NFR-WEB-003 | 017 | web/index.html、web/styles.css、交互 |
| NFR-WEB-004 | 001、005、018 | server.py、启动脚本、web/app.js |
| NFR-WEB-005 | 016、018 | web/app.js、服务查询与基准 |
| NFR-WEB-006 | 003、019、020 | 身份声明、证据/README/交付文档 |

共11项FR和6项NFR，全部映射到独立验收；AC为001至020。没有预造功能通过结果。


## 用例、数据与真实结论

| 需求范围 | 用例/数据 | 执行与验收 |
|---|---|---|
| FR001至003，NFR001/006 | TC001/003/007，TD001/002/004/005 | 身份、未知进程、状态/时标、只读与真实对账通过；017/018/020补测通过 |
| FR004/005/009 | TC003/007，TD001/002/004 | 真实OHLCV、预测语义、已有字段/无MODEL_INPUT/修订详情通过 |
| FR006/007/008，NFR002 | TC002/003/007，TD001/004/005 | 原口径全字段、午夜/回执/趋势修订、完整120条分页、同snapshot API/DOM通过 |
| FR010/011，NFR005 | TC004/005/006，TD002/003/006 | 演示隔离、真实故障不回退、异常恢复、十轮稳定与API性能通过；Edge首屏上界1.229秒通过 |
| NFR003/004/006 | TC005/006/008，TD003/004 | 启动与接口通过；IAB布局/颜色/键盘/首屏通过；Windows Edge资格及最终交付门禁通过 |

[执行记录](executions/development-v0.1.md)链接实际日志；[独立20项记录](../acceptance/runs/native-edge-20261030/run.md)给出逐项实测、模式和范围。20项必需验收全部PASS；原模型效果与原系统资格独立。
