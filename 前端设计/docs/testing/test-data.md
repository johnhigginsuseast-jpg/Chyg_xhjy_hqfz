# 测试数据 v0.1

| 数据编号 | 来源/生成 | 含义与边界 |
|---|---|---|
| TD-WEB-001 | tests/test_dashboard.py的fixture及midnight用例；tools/hand_case.py；验收revision_probe.py | 原Ledger只在前端临时库构造13条6HIT/4MISS/1FLAT/1PENDING/1UNSCORABLE；wait含于主分母；午夜、无回执、外部署、版本修订单独检查。原生产库从不注入 |
| TD-WEB-002 | demo.py seed；tools/ui_fixture.py，前端runtime/ui-qa-* | 显著DEMO的120条与7类状态，合成价量；冻结时钟只作测试。10轮状态更新及新增1条也仅写这类库，不计真实效果 |
| TD-WEB-003 | seed(count=10000)，标准库HTTP测试50请求 | 10,000预测、600 bars、至多50趋势点、100 API记录行。页面默认50行。全50次耗时保留；不是训练/回测/真实前向样本 |
| TD-WEB-004 | 固定系统设计/runtime/http-research/forward.sqlite3，以mode=ro打开；前端docs/evidence/live-check-*保存只读backup | 真实当前部署、原预测和结算；原Ledger只在证据副本上比较as_of。当前账本持续变化，每轮结果必须带cutoff，不把自然写入当作前端写入 |
| TD-WEB-005 | tools/zero_replay.py及验收one_point_probe.py | 从原账本选择真实历史POLL，冻结只读观察时钟，展示模式强制标REPLAY；数据/原口径不改，非当前LIVE。0预测和1个统计点各与原summary同cutoff比较 |
| TD-WEB-006 | 验收live_fault_probe.py、前端runtime/live-fault.json | 正常时读取真实只读Reader；受控失败只返回503，不修改原库。首次失败无数据，有缓存时保留LIVE；不生成演示行情 |

[历史回放同截面对照](../acceptance/runs/frontend-v0.1-candidate4/historical-replay-check.json)、[修订原始数据](../acceptance/runs/frontend-v0.1-candidate4/revision-check.json)和[真实联调报告](../evidence/live-check-1793274849189969500/report.json)分别留存，不能合并统计或互作效果证据。
