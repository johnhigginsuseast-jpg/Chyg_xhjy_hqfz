# 现有系统只读调查（2026-10-29）

本轮仅调查及需求定义。证据：[只读检查记录](../evidence/readonly-inspection-20261029.json)。观察时刻为2026-10-29 01:07:44（Asia/Shanghai），不是未来页面的实时快照。

## 已核实事实

- 现有工程为Python控制台，已有解释器 `D:\mycode\沧海易购1\market-direction-ml\.venv\Scripts\python.exe`，实测Python 3.12.14。无需为网页安装模型训练依赖。
- [已确认需求](../../../系统设计/docs/requirements/realtime-v0.1.md)、[跨源变更](../../../系统设计/docs/requirements/changes/source-v0.4-draft.md)和[验收标准](../../../系统设计/docs/acceptance/realtime-criteria-v0.1.md)约束原系统；前端另立基线，不替代其验收。
- 当前部署为 `http-research-20261028T231725`，候选candidate3；品种531/印江花果红茶二期，来源 `HTTP_CROSS_SOURCE_RESEARCH`，mode=LIVE、research_only=true、domain_shift_acknowledged=true。LIVE表示记录来源模式，不表示数据当前新鲜或模型有效。
- 冻结模型版本 `study-20261028-v1-1min-h1-logistic`，模型摘要 `d79afdbc7936dbd8692f903c37c0948de3c06c9579f671ed8bbb6f1f884b1ba7`；只读其JSON元数据，未载入或运行模型。
- 当前部署6000条行情版本、0条预测；最近轮询成功且记录NOMINAL_REST。没有以账本活动推断操作系统进程仍活着。旧[阶段记录](../../../系统设计/docs/project-status.md)为NOT_ACCEPTED，不改写成前端或预测系统已通过。
- 现有代码未发现HTTP监控服务器或网页API。行情供应商的HTTP请求在采集器内，不是可直接复用的本地监控接口；网页不得重复请求该供应商。
- `启动HTTP研究.cmd`启动采集器；`查看HTTP统计.cmd`运行 `-m realtime --source http-research --status`。后者仍调用[Ledger构造函数](../../../系统设计/realtime/ledger.py)，包含建表、PRAGMA和部署写入，因此本次未执行，未来只读服务也不调用。

## 数据结构与证据能力

| 对象 | 已有结构/用途 | 网页使用限制 |
|---|---|---|
| deployments | id、payload；冻结来源/模式/模型/策略 | 只查当前deployment.json指定且与库内一致的部署，不汇总旧部署 |
| bars | deployment、ts、revision、received_ms、payload | payload有raw_ts、OHLC、volume、turnover；按快照选最新修订；隔离事件不画成分钟 |
| predictions | id、deployment、anchor_ms、payload | 方向、p_up/p_down、signal、base_close、computed_at_ms、input_sha256；0条是实际空状态 |
| events | id、deployment、kind、at_ms、payload | POLL、SOURCE_STATE、PUBLISHED、MODEL_INPUT、CURSOR/BOOTSTRAP、RULE_SKIP、STOPPED等 |
| settlements | prediction、revision、at_ms、payload | HIT/MISS/FLAT/UNSCORABLE、目标/原因/修订；未结算状态按原账本推导 |

行情raw_ts为源开盘标签，ts=raw_ts+60000为结束标签，不能当作最新逐笔成交时间。尾根可能尚未确认完整；当前末尾ts=21:00，而BOOTSTRAP完整游标为20:59。应显示“最后观察的源K线”与“已确认完整K线”两种时间。received_ms是该行版本入账时刻；数值未变化时不会每次更新，最近成功获取时间须从成功POLL读取，不能取旧SOURCE_SNAPSHOT代替。

`Engine`以真实后继记录及2秒宽限确认完整性，保存的bars不全是完整根。只读展示应保守使用BOOTSTRAP/CURSOR及已合格历史作为完整证据；不自行推进游标、补分钟、重新执行三连规则或判断结算。

主统计沿用[Ledger.summary](../../../系统设计/realtime/ledger.py)：HIT/(HIT+MISS)，wait仍计主分母；FLAT/PENDING/UNSCORABLE另列。无回执/不合格回执属于无法计分，历史查询按实际发布时刻或未回执记录的计算时刻筛选，并选截止时刻内最新结算版本。今日是上海日期下的“今日发布预测”的结果，含对这些预测的后续结算，不是今日结算总数。

单条解释仅有MODEL_INPUT中的规则状态、来源、模型版本及特征/快照摘要等追踪字段；没有自然语言模型理由、特征贡献或SHAP。缺少字段显示未记录，不生成解释。

## 最小接口缺口与推荐处理

| 缺口 | 首版推荐处理 | 是否改现有系统 |
|---|---|---|
| 浏览器没有安全JSON入口 | 前端目录新增单个Python标准库服务，同源提供静态文件与GET /api/dashboard | 否 |
| Ledger构造入口会写入 | 服务用固定路径mode=ro/query_only只读连接，保持现有汇总语义；与原Ledger在隔离夹具及真实快照逐项比对 | 否 |
| 无可靠PID/进程会话协议 | 当前进程显示未知；另列近期轮询活动和最后停止记录。若要可靠进程探针，另行确认改动范围 | 否 |
| 无统一原子页面快照 | 单个读事务、最后完成POLL作为业务截止；一次响应含各区数据，另带诊断观察时刻 | 否 |
| 无命中率趋势接口 | 服务按原summary(as_of)语义生成历史时点统计；浏览器不累加命中或重新定义分母 | 否 |
| 无受控演示入口 | 明确独立demo模式/固定夹具，只在前端目录，失败时不自动切换 | 否 |

未来拟新增：`server.py`、`web/index.html`、`web/app.js`、`web/styles.css`、测试和启动cmd，全部在前端目录。此处只是规划，文件尚未创建。推荐SVG绘制本地分钟K线、量柱和统计趋势，不引入框架、CDN或付费图表服务。

替代方案：给现有采集器增加Web API或PID心跳，会改变冻结系统/运行入口；当前没有必要，首版不推荐，也未获本次授权。只做纯静态演示则不能完成真实监控，不能作为最终替代品。

## 本轮实际检查结果

只读需求/结构/启动入口调查PASS；当前候选全部文件及原15个保护文件摘要与既有清单一致。未启动第二采集器、未写账本、未修改现有系统。网页、接口、统计对齐和布局均NOT_TESTED，后续执行与本次文档检查分开记录。

10:51只读复查：同部署已有1条预测、6083条行情版本、0个结算版本，最近已记录POLL为10:49:00；状态是该时刻的WAITING_NEW_COMPLETE_BAR，不是10:51当前进程存活证明。已检查的现有文件摘要继续未变。保留01:07初查的0预测事实，不覆盖原观察；前端仍未实现或联调，不因记录自然增加而声称网页真实链路通过。
