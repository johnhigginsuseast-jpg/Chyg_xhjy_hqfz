# 本次验收的临时防自动休眠方案（等待用户授权，尚未执行）

原因：系统电源事件记录SleepTime=2026-10-29T11:36:40.5693007Z、WakeTime=11:42:38.9110190Z，对应上海19:36:40–19:42:38，与366.626秒POLL空档重合。恢复后出现23.640/41.625秒处理及一条迟到预测。原始证据在../evidence/20261029-live/evening-power-events.json和evening-interruption.json。当前电源查询显示自动睡眠接电900秒、电池600秒；没有修改这些设置。

拟执行的一次性动作：在既有Python环境启动一个独立、隐藏的辅助进程，仅调用Windows SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)，持续到**2026-10-29 21:05（Asia/Shanghai）**，正常到期/中断时主动清除该线程请求。屏幕仍可关闭，不申请DISPLAY_REQUIRED或AWAYMODE_REQUIRED；不改电源计划、注册表、客户端、模型、阈值、数据源或已有预测，不安装服务/计划任务/开机自启。

本动作需要单独确认，因为会临时影响本机自动休眠，属于先前行情读取范围之外的电源行为。可选择由用户手动保持本机唤醒联网，原采集进程不因此停止。

以下为拟执行的核心命令，未运行；确认后才生成并启动执行文件：

```python
import ctypes
import time
from datetime import datetime, timedelta, timezone

zone = timezone(timedelta(hours=8))
deadline = datetime(2026, 10, 29, 21, 5, tzinfo=zone)
remaining = (deadline - datetime.now(zone)).total_seconds()
if not 0 < remaining <= 7200:
    raise ValueError('Expired or outside this one-time approval window')
stop = time.monotonic() + remaining
set_state = ctypes.WinDLL('kernel32').SetThreadExecutionState
set_state.argtypes = [ctypes.c_uint32]
set_state.restype = ctypes.c_uint32
if not set_state(0x80000001):
    raise OSError('Sleep-prevention request failed')
try:
    while time.monotonic() < stop and datetime.now(zone) < deadline:
        time.sleep(min(20, max(0, stop - time.monotonic())))
finally:
    set_state(0x80000000)
```

执行后验核：记录辅助PID/路径/启动时间及API返回值；确认原电源计划未变；继续以真实POLL、发布及有效根判断60连续锚点，不把防休眠请求成功当作行情验收通过。到期记录清除请求及进程结束。若批准到达时窗口已过，拒绝执行，不自行延长。

限制：Windows官方说明，此API不能阻止用户主动睡眠、合盖或电源按钮引起的睡眠；也不据此保证宿主退出、断电或外部强制挂起后的连续性。需要保持网络连接。主采集进程与该辅助进程分离，辅助退出不停止采集。

依据：[Microsoft SetThreadExecutionState文档](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate)。本页是可审阅的操作方案，不是已执行记录，不改变已确认v0.4预测/计分基线。
