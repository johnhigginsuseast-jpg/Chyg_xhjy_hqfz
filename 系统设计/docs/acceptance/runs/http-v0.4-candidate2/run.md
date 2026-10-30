# 独立检查记录：HTTP v0.4 candidate2

- 基线：已确认v0.1与CR-RT-003；[验收条件](../../../acceptance/realtime-criteria-v0.1.md)及[跨源变更](../../../requirements/changes/source-v0.4-draft.md)。
- 候选：[固定清单](../../../candidates/http-v0.4-candidate2.json)，代码SHA256为51657113c71126f3c54870a9052df6dd187f305c1091f1351adee591f60ac457；原模型、批准、引导及工具版本同时固定。
- 2026-10-28，本机Windows/原Python环境，Codex独立执行新增REPLAY场景及只读LIVE快照复算。独立检查中未再改产品代码；REPLAY不写真实预测。
- 阶段：S3测试中的独立检查，尚未满足完整S4入口；本记录可累计真实结果，不能据此提前进入正式交付。

| AC | 实际执行与范围 | 结果 | 证据/尚欠 |
|---|---|---|---|
| AC-RT-001 | 按已批准v0.4研究版条件检查531/名称、HTTP原数量/时间策略、独立引导与部署、模型及用户跨源批准摘要；不宣称原生等价 | PASS | candidate2-binding-check.json；原生等价失败保留 |
| AC-RT-002 | 当前进程有真实HTTP成功/超时及恢复，但处于名义休市，未在本候选观察新增分钟 | NOT_TESTED | 仍需真实新分钟；旧协议观察不替代本轮运行链路 |
| AC-RT-003 | 坏字段/身份/时间/顺序/边界及形成中根隔离回放通过；当前候选真实完成转换未发生 | NOT_TESTED | 待当前候选真实形成中→后继完整根 |
| AC-RT-004 | 63/64根拒绝、65根概率分支；开盘合并手算；真实冻结模型三连/跨时段/跳两根、原入口概率回归；tie判UP、wait保留方向 | PASS | 37项冻结回归及7项独立场景 |
| AC-RT-005 | 合成迟到/已知目标/无回执拒绝已测；0真实发布 | NOT_TESTED | 仍需真实输入截止、计算及持久化回执 |
| AC-RT-006 | 手算HIT/MISS/FLAT/PENDING/UNSCORABLE；真实规则19:03锚点目标为19:06；锚点失效追加UNSCORABLE；原预测不可改写 | PASS | 独立REPLAY，非实时效果证明 |
| AC-RT-007 | 6HIT/4MISS另加平盘/未到期/迟到，主率60%，wait计分，子集/覆盖率、Wilson及0分母正确 | PASS | 独立手算与产品账本对比 |
| AC-RT-008 | 源/部署隔离、行情锚点失效及结果版本、6/10→7/10时点恢复、早于发布时点为0；预测只追加 | PASS | 7独立场景+冻结回归；BUG-RT-006/007关闭 |
| AC-RT-009 | 重启跨两个跳过根后可结算原预测且不补发；重复、缺根和补数边界回放通过 | PASS | 回放/故障注入范围；真实长时间前向仍由015判断 |
| AC-RT-010 | 缺根/滞后拒绝已测，真实官方休市核实与两个后续已观察交易日缺数到期独立场景未齐 | NOT_TESTED | 不用自然日替代，不补价或自动换源 |
| AC-RT-011 | 已回执备份恢复、一致性、不可改写、写失败不新增正式回执；模拟提交预测后无发布回执的中断不得补发 | PASS | 隔离REPLAY故障注入；不冒充真实业务样本 |
| AC-RT-012 | 后续独立控制台检查复现：输出缺少明确模型版本，来源和部署不能代替模型标识 | FAIL | candidate2-console-model-first-fail.log；转candidate3修复 |
| AC-RT-013 | 固定3秒/4线程策略，当前0发布，p95为null | NOT_TESTED | 真实连续60可预测锚点、全量延迟及异常/迟到占比 |
| AC-RT-014 | 候选/15原模型保护文件摘要不变；可信路径/哈希/原来源门禁正反例；只读客户端/固定行情地址，输出范围受限 | PASS | 独立7场景、37回归、源码审查和清单核对 |
| AC-RT-015 | LIVE快照0预测/0计分；独立算术一致仅适用于零样本，模型逐条复算数0 | NOT_TESTED | 尚无真实前向发布→目标→结算；仍标效果样本不足 |

本轮8项PASS、7项NOT_TESTED，覆盖全部15项，不以总通过率豁免必需项。原始日志：`docs/evidence/20261028-preflight/candidate2-frozen-independent-cases.log`（7项，3.739秒）；`candidate2-frozen-regression.log`（37项，28.415秒）；`candidate2-auditor-selfcheck.log`。本目录observation-20261028T2255/report.json与ledger.sqlite3固定一轮真实证据，观察时间以JSON为准。

结论：**NOT_ACCEPTED / 不予正式交付**。S3继续，未代签人工确认；原生缓存实时性和DDE遗留缺口保持原状态，v0.4仅授权独立跨源研究。

后续补测使本候选最终为FAILED：8 PASS、1 FAIL、6 NOT_TESTED。37/7已通过证据保留；未因其绿灯忽略FR-RT-009/AC-RT-012缺失。产品代码修复后另建candidate3，不沿用本候选通过声明。
