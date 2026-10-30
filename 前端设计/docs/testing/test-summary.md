# 测试总结 v0.1候选4

**最终20 PASS、0 FAIL、0 BLOCKED、0 NOT_TESTED。** 用户确认范围、阈值及候选运行代码不变。

16项独立回归（50.356秒）及4组补充检查PASS。API一万条预测/600根/50趋势点上限/100 API行、50请求p95=1.270355秒。Windows Edge一万条DEMO首屏墙钟上界1.229秒；页面50行。

Edge 1440×900、390×844、360×800无页面横溢，表格内部横滚、图高340px；抽测文字最低8.0245、控件边框3.18865。键盘筛选/翻页/详情/Esc焦点返回PASS。

既有正常/零样本/休市/断线/恢复/滞后/接口错误/超时/数据库忙/乱序响应/十轮稳定证据保留原模式和范围。今日真实预测PENDING到下一有效根MISS单列；本轮原生页面/API/原Ledger副本同cutoff的31计分、600根、31趋势点相等。新终端启动cmd及四类资源均200，候选15项和原模型15项摘要一致。

当前源POLL截止11:04:50，页面已标旧；进程未知，不宣称当前采集存活或模型有效。实体手机、其他电脑、云发布和多仪表盘并发未测，均非本版资格。

[最终独立验收](../acceptance/runs/native-edge-20261030/run.md) · [历史阻断尝试](../acceptance/runs/frontend-v0.1-candidate4/run.md) · [执行](executions/development-v0.1.md) · [追踪](traceability-v0.1.md) · [缺陷](defects.md) · [交付](../delivery/frontend-v0.1.md)。
