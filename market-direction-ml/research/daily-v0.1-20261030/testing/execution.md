# 测试执行记录

2026-10-30，Windows/Python项目虚拟环境；命令见README。run.py exit0表示按方案记录了INSUFFICIENT_DATA，不是LR拟合成功。

DTC-01至03：源/聚合差异、原价索引、全部边界、特征前缀截断/未来扰动断言通过；DTC-04：真实原fit_model入口拒绝38<80，5折与其他h不足，未创建joblib；DTC-05：verify.py exit0，344预测/12指标组独立原价/混淆/准确率核对通过；DTC-06：原26测试回归及5317原文件同SHA通过。

机器证据在run-01，原始stdout/stderr在execution.txt、verification.txt。源时间/身份资格未核实，历史测试非新盲测。
