# 独立验收记录 v0.2

执行者：本地AI自动检查；候选代码/需求/数据快照见preregistered.json，结果复算入口为verify.py，不重新拟合。未聘用第二个人工审查员。

| 项 | 结果 | 证据（位于runs/daily-h1-short4-20261030-01/） |
|---|---|---|
| DAC-01 | PASS | source-audit.json, preservation.json |
| DAC-02 | PASS | preflight-tests.txt, postflight-tests.txt, config.json |
| DAC-03 | PASS | sample-counts.json, fit-indices.json, final-fit.json |
| DAC-04 | PASS | selection.json, config.json, independent-verification.json |
| DAC-05 | PASS | holdout-metrics.json, walk-forward.json, independent-verification.json |
| DAC-06 | PASS | bar-ledger.csv, predictions.csv, cv-predictions.csv, independent-verification.json |
| DAC-07 | PASS | preregistered.json, frozen.json, holdout-unlocked.json, independent-verification.json |
| DAC-08 | PASS | postflight-tests.txt, legacy-regression.txt, independent-verification.json |

程序/记录要求8项通过；研究信号资格FAIL，不具备稳定预测、正式交易或实时交付资格。未核实元数据和NOT_TESTED前向/实时/实盘/校准不得按已验证处理。原始测试后模型与已登记标准未改动。
