# 开发检查执行记录（增量）

日期：2026-10-28，Asia/Shanghai；基线v1.0；无Git，阶段证据与最终源码清单固定候选。

| 执行 | 命令/数据 | 实测 | 原始输出 |
|---|---|---|---|
| E-001 | test_data.py，TD-002三格式及错误边界 | 6个通过，exit0 | reports/evidence/stage1/unit-tests.txt |
| E-002 | src.data_audit，TD-001全部真实CSV | exit0，研究审计门禁通过 | stage1/audit-command.txt、audit.json |
| E-003 | 独立原行映射/时间/量守恒/8源哈希 | 全通过，exit0 | stage1/independent-checks.json |
| E-004 | 当轮全部unittest，TD-002 | 13个通过，exit0 | stage2/unit-tests-initial.txt |
| E-005 | TD-001每周期两个训练/验证前缀重算 | 16次真实前缀检查通过 | stage2/real-prefix-checks.json |
| E-006 | 四个实际模型类的合成拟合/内层早停及指标/阈值 | 3个通过，exit0；不是行情预测效果 | stage3/model-tests.txt |
| E-007 | 合成模型保存、新进程CLI重载、未完成/错来源/校验失败及块统计 | 2个通过，exit0 | stage3/delivery-tests-initial.txt |

E-007初次绘图导入尝试默认缓存目录被环境拒绝，库回退临时目录，测试通过；随后将缓存明确限制工程reports/.mplcache，最终候选回归还需验证该修改。没有绕过权限或升级权限。

后续：两次完整训练exit0、112模型验证概率最大差0（reproducibility.json）；首轮最终留出唯一解锁exit0，413,136预测。独立复核初次FAIL为BUG-001，保留independent-verification-initial.txt；修复脚本首次Windows路径键失败保留probability-export-repair-initial.txt，修正后240导出不改模型/方向/信号，独立复测PASS。960模拟场景和128详细账目复核PASS。BUG-002保留原图后重绘60图，2共享版式视觉复查及全部PNG完整性通过。正式独立验收另开记录，不把本开发记录复制为验收通过。
