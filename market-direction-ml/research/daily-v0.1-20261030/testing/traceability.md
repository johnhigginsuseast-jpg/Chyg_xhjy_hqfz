# 需求追踪

| 用户验收项 | 产物/检查 |
|---|---|
| 1 源数据/差异保护 | source-audit.json、legacy-before.json、preservation.json；DTC-01/06 |
| 2 时序/热身/冻结 | config.json、fit-indices.json、frozen.json、test-unlocked.json；DTC-02/03 |
| 3 h1尝试/其他h不足 | logistic-attempt.json、readiness.json、walk-forward.json；DTC-04 |
| 4 成功则模型/指标；不足不捏造 | result.json、predictions.csv、model-comparison.csv；DTC-05；LR未拟合不得写其准确率 |
| 5 命令/决策/证据/回归/非正式交付 | execution.txt、decisions.md、legacy-regression.txt；DTC-06 |

所有run产物均在run-01/，最终状态按实际执行记录。
