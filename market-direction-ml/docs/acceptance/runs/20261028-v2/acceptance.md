# 验收报告：v1.0 离线研究工程

候选：v1.0-research-20261028-v2；需求/验收基线v1.0按用户委托推荐选择采用。
**工程验收PASS；当前数据未验证出稳定可用的预测信号。**

26个自动化测试、240组合/413136预测的原价标签/指标、960回测场景/128详细账目、112模型复现均有独立执行证据。便携包解压后26测试、全量数据审计、新进程预测通过；另以60min h=1运行8模型训练→冻结评估→4费用模拟→独立重算完整链路。该缩小用例仅验证便携集成，不替代主实验8周期×4跨度。

| AC | 工程结论 | 实测范围 | 证据入口 |
|---|---|---|---|
| AC-001 | PASS | 8源SHA不变，原行与派生/快照隔离 | stage1/independent-checks.json; source-manifest.json |
| AC-002 | PASS | Windows独立虚拟环境/锁版本/完整流程及便携包实际运行 | dependencies.txt; docs/delivery/portable-integration-smoke.json |
| AC-003 | PASS | CSV/Excel(.xlsx)/Parquet等价与缺列/非法输入拒绝 | unit-tests.txt: test_data |
| AC-004 | PASS | 全量97135行结构/周期/时间/单位状态审计 | reports/data_audit.md; stage1/audit.json |
| AC-005 | PASS | 事件/短桶/日线时间、无填充；周日/周六夜盘拒绝，BUG-003修复 | unit-tests.txt; calendar-validation-repair.json; canonical equality |
| AC-006 | PASS | 未认证品种/代码/时区/单位显式标记，不混其他源 | audit.json; docs/decisions.md |
| AC-007 | PASS | 三连跳两根/平盘/六连/状态重放 | unit-tests.txt; independent-verification.json reference replay |
| AC-008 | PASS | 四种有效根h及14:02到14:05基准 | test_causality; 413136逐条目标重算 |
| AC-009 | PASS | UP/DOWN/FLAT/PENDING与96分段占比/分母 | label_distribution.csv; independent research |
| AC-010 | PASS | 240已可预测组合全量覆盖413136行；16不足单列不伪造 | independent-verification.json; model_comparison.csv |
| AC-011 | PASS | 39特征、未来/跳过扰动和16次真实前缀 | unit-tests.txt; stage2/real-prefix-checks.json |
| AC-012 | PASS | 8种模型实现，112学习模型；16日线不足只证明不足处理 | decisions.json; model-parameters.json; models/ |
| AC-013 | PASS | 70/15/15原时间边界在过滤前固定 | feature-info.json; validation tests |
| AC-014 | PASS | 1232拟合实际目标结束及内层/校准/阈值purge | fit-index-audit.json; independent-verification.json |
| AC-015 | PASS | 2候选/5调度窗口，逐折n/结果/波动；日线空折不可计分 | candidate-grid.json; walk-forward.csv/report |
| AC-016 | PASS | 112冻结校准器用独立过去角色复现，阈值重新核算 | independent-verification.json calibration_checks |
| AC-017 | PASS | 七字段/互补概率/方向/信号；BUG-001浮点回归 | unit-tests.txt; 240导出独立复核; report-repair.json |
| AC-018 | PASS | 原模型选择和阈值冻结、唯一解锁；三次修复不追测试 | frozen.json; final-test markers; repairs and original source |
| AC-019 | PASS | 全量Accuracy/Balanced/MCC/F1/AUC/Brier/LogLoss/P-R/混淆/覆盖独立重算 | independent-research.txt; model_comparison.csv |
| AC-020 | PASS | 偏置/过拟合/概率/状态/基线分析，无稳定信号结论 | final_test_report.md; state diagnostics; 60 figures |
| AC-021 | PASS | 历史暴露披露通过；全新盲测资格仍未验证 | final_test_report.md; leakage_audit.md |
| AC-022 | PASS | 严格后续开盘、已知信号、只做多 | backtest tests; 128详细成交时刻独立核对 |
| AC-023 | PASS | 费用/价差/权益/胜率/PF/无交易/未平仓手算 | 5 backtest tests; independent-backtest-verification.json |
| AC-024 | PASS | 960费用场景/公平买入持有；假设不冒充平台成本 | backtest_comparison.csv; 128账目重算 |
| AC-025 | PASS | 新进程重载、状态/重放与112模型重复概率差0 | unit-tests.txt; reproducibility.json; unpacked prediction |
| AC-026 | PASS | 缺字段/未完成/错来源/周期/损坏/重复run拒绝，旧模型SHA不变 | test_data/test_delivery/test_models |
| AC-027 | PASS | 八报告、逐预测、图表、README及便携完整流程 | docs/delivery/*smoke.json; figures integrity; artifacts |
| AC-028 | PASS | 六阶段及七类测试材料分开、缺陷首败/修复/复测 | docs/phases; docs/testing; old candidate rejected |
| AC-029 | PASS | 两次完整独立训练，256选择/标签/覆盖/窗口一致，112模型差0 | reproducibility.json; repeat final test not opened |
| AC-030 | PASS | 固定v2候选独立重跑26测试/研究/回测/复现，无真实交易模块 | candidate.json; four logs; source review |

## 资格与失败证据

- 16个日线学习模型组合仍为INSUFFICIENT_DATA，不能称它们预测效果通过；工程通过只包含不足处理和完整披露。
- 112/112学习组合校准后Brier更差，不能据校准流程存在就认定概率可靠。
- 验证选中的1分钟h=1测试准确率55.68%（6638可计分），不是训练集分数，不代表可交易利润。
- 此前历史暴露未排除，不称全新盲测；来源/时区/单位/真实成本/实时能力仍未认证。
- BUG-001导出精度、BUG-002图日期、BUG-003休市输入门禁均留原源码和首败；前两次修复不改模型/方向/信号，第三次对8历史规范表完全无影响。原frozen.json和模型不改写，源码差异显式登记。旧候选v1虽25测试通过，完成审查后因BUG-003拒绝交付，v2重新验收26测试。
- 总RAM通过CIM读取受限未绕过；代表性30744训练样本资源探测实测峰值工作集281780224字节。没有承诺未测性能SLA。

## 材料与复核

完整执行与固定文件校验在docs/acceptance/runs/20261028-v2/；逐模型数据在reports/evidence/study-20261028-v1/。原始CSV的SHA保持不变，便携快照相同。最大回撤按完整K线收盘权益估计，费用为明确假设，无账户或真实委托。最终压缩包SHA与启动复核在docs/delivery及delivery目录。
