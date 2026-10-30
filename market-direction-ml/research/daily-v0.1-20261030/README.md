# 日线v0.1隔离研究

先读[结果](report.md)和[逐项记录](acceptance-record.md)。模型因38<80未拟合，现有目录只包含研究证据。

实际运行命令（工作目录为market-direction-ml）：

```powershell
& .\.venv\Scripts\python.exe -B -X utf8 research\daily-v0.1-20261030\run.py
& .\.venv\Scripts\python.exe -B -X utf8 research\daily-v0.1-20261030\verify.py
```

run.py拒绝覆盖已存在的run-01；历史实验不可重置成未暴露测试。verify.py可再次独立核对原结果。新增真实日线或变更门槛须另建研究版本并保留此记录，不能修改这次已冻结结果。
