# 执行记录 TE-D02

实际UTC时间见runs/daily-h1-short4-20261030-01/execution.log及各JSON；本地任务日期2026-10-30，原生行情时间未擅自认定时区。Python及依赖见environment.json。

1. `python -B -X utf8 test_daily.py`：训练前9/9，训练后9/9，exit 0；TC-D01..D09。
2. `python -B -X utf8 -m unittest discover -s tests -v`：训练前后均26/26，exit 0；TC-D12。
3. `python -B -X utf8 run.py --run-id daily-h1-short4-20261030-01`：exit 0；审计→预注册→两候选两折→最终拟合→冻结→一次历史计分→保全。执行路径均以项目根起始，实际日志位于run-id目录。
4. `python -B -X utf8 verify.py runs/daily-h1-short4-20261030-01/`：exit 0，12组指标/模型重载/配置数据代码模型哈希/5355文件保全通过；TC-D10..D12，无重拟合。

弃用和人工异常夹具解析/单类指标警告均保留在原日志中，未改变预测或准入门槛。研究优势FAIL来自真实比较，不是程序崩溃。
