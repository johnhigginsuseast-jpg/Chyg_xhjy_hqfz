# OHLCV 行情方向研究

Windows/Python 本地研究工程，使用用户提供的真实历史 CSV；无账户连接或真实委托。原始数据位于上级 `2026-10-28`，派生文件与全部新产物仅写本工程。

**工程运行通过与预测信号有效是两种结论。** 既往历史暴露未排除，本轮末15%是冻结方案下的历史留出，不称全新盲测。没有可靠优势时报告“当前数据未验证出稳定可用的预测信号”。

## 当前入口

在 PowerShell 中：

```powershell
Set-Location -LiteralPath 'D:\mycode\沧海易购1\market-direction-ml'
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
```

本机 `.venv` 已创建，确切依赖在 requirements.txt。新环境可用自己的 Python 3.12 执行 `python -m venv .venv`，然后：

```powershell
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m pip check
```

如本机 PATH 无 Python，请使用本机已安装的 Python 解释器路径。不需要原行情客户端、其他工程的环境或付费模型。

## 复现完整流程

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m src.data_audit
& '.\.venv\Scripts\python.exe' -X utf8 -m src.train --run-id my-new-study
& '.\.venv\Scripts\python.exe' -X utf8 -m src.evaluate --run-id my-new-study
& '.\.venv\Scripts\python.exe' -X utf8 -m src.backtest --run-id my-new-study
& '.\.venv\Scripts\python.exe' -X utf8 -m tests.verify_research --run-id my-new-study
```

每次训练使用新 run-id，拒绝覆盖已有实验。`src.train`完成模型拟合、训练内5轮滚动、校准、阈值选择及冻结，不查看最终测试评分。`src.evaluate`检查冻结源码/数据/配置后单次解锁，重复解锁会拒绝。重新使用同一批历史不会恢复“未暴露”资格；源码/模型/阈值改动不能对原测试重调。

配置在 configs/default.json，可修改数据目录、研究周期、跨度、CPU线程（1–4）、阈值候选及模拟费用。修改数据/时间策略后先重新审计，建立新实验并保留旧记录。默认研究所有8周期×4跨度，不根据测试挑最终跨度。

交付包另含 `data/source/` 的原CSV快照（与用户原文件SHA256一致）和 `configs/portable.json`。移动工程后使用 `src.data_audit --config configs/portable.json`、`src.train --config configs/portable.json --run-id 新实验名`；预测时将 `--input` 改为该快照文件路径。原始记录不覆盖，既有实验内保存的绝对来源路径仍保留作历史审计，移动工程不代表历史重新变成未暴露数据。

配置/CSV中的周期 `0` 表示日线，其余数字为分钟周期。模型概率归一及图表日期标签的报告修复记录在实验 `report-repair.json`；原模型、参数、校准器和阈值没有更改，修复前输出保留可对照。

## 新增完整 K 线后预测

以下例子使用已保存的3分钟h=1逻辑回归。输入必须包含完整历史加新增完整根；接口通过重放恢复规则状态，支持进程退出后继续。输入CSV/Excel/Parquet均需时间和OHLCV；来源与周期必须匹配。

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m src.predict `
  --model 'models\study-20261028-v1\3min-h1-logistic.joblib' `
  --input '..\2026-10-28\3分钟K线.csv' `
  --as-of '2026-10-28 00:00' `
  --source-identity 'supplied-20261028-native-csv' `
  --output 'reports\latest-prediction.json'
```

时间采用数据原生时间，时区仍未独立核实；`--as-of`必须是真实允许使用数据的时刻，接口拒绝包含尚未完成根的输入。日线另需 `--minute-reference` 指向同源1分钟CSV，以确认开盘时刻。模型只能从本工程models内加载，读取前核对文件SHA256；仍不得导入不可信外部pickle/joblib模型。

Python 接口为 `src.predict.predict_history(model_path, input_path, as_of, source_identity, output=None, minute_reference=None)`。七个必需字段为 p_up/p_down/predicted_direction/confidence/prediction_horizon/prediction_timestamp/model_version；另有 signal（up/down/wait）、最新完整根和规则状态。

1分钟规则跳过根返回RULE_SKIP，不伪造概率；其他有效完整根均给出方向/概率。观望保留预测。平盘不进入二分类训练或评分，但保留预测账目；因此p_up/p_down表示二分类涨跌条件概率，不是包含平盘的三分类概率。

## 已固定的数据和统计口径

- 25条开盘单价记录作为事件并入随后完整分钟，保留源行与成交量，不能把事件当独立完整K线。原CSV不变。
- 1分钟按相邻有效收盘三连后跳两根，期间不重触发，之后重新计数；其余周期无此规则。h按未来有效根，不是自然分钟，目标时间事后结算，不偷看未来筛选状态作输入。
- 无记录时间按用户要求作为休息；周六仅日盘、周日休息。正式节假日历未认证，实时“还没收到记录”不能据此认定休市。
- 合成桶的源标签与available_at分开，20:14最后成交的20:15桶最早20:15使用；日线最早当日16:00使用，不在午夜偷看日终。
- 固定64有效根热身；39个价格/趋势/波动/动量/量价/状态特征，无小时/星期特征。日收益只来自规则接纳序列，不引入跳过根的外部指标。
- 原时间轴70/15/15；验证前半校准、后半阈值。所有边界按实际目标结束purge；树模型早停用训练内部时间段。
- 每类学习模型2个候选；CPU最多4线程；固定随机种子。Logistic仅训练缩放，LightGBM/XGBoost/CatBoost均真实调用。
- 四个规则基线概率是未校准的0/1规则；四个学习模型用独立校准段sigmoid。全覆盖准确率、二分类信号覆盖率、所有预测信号覆盖率与平盘/待结算计数同时提供。
- 日线150根无法满足预登记的学习模型拟合/校准门槛，相关组合保留INSUFFICIENT_DATA，不删除或伪造指标。

## 证据与报告

- reports/data_audit.md：源数据、时间与处理口径。
- reports/feature_report.md：特征和因果约束。
- reports/model_comparison.csv：完整模型×周期×跨度矩阵、样本量、方向及概率指标。
- reports/walk_forward_report.md：滚动窗口及波动；逐折原数据在实验目录。
- reports/final_test_report.md：冻结历史留出、基线对照、偏置/过拟合/概率/状态诊断。
- reports/backtest_report.md：单独的模拟成交、费用敏感性及买入持有对照。
- reports/leakage_audit.md：时间/标签/拟合角色与既往暴露说明。
- reports/acceptance_report.md：最终候选逐AC验收及未验证资格。

阶段、七类测试资料和需求追踪在docs/；[决策记录](docs/decisions.md)保存用户授权与推荐选择，[AI_CHANGELOG](AI_CHANGELOG.md)记录AI修改。逐预测、冻结、拟合索引、校准复核、复现证据在reports/evidence/对应run-id。原始二进制不参与训练或上传。

这是离线历史研究系统。新数据独立验证、真实时区/品种认证、实时延迟、做空资格和真实平台成本均未验证。
