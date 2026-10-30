# 缺陷记录 v0.1

保留首败；关闭只指本次范围复测，不代表整体验收通过。原始路径相对前端目录。

| 编号 | 原问题 | 修复与关闭证据 |
|---|---|---|
| BUG-WEB-001 | 演示末条碰17倍数，被标迟到、无当前预测 | 末条明确合格；unit-after-fixes.log和候选4 regression.log，CLOSED |
| BUG-WEB-002 | p_up字符串未在服务边界拒绝 | 预测/行情数值校验、安全503；候选4坏字段测试PASS，CLOSED |
| BUG-WEB-003 | SQLite上下文未关闭，Windows测试清理锁3个ERROR | 使用closing并保留事务；16项完整执行/清理PASS，CLOSED |
| BUG-WEB-004 | 初轮10,000记录p95=2.7326365秒 | 趋势单次回放，原时点/修订对齐，unit-after-fixes.log p95约0.68秒；首败保留unit-first.log，CLOSED |
| BUG-WEB-005 | SVG的hidden属性未移除，有子节点却不显示 | toggleAttribute；桌面/三视口图表可见，CLOSED |
| BUG-WEB-006 | 重开相同详情停在加载中 | 加载前清signature；实际重开及修订自动更新通过，CLOSED |
| BUG-WEB-007 | DEMO首次503没有banner，且无缓存却声称缓存 | 初始HTML标模式、首次错误不假缓存；first-error-fixed.json，CLOSED |
| BUG-WEB-008 | 对照工具把原工程2份独立变化.md当成代码污染 | 文档变化单列，源码/配置和原15文件仍硬门禁；live-check-1793274849189969500/report.json无产品差异，CLOSED |
| BUG-WEB-009 | 手机固定viewBox1000导致图高111.5px、字缩小 | 按容器宽度绘制；final-layouts.json三尺寸图高340px，无页面横溢，CLOSED |
| BUG-WEB-010 | JSON/断网错误显示原始英文异常 | 中文映射；failure-recovery-final.json、offline-final.json，CLOSED |
| BUG-WEB-011 | 离线12秒后仅写缓存，未明确过期 | 超10秒明确“上次快照已过期”，成功刷新时间不变；offline-final.json，CLOSED |
| BUG-WEB-012 | 未提交筛选草稿被自动刷新采用 | 请求仅用已提交state.filters；filter-pagination.json草稿50条/应用后34条，CLOSED |
| BUG-WEB-013 | id=reset遮蔽form.reset，重置报TypeError | 改reset-filters；实际清空条件并回第1页，filter-pagination.json，CLOSED |
| BUG-WEB-014 | Windows客户取消请求时ConnectionAbortedError10053打印堆栈 | 写响应时处理ConnectionError；client-abort-first/fixed.log、候选4取消客户测试，CLOSED |
| BUG-WEB-015 | 控件边框对比度约2.2低于3 | #60758e；contrast-fixed-ratios.json边框3.18865、抽测文字最低8.0245，CLOSED |
| BUG-WEB-016 | 候选1基准再现p95=2.6938994秒 | 完整原文作键的有界解析/校验缓存，不缓存业务汇总；修改原文及返回值污染测试PASS；候选4 p95=1.270355秒，CLOSED |
| BUG-WEB-017 | Windows默认HTTPServer可能共享已占端口，重复启动未报错 | LocalServer关闭reuse并启用SO_EXCLUSIVEADDRUSE；port-conflict-fixed.log、候选4同端口拒绝且首服务仍200，CLOSED |

001至004首败/复测在docs/evidence/development；其余浏览器首败与修复证据在docs/evidence/browser。候选1失败日志不覆盖，不能用后来的PASS改写首轮结果。

## 环境及测量问题

- ENV-WEB-001：原生Edge URL可靠识别失败，用户已显示完整地址栏后仍被Windows Computer Use安全检查中止。当前IAB/MCP Apps清单不提供可控Edge/Chrome标签页；017、018、020整体仍BLOCKED，未豁免。
- TEST-WEB-001：启动测试的cmd退出等待超时；首失败记录保留。实际端点、脚本SHA及进程启动时间重新核对，仅停止自建服务/cmd并确认监听和3个进程消失。startup-smoke.json关闭此探针清理问题，不将其说成产品端口故障。
- TEST-WEB-002：最初连续更新测量在PageDown平滑滚动尚未结束时取锚点（38→240）。固定滚动后重测十轮不同状态，全部保持；ten-updates-stability-final.json是有效结果，旧测量保留。
- TEST-WEB-003：部分waitFor发生工具自身截止，但返回诊断已可见；改读实际DOM/网络事件核实。首个LIVE故障探针过早记录加载态，保留，live-failure-no-demo-final.json等待记录可见后给出有效缓存对照。

- TEST-WEB-004：原始CDP长截图出现重复拼接，保留overview-capture-first-failure.jpg，不作有效页面证据。改用Tab.screenshot(fullPage=True)，逐图查看桌面、390与360截图均正常；capture-review.json记录范围。普通viewport截图只是1280x720物理裁切，不改标1440x900完整画面。

## 2026-10-30 环境复测

ENV-WEB-001 CLOSED（本版前端必需平台范围）：已有Edge扩展可靠识别目标URL，用户正常地址栏访问后完成原生布局/键盘/首屏实测。原生App地址栏安全中止未绕过，未放宽同源保护。测试viewport/定位/计时接口及点击超时的失败与复核见[最终记录](../acceptance/runs/native-edge-20261030/run.md)。产品001至017关闭状态不变。
