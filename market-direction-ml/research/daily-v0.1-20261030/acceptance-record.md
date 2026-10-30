# 日线v0.1研究执行记录

依据两份用户指定v0.1基线；本记录是研究核对，不是正式模型交付验收。

| 用户验收项 | 实测与结论 | 证据 |
|---|---|---|
| 1 数据审计与保护 | 已执行；150根、4差异日期保留原值；两份外部基线副本同SHA | source-audit.json、baseline-verification.json、preservation.json |
| 2 时序、热身、标签与冻结 | 已执行；原105/22/23；64热身；逐h原价索引与目标边界一致，截断/扰动前缀不变，冻结先于测试指标 | config.json、fit-indices.json、frozen.json、test-unlocked.json |
| 3 h1尝试及其他h可行性 | 已执行；h1拟合入口被38<80拒绝，五折不足；h3/5/10为37/36/31，也不足 | logistic-attempt.json、walk-forward.json、readiness.json |
| 4 成功训练时的模型与结果 | MODEL_NOT_TRAINED；没有LR模型或LR准确率。四个规则基线的各集合分母、类别、混淆和全覆盖预测单独核对通过 | result.json、metrics.json、label-distribution.json、predictions.csv |
| 5 留痕、回归与资格边界 | 已执行；原26回归通过、5317既有文件同SHA；不声称新盲测、概率可靠、收益、实时或正式交付 | legacy-regression.txt、preservation.json、independent-verification.json、decisions.md |

模型状态：INSUFFICIENT_DATA。研究核对完成不表示模型效果通过。所有run文件在run-01/，首轮命令stdout/stderr在execution.txt，独立核对输出在verification.txt。
