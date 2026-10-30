# 日线小样本研究 v0.2

本次已训练h=1逻辑回归；结论：**未得到可靠预测信号**。

- [完整研究报告](runs/daily-h1-short4-20261030-01/report.md)
- [数据审计](runs/daily-h1-short4-20261030-01/data-audit.md)
- [新旧差异](baseline/change-request-v0.2.md)、[需求](baseline/requirements-v0.2.md)、[验收标准](baseline/acceptance-v0.2.md)
- [模型](runs/daily-h1-short4-20261030-01/model.joblib)、[逐根预测](runs/daily-h1-short4-20261030-01/predictions.csv)、[决策](decisions.md)
- [独立复算](runs/daily-h1-short4-20261030-01/independent-verification.json)、[验收记录](acceptance-record.md)

原始数据与旧实验原样保留。本目录中的旧v0.1需求/验收副本可核查，正式旧实验仍在../daily-v0.1-20261030。历史测试此前已暴露，不是全新盲测；原始概率未校准。

在项目根目录PowerShell中，只审查既有结果：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 research\daily-v0.2-20261030\verify.py research\daily-v0.2-20261030\runs\daily-h1-short4-20261030-01
```

不要重复计分或覆盖已有run-id。需重新运行时必须新建run-id并登记目的；相同数据仅可称复现，不能创造新的独立测试证据。命令模板（替换为明确的新run-id）：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 research\daily-v0.2-20261030\test_daily.py
.\.venv\Scripts\python.exe -B -X utf8 research\daily-v0.2-20261030\run.py --run-id NEW_UNIQUE_RUN_ID
```

model.joblib是可信本地研究包，包含estimator及f_前缀列顺序。需先使用run.features在按原规则确认完整的同源日线上计算特征；缺特征时不预测，不填值。不是通用实时接口，也未接入原系统旧模型加载路径。
