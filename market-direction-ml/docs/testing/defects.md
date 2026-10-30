# 缺陷记录

## BUG-001 — XGBoost概率CSV导出精度（P1，VERIFIED）

- 关联：FR-013/FR-014、AC-017/AC-019；study-20261028-v1。
- 实际：独立复核发现部分float32概率CSV读回后p_up+p_down偏差最大约6e-8，超过1e-8验收门槛；首次失败保留于reports/evidence/independent-verification-initial.txt。
- 原因：p_down在float32中计算且CSV以短十进制保存，原模型概率没有对应的float64导出。
- 修复：导出边界提升为float64后计算互补概率；共享prediction_frame用于正常评估、原冻结模型导出修复及回归测试。模型对象、参数、校准器与阈值不调整，不重训追测试。
- 保留：原报告/预测压缩包与修复前源码保存在实验repairs/probability-export/；原frozen.json不改写，独立复核仅允许显式登记的报告模块差异，其他源/模型必须仍匹配原冻结。
- 复测：float32 CSV round-trip回归通过；240组/413,136条实际预测独立重算通过，16个不足组合保持不足；方向/信号/模型/选择未变。正式候选阶段再执行独立验收。

## BUG-002 — 科研图日期标签重叠（P2，VERIFIED）

- 关联AC-027；人工查看1min-h1诊断及回测图发现日期刻度过密。
- 修复：AutoDateLocator限制刻度数并用ConciseDateFormatter；数值/模型/预测不改。
- 原图、源码与重绘命令保留在实验repairs/probability-export；全部60图重绘。复查1min-h1诊断/回测两种共享版式，日期不再重叠；全部PNG完整性在最终候选检查中核对，不冒称逐张人工检查。

初检时间/事件问题已按阶段1数据策略处理，详见reports/data_audit.md和docs/decisions.md。默认绘图库缓存目录受限已改为工程内缓存，原警告保留。

## BUG-003 — 周日/周六夜盘输入缺少拒绝门禁（P1，VERIFIED）

- 完成审查发现：现有真实数据虽无这些记录，但共享规范化函数未拒绝用户明确休市日期的非法输入；AC-005边界覆盖不足。
- 新增反例在修复前失败，原输出保留于docs/acceptance/runs/20261028-v1/calendar-gap.txt；旧候选不作为最终交付候选。
- 在共享canonicalize补充休市拒绝；不调整任何现有样本、模型/校准器/阈值。修复前源码保留，逐周期重算确认原全部规范K线完全一致后登记calendar-validation-repair.json。
- 另建20261028-v2候选重新独立验收，不把旧25测试通过当作当前通过。
- v2实际复测：26测试、240组预测/指标、回测/复现检查与解压包全链路均通过；所有8历史规范表逐字段完全不变，未重训或调整原模型。
