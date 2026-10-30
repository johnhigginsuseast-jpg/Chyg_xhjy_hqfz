# 10月30日下午：原入口按需恢复与原生聊天跟进

状态截至14:40，Asia/Shanghai。本次目标仍是原冻结candidate4的真实行情验收，不改变模型、规则、来源、阈值或60/20秒门槛。

## 证据与选择

原采集PID20752及辅助PID5404/14488均已消失，最后POLL为11:04:50，无正常STOPPED/CLEARED日志。11:20系统uptime约33814秒，不据此推断具体终止原因。保留异常退出和所有既有预测，先一致性备份；未把进程缺失改成网络等待。

用户先前已允许常规问题按推荐方案处理，并明确允许今天临时防自动休眠至16:05、结束时提前清除。采用Windows已有任务计划程序托管相同入口，减少对聊天工具进程生命周期的依赖；不安装服务，不创建周期或开机触发，不修改电源计划。宿主关闭/系统重启后的实际存活仍未通过破坏性测试，不能用架构推断替代实测。

## 实际运行

- Codex-Market-Collector-20261030：普通交互用户，按需启动原venv/pythonw.exe，原realtime模块与--source http-research参数；Task状态Running，实际Python进程PID23404，启动UTC06:31:57.7086965Z。
- Codex-Market-Awake-20261030：同样普通权限、按需运行原已批准脚本；实际调用PID11136，14:32:01真实ACTIVE，固定截止16:05，已有stop标记提前退出机制不变。
- 原生任务XML实查均无触发器（0），不是周期或开机任务。初始PowerShell空值数组计数为1的原始输出保留，以后续XML核验为准。LastTaskResult=267009是当前运行状态，不作为完成成功码。
- 当前执行程序是venv的pythonw重定向到原Python运行时，启动元数据由进程自身记录PID；随后Get-Process核验实际Path与精确启动时间。canonical collector-process.json的interpreter为实际进程Path，launcher单列原venv入口。后续恢复应使用task_name按需启动，不直接用base interpreter代替venv。

14:32:20新BOOTSTRAP只暖机/补数并结算旧预测，未补发11:04后及下午缺失历史预测。14:40已有新的成功POLL和形成中行情，模型/来源/部署身份正确。新连续段从该BOOTSTRAP后判断，不与晨盘断点拼接。

## 原生同聊天定时跟进

原生automation_update现在可用，创建heartbeat id=automation、目标为本聊天01a18203-8084-7c62-a07f-d4bab990638f，状态ACTIVE。已回读保存配置：每5分钟、仅至今天16:05；普通进展写证据，达标、实质失败或用户操作需求时给结论，达标或本次截止后暂停。完整prompt和配置快照见docs/evidence/20261030-live/native-heartbeat-saved.toml，核验JSON同目录。

该原生跟进不启动另一个CLI聊天写入者。配置创建和回读已通过；真实调度触发尚待核验，不能据此关闭OPS-RT-001或追认早上09:28成功。旧单次Windows定时器仍保留失败记录，无后续触发，不重跑旧CLI入口。

## 操作与停止

只在核验任务/实际进程终止、且既有worker.lock空闲后恢复采集；观察超时或临时HTTP错误不重启。Windows TaskScheduler自身IgnoreNew及既有文件锁防止重复运行。采集任务按需恢复命令为Start-ScheduledTask -TaskName Codex-Market-Collector-20261030，需先满足上述条件。

验收先结束则创建runtime/http-research/awake-20261030.stop，等待CLEARED成功、实际PID11136退出及Task状态/本轮电源超时值核验；最晚16:05由原脚本自动清除。不得延长到夜盘。旧PID14488异常退出无CLEARED日志的事实独立保留。

证据：scheduler-recovery-plan.json（原入口命令、语法检查）、collector-task.xml/awake-task.xml、scheduler-recovery-start.json、scheduler-recovery-verified.json、scheduler-collector-identity.json/scheduler-awake-identity.json；均在docs/evidence/20261030-live。TaskScheduler有限范围操作通过自动审批审查后执行，未修改业务代码或应用写入锁。
