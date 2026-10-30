# 独立验收：HTTP v0.4 candidate1

基线：已确认v0.1与CR-RT-003；候选[清单](../../../candidates/http-v0.4-candidate1.json)和zip保留。2026-10-28，本机Windows/原Python环境，Codex执行，生产代码在验收用例执行前保持冻结。

独立方式：除直接查询LIVE一致性快照，新增独立REPLAY用例，使用真实冻结模型内核、合成行情与手算期望；数据和结果不写入LIVE。快照算术无差异，但0预测，不能证明真实前向链路。

| 验收项 | 实际观察 | 结果 |
|---|---|---|
| AC-RT-006 | 源修订使原锚点变为跳过后，已发预测一直PENDING | FAIL |
| AC-RT-008 | 查询早于真实发布时间的证据时点，尚未发布的行被统计为迟到/UNSCORABLE | FAIL |
| AC-RT-001至015其余项 | 发现必需缺陷后停止本轮，不将开发绿灯或0分母查询追认为完整验收 | NOT_TESTED |

首败：[candidate1-independent-cases.log](../../../evidence/20261028-preflight/candidate1-independent-cases.log)。LIVE快照及报告：`observation-20261028T2243/`，其中0真实预测，算术无差异仅适用于零样本。BUG-RT-006/007另行修复并建立candidate2，本候选原文件、失败及原部署均保留。

结论：**FAILED / 不予正式交付**。没有人工评价或用户签字被代填。
