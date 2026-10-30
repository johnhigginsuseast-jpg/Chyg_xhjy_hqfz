# 2026-10-30 实机续验执行

工作目录D:\mycode\沧海易购1\系统设计，Asia/Shanghai，原market-direction-ml/.venv解释器，参数-B -X utf8。本轮冻结candidate4，不改产品/模型/原测试。

| 实际执行 | 结果/证据 |
|---|---|
| git rev-parse HEAD / git status --short | exit1，非仓库；不虚构Hash，使用既有清单/zip |
| Get-Process原PID14144及日志/最后POLL核验 | 进程缺失，最后01:49；已停止才恢复，未因超时重启 |
| 固定22/原15文件摘要及配置核验、一致性备份 | PASS，preflight.json，旧备份保留 |
| 原冻结入口Hidden恢复，Python自身日志 | 10:19 PID20752，后续实际路径/启动时间与新POLL匹配 |
| python tools/audit_forward.py --output docs/acceptance/runs/http-v0.4-candidate4/observation-20261030T1025 | exit0，3条模型/输入/目标一致，first-forward-audit.log |
| python tools/audit_continuity.py --output docs/acceptance/runs/http-v0.4-candidate4/continuity-20261030T1025 | exit0，连续3、无有效根漏发/已完成价格修订，60=false |
| python docs/evidence/20261030-live/check-live-minutes.py | exit0，三个连续形成中→完成，源时钟最大0.916秒，live-minute-check.log |
| 只读发布链/旧备份五表逐行集合比较 | PASS，publication-chain.json，旧行缺失0 |
| 限定schtasks /Query /TN Codex-Market-Resume-20261030-0928 /FO LIST /V | exit0，09:28:00触发、Last Result1，task-query-actual.txt；CLI写入锁失败原文保留 |
| 四项模拟API退出/失败/过期测试+stop提前退出 | PASS，awake-proposal-tests.log和awake-early-stop-test.log；不计真实行情 |
| 用户本次批准后临时防休眠 | 10:24真实ACTIVE，实际调用PID14488；真实清除待验，不由模拟测试替代 |

原45回归/7独立/3补测为同一固定candidate4已通过证据，本轮只补真实链路，不因未改代码重复全部旧测试。当前13 PASS/2 NOT_TESTED，真实连续60、最终延迟及全部到期复算尚欠。七类资料中的原计划/用例/数据定义不变，补充原始数据由本轮验收报告引用。
