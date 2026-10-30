# HTTP v0.4 candidate4 检查记录

2026-10-29，本机Windows/原Python环境，S3重新冻结后检查，**NOT_ACCEPTED**。固定产品SHA256为68ee5278245342068a2231f73e39da73cef8bc9e1667c319eae199ac80a0cdf6，[清单](../../../candidates/http-v0.4-candidate4.json)及zip保存。唯一产品修复为网络传输错误不再额外等待已消耗的轮询间隔；服务器明确等待提示仍保留。

45项回归、7项独立场景、3项冻结后补测PASS。首次补测使用旧candidate3清单而拒绝变化，FAIL原文保留，未放宽检查。修复前2 FAIL/2 PASS实际复现；45回归含4项重试时序及4项隔离防休眠测试。隔离REPLAY不计实时效果。

| 项目 | 状态 | 范围 |
|---|---|---|
| AC-RT-001 | PASS | 原批准来源/品种/模型不变；6371根同一HTTP完整历史延伸保留初始规则起点和摘要 |
| AC-RT-002 | NOT_TESTED | 新部署三个连续实时分钟尚欠；旧部署实测保留但不作新部署证据 |
| AC-RT-003 | NOT_TESTED | 回归通过；新部署形成中→完成及全部实际输入复算尚欠 |
| AC-RT-004 | PASS | 原内核/模型/规则不变，45回归及7独立场景 |
| AC-RT-005 | NOT_TESTED | 发布/排除回归通过；新部署真实回执与目标链路尚欠 |
| AC-RT-006 | PASS | 下一有效根/追加结算/例外回放 |
| AC-RT-007 | PASS | 手算统计、wait分母、Wilson及空样本 |
| AC-RT-008 | PASS | 隔离/追加/修订/历史时点回归 |
| AC-RT-009 | PASS | 重启/缺数/不补发回放 |
| AC-RT-010 | PASS | 用户确认常规周历保持，具体节假日另核 |
| AC-RT-011 | PASS | 备份故障注入通过；旧真实结清库一致性备份保留 |
| AC-RT-012 | PASS | 冻结后补测控制台身份和统计通过 |
| AC-RT-013 | NOT_TESTED | 新部署连续60及全量p95≤20秒尚欠，不能用旧版局部p95替代 |
| AC-RT-014 | PASS | 原15保护文件与新固定清单核验，输出范围及只读访问保持 |
| AC-RT-015 | NOT_TESTED | 新部署连续60及该范围全部到期结果独立复算尚欠 |

当前10 PASS、5 NOT_TESTED，不正式交付。原candidate3连续尝试因19:35/休眠/20:25缺根中断，已证实最长32；其全部109预测及65/105成绩独立保留，不混入本部署。

[21:03初始独立审计](observation-20261029T2103/report.json)0预测、issues=[]，只证明当前摘要/保护/空账本一致，不能作为实时发布通过。新后台PID14144已核验启动时间/路径及新POLL，常规休市状态；全库旧行保留及新固定文件检查见docs/evidence/20261029-live/candidate4-postcheck.json。

原始日志位于docs/evidence/20261029-live：candidate4-regression.log、candidate4-independent.log、candidate4-frozen-supplement.log、transport-cadence-repro.log及candidate4-freeze.log。后台启动元数据只定位进程，实际存活另核PID/时间/路径及新POLL。
