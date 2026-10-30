"""Describe existing frozen evidence; never fit models or change experiment decisions."""
import json
import pandas as pd

import run

STUDY = run.STUDY
OUTPUT = STUDY / "runs" / "daily-h1-short4-20261030-01"


def read(name):
    return json.loads((OUTPUT / name).read_text(encoding="utf-8"))


def write(path, text):
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def pct(value):
    return f"{value * 100:.2f}%"


def main():
    result, counts, audit = read("result.json"), read("sample-counts.json"), read("source-audit.json")
    test, cv, uncertainty = read("holdout-metrics.json"), read("walk-forward.json"), read("uncertainty.json")
    independent = read("independent-verification.json")
    assert independent["status"] == "PASS" and read("preservation.json")["status"] == "PASS"
    for name in ("preflight-tests.txt", "postflight-tests.txt", "legacy-regression.txt"):
        assert "exit_code=0" in (OUTPUT / name).read_text(encoding="utf-8")
    train_prediction = pd.read_csv(OUTPUT / "cv-training-predictions.csv")
    full_prediction = pd.read_csv(OUTPUT / "predictions.csv")
    training_metrics = []
    for (fold, name), group in train_prediction.groupby(["fold", "model"]):
        training_metrics.append({"role": "TRAIN_IN_SAMPLE_AUDIT_ONLY", "fold": int(fold), "model": name, **run.metrics(group.y, group.p_up)})
    final_pos = read("frozen.json")["training_positions"]
    for name, group in full_prediction.groupby("model"):
        part = group.loc[group.bar_position.isin(final_pos)]
        training_metrics.append({"role": "FINAL_TRAIN_IN_SAMPLE_AUDIT_ONLY", "model": name, **run.metrics(part.y, part.p_up)})
    run.write_json(OUTPUT / "training-audit-metrics.json", {"warning": "In-sample only; never evidence of predictive ability", "models": training_metrics})

    sections = [("扩展1训练", cv[0]["training"]), ("扩展1验证", cv[0]["validation"]),
                ("扩展2训练", cv[1]["training"]), ("扩展2验证", cv[1]["validation"]),
                ("最终开发拟合", counts["development_fit"]), ("历史留出测试", counts["historical_holdout"])]
    table = ["| 区间 | 起止交易日 | 原根 | 热身 | 就绪预测 | 涨 | 跌 | 平 | 未结算 | 隔离 | 二分类实数 |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, row in sections:
        table.append(f"| {name} | {row['first'][:10]}—{row['last'][:10]} | " + " | ".join(str(row[key]) for key in
                     ("raw_rows", "warmup", "forecast_anchors", "up", "down", "flat", "pending", "purged", "binary_samples")) + " |")
    summary_table = "\n".join(table)
    comparison = ["| 模型 | 可计分n | 准确率 | 平衡准确率 | 混淆矩阵 | 准确率Wilson95%描述区间 |",
                  "|---|---:|---:|---:|---|---|"]
    for row in test["models"]:
        lo, hi = row["wilson95_accuracy_descriptive"]
        comparison.append(f"| {row['model']} | {row['n']} | {pct(row['accuracy'])} | {pct(row['balanced_accuracy'])} | {row['confusion_matrix']} | {pct(lo)}—{pct(hi)} |")
    cv_table = ["| 折 | 模型 | 验证n | 准确率 | 平衡准确率 | 混淆矩阵 |", "|---|---|---:|---:|---:|---|"]
    for row in cv:
        for name in ("logistic_C0.1", *run.BASELINES):
            metric = row["models"][name]
            cv_table.append(f"| {row['fold']} | {name} | {metric['n']} | {pct(metric['accuracy'])} | {pct(metric['balanced_accuracy'])} | {metric['confusion_matrix']} |")
    differences = ["| 日期 | 字段 | 原日线 | 同源分钟聚合 |", "|---|---|---|---|"]
    for row in audit["daily_minute_differences"]:
        differences.append(f"| {row['date']} | {','.join(row['fields'])} | {row['daily']} | {row['minute']} |")
    raw_label = audit["h1_all_raw_labels"]
    audit_text = f"""# 日线原始数据审计 v0.2

只读检查：{audit['first']} 至 {audit['last']}，原始/有效均150根。1分钟参照55386条。字段为时间、开盘、最高、最低、收盘、成交量、成交额；严格递增，无重复时间、缺失数值、非有限数、非正价格、负量/负成交额或OHLC高低价逻辑错误。零成交量0、零成交额0；成交量高于Q3+3IQR的记录0（仅描述，未据此删行）。字段统计与源SHA256见[source-audit.json](source-audit.json)。

原始h=1标签：上涨{raw_label['UP']}、下跌{raw_label['DOWN']}、持平{raw_label['FLAT']}、未结算{raw_label['PENDING']}；前5根热身也保留于此分母。特征就绪145根标签为上涨63、下跌77、持平4、待结算1，二分类共140；二者分母不同，不混用。

按原生分钟19:00以后归下一自然日，日盘归当天进行交叉审计：150/150收盘、150/150最高价、150/150成交量一致；开盘146/150、最低149/150一致。共4个日期、5个价格单元格不同，以下全部保留，未修改或替换日线。

{chr(10).join(differences)}

每天均有同源当日16:00末分钟，且其收盘等于日线收盘；依既有研究规则将日线可用时刻设为当日16:00，午夜仅是交易日标签。24根周六日线、0根周日线；周六日盘/周日休息、缺席时段按休息处理，不补价格。此检查确认内部一致性，不证明平台官方完整性；缺席究竟节假日或历史缺失，仍依用户研究假设而非平台认证。

品种代码、时区、平台真实性、正式节假日历、价格/成交量单位未核实。原生无时区时间保留，不擅自转为北京时间；执行日志另用明确UTC。数据未与其他研究/行情源合并；不读取客户端、账户或二进制非行情数据。
"""
    write(OUTPUT / "data-audit.md", audit_text)
    train_lines = ["| 训练角色 | 模型 | n | 训练内准确率 | 训练内BA |", "|---|---|---:|---:|---:|"]
    for metric in training_metrics:
        role = f"折{metric['fold']}" if "fold" in metric else "最终拟合"
        train_lines.append(f"| {role} | {metric['model']} | {metric['n']} | {pct(metric['accuracy'])} | {pct(metric['balanced_accuracy'])} |")
    write(OUTPUT / "training-audit.md", "# 训练内拟合审查（不是预测能力）\n\n以下只供排查过拟合，不进入选参、优势门槛或对外预测能力结论；样本外证据只取扩展验证和已暴露历史留出。完整指标见training-audit-metrics.json。\n\n" + "\n".join(train_lines))
    paired = ["| LR相对基线 | 配对准确率差 | 95%成块自助区间 |", "|---|---:|---|"]
    for name, row in uncertainty["paired_differences"].items():
        lo, hi = row["paired_block95"]
        paired.append(f"| {name} | {pct(row['mean_accuracy_difference'])} | {pct(lo)}—{pct(hi)} |")
    report = f"""# 日线方向模型研究 v0.2

已完成独立训练实验，**未得到可靠预测信号**。run-id：`{result['run_id']}`。研究资格门槛FAIL；本次程序/保全检查通过不代表预测能力通过。

仅h=1，逻辑回归最终拟合111条开发样本，C=0.1。测试30根中上涨12、下跌16、持平1、未结算1；28条二分类结果中命中16条，准确率57.14%，平衡准确率53.125%，与永远跌的准确率相同。预测上行6次，真实上行召回仅3/12=25%，存在偏向下跌的表现。未承诺盈利或实时可用。

## 数据与短窗口

原始日线150根，2026-04-27至2026-10-27；完整审计见[data-audit.md](data-audit.md)。保留原始来源，4日5个OHLC差异未纠正。四个特征是r1=Ct/C(t-1)-1、r3=Ct/C(t-3)-1、Ct/mean(Ct..C(t-4))-1、std(r[t-4..t],ddof=1)。所有窗口min_periods等于窗口长度，不填补，首个全有效位置5（2026-05-05），实际热身5。时间t指已完成日线，目标为下一条已有有效日线，而不是下一自然日。

## 固定时间切分与真实数量

先按150根有效时间轴固定前120根开发、末30根留出，再做热身/持平/目标隔离。开发内只做两个足量扩展折，保留拟合>=80、验证/测试>=10且两类门槛。表中涨跌平未结算指特征就绪且目标未跨段的锚点；跨段另列，不偷偷进入下一段。原段标签全集另见sample-counts.json的all_anchor_labels。

{summary_table}

等式：原根=热身+就绪预测；就绪预测=涨+跌+平+未结算+隔离。验证边界各排除1个跨段目标；最终开发末锚点119预测保留，但其目标120属于测试，故不拟合。末尾149保持PENDING并保留概率。持平只不参加二分类计分，照常预测。

## 开发期选择与扩展验证

仅C=0.1和1.0两候选，两折等权平均BA均为60.8333%，依预定同分规则选择更强正则C=0.1。StandardScaler仅拟合每轮实际训练索引；未使用测试缩放、测试选参或测试选特征。阈值始终0.5；概率是未校准predict_proba，不能解释为已验证的发生频率。上一根方向基线用相邻有效收盘比较，上一根持平预先固定按涨。

{chr(10).join(cv_table)}

LR两折准确率69.23%、57.14%（波动12.09个百分点），BA63.89%、57.78%。第一折准确率与永远跌相同，第二折低于永远涨，严格胜过当折最强基线0/2折。两折仅27个可计分验证锚点，不能把折数或总数包装为大量独立试验。训练内指标单独放在[training-audit.md](training-audit.md)，不作为能力证据。

## 本轮一次历史留出

配置/特征/指标/门槛在preregistered.json固定；开发选参后保存模型和frozen.json，之后holdout-unlocked.json仅解锁一次。历史区间此前已经暴露，本实验只保证本轮参数选择未使用留出得分，**不称全新独立盲测**。后续复算属于审计，不重拟合、不改模型、不产生新独立测试资格。

{chr(10).join(comparison)}

混淆矩阵行是真实[跌,涨]、列是预测[跌,涨]。LR为[[13,3],[9,3]]。MCC=0.0754，AUC=0.5260，Brier=0.24469，LogLoss=0.68196；这些是未校准历史结果。三规则基线的0/1概率仅是规则输出，其概率评分会很差，不能据此宣称LR有方向优势。

每错/对1个测试样本，准确率约变3.57个百分点。LR Wilson95%描述区间39.07%—73.49%很宽，且它并未校正序列相关性。预登记的配对成块自助法block=5、2000次，仅约6个块，推断同样不稳定：

{chr(10).join(paired)}

所有相对差值区间均跨0，LR对永远跌的准确率差0，且验证优势0/2，不满足预登记门槛。不得根据本结果再改特征、C、切分或门槛后将同一历史称独立测试。未来数据增加后可另立研究，不为本实验的负结论调参补救。

## 逐根记录与模型

bar-ledger.csv覆盖150根，首5根WARMUP并明确不可预测；符合规则145个锚点×4模型=580条完整预测，含开发内、持平、跨边界、尾部待结算。另有两个扩展验证30锚点×4=120条、两候选共60条验证预测及训练内审查记录。每条有方向、p_up/p_down、来源时间、当时可用/逻辑预测时间、实际执行UTC、样本状态、版本；逻辑时间不冒充实际历史运行。所有signal标为OBSERVE_RESEARCH_ONLY；指标中的覆盖率1仅表示预测未筛选，并非实盘下单覆盖。

model.joblib保存最终冻结模型、特征顺序、配置、拟合位置、源哈希和版本，cv-fold*.joblib保存各候选折模型。只加载本项目可信模型；独立验证已确认重载概率一致及缩放器只使用111条开发样本。该研究模型未接入旧CLI，也未在留出后使用全历史再训练。

## 检查与限制

PASS：针对性9项测试（训练前后）、原项目26项回归（训练前后）、12组测试/CV指标独立复算、模型重载与缩放审查、冻结/一次解锁时序、旧项目及8CSV共5355个文件哈希前后不变。详见independent-verification.json、preservation.json、postflight-tests.txt、legacy-regression.txt及独立验收记录。没有覆盖原数据、旧模型、旧实验、旧报告或旧交付包。

FAIL：研究信号优势门槛。BLOCKED：本轮必需程序检查无阻塞项。未核实：代码/品种、平台真实性、时区、官方日历、计价/成交量单位。NOT_TESTED：未来未暴露前向数据、实时环境、实盘、概率校准。h=3/5/10、树模型、交易回测按本轮范围不运行。运行出现pandas旧日序属性弃用警告，尚无功能失败；保持冻结源码原样，未来环境升级时另行处理。
"""
    write(OUTPUT / "report.md", report)
    write(STUDY / "README.md", f"""# 日线小样本研究 v0.2

本次已训练h=1逻辑回归；结论：**未得到可靠预测信号**。

- [完整研究报告](runs/{result['run_id']}/report.md)
- [数据审计](runs/{result['run_id']}/data-audit.md)
- [新旧差异](baseline/change-request-v0.2.md)、[需求](baseline/requirements-v0.2.md)、[验收标准](baseline/acceptance-v0.2.md)
- [模型](runs/{result['run_id']}/model.joblib)、[逐根预测](runs/{result['run_id']}/predictions.csv)、[决策](decisions.md)
- [独立复算](runs/{result['run_id']}/independent-verification.json)、[验收记录](acceptance-record.md)

原始数据与旧实验原样保留。本目录中的旧v0.1需求/验收副本可核查，正式旧实验仍在../daily-v0.1-20261030。历史测试此前已暴露，不是全新盲测；原始概率未校准。

在项目根目录PowerShell中，只审查既有结果：

```powershell
.\\.venv\\Scripts\\python.exe -B -X utf8 research\\daily-v0.2-20261030\\verify.py research\\daily-v0.2-20261030\\runs\\{result['run_id']}
```

不要重复计分或覆盖已有run-id。需重新运行时必须新建run-id并登记目的；相同数据仅可称复现，不能创造新的独立测试证据。命令模板（替换为明确的新run-id）：

```powershell
.\\.venv\\Scripts\\python.exe -B -X utf8 research\\daily-v0.2-20261030\\test_daily.py
.\\.venv\\Scripts\\python.exe -B -X utf8 research\\daily-v0.2-20261030\\run.py --run-id NEW_UNIQUE_RUN_ID
```

model.joblib是可信本地研究包，包含estimator及f_前缀列顺序。需先使用run.features在按原规则确认完整的同源日线上计算特征；缺特征时不预测，不填值。不是通用实时接口，也未接入原系统旧模型加载路径。
""")
    evidence = "runs/" + result["run_id"] + "/"
    mapping = {"DAC-01": "source-audit.json, preservation.json", "DAC-02": "preflight-tests.txt, postflight-tests.txt, config.json",
               "DAC-03": "sample-counts.json, fit-indices.json, final-fit.json", "DAC-04": "selection.json, config.json, independent-verification.json",
               "DAC-05": "holdout-metrics.json, walk-forward.json, independent-verification.json", "DAC-06": "bar-ledger.csv, predictions.csv, cv-predictions.csv, independent-verification.json",
               "DAC-07": "preregistered.json, frozen.json, holdout-unlocked.json, independent-verification.json", "DAC-08": "postflight-tests.txt, legacy-regression.txt, independent-verification.json"}
    write(STUDY / "acceptance-record.md", "# 独立验收记录 v0.2\n\n执行者：本地AI自动检查；候选代码/需求/数据快照见preregistered.json，结果复算入口为verify.py，不重新拟合。未聘用第二个人工审查员。\n\n| 项 | 结果 | 证据（位于" + evidence + "） |\n|---|---|---|\n" + "\n".join(f"| {key} | PASS | {value} |" for key, value in mapping.items()) + "\n\n程序/记录要求8项通过；研究信号资格FAIL，不具备稳定预测、正式交易或实时交付资格。未核实元数据和NOT_TESTED前向/实时/实盘/校准不得按已验证处理。原始测试后模型与已登记标准未改动。\n")
    write(STUDY / "testing" / "test-execution.md", f"# 执行记录 TE-D02\n\n实际UTC时间见{evidence}execution.log及各JSON；本地任务日期2026-10-30，原生行情时间未擅自认定时区。Python及依赖见environment.json。\n\n1. `python -B -X utf8 test_daily.py`：训练前9/9，训练后9/9，exit 0；TC-D01..D09。\n2. `python -B -X utf8 -m unittest discover -s tests -v`：训练前后均26/26，exit 0；TC-D12。\n3. `python -B -X utf8 run.py --run-id {result['run_id']}`：exit 0；审计→预注册→两候选两折→最终拟合→冻结→一次历史计分→保全。执行路径均以项目根起始，实际日志位于run-id目录。\n4. `python -B -X utf8 verify.py {evidence}`：exit 0，12组指标/模型重载/配置数据代码模型哈希/5355文件保全通过；TC-D10..D12，无重拟合。\n\n弃用和人工异常夹具解析/单类指标警告均保留在原日志中，未改变预测或准入门槛。研究优势FAIL来自真实比较，不是程序崩溃。\n")
    write(STUDY / "testing" / "defects.md", "# 缺陷与限制台账\n\n本轮9项聚焦检查、26项旧回归及独立复算中未发现违反已登记程序验收要求的功能缺陷。研究优势门槛FAIL（LR未超最强基线）是真实研究结果，不是需通过改测试修复的软件缺陷。\n\nLIMIT-D01：样本很少、已暴露历史、原始概率未校准、外部元数据未核实、前向/实时/实盘未测。全部在基线与报告披露，不转为已通过。\nWARN-D01：pandas dayofweek弃用提示；当前环境仍执行正确。为保持已冻结代码不在测试后修改；环境升级另行立项并回归。\n")
    write(STUDY / "testing" / "traceability.md", "# 需求追踪矩阵\n\n| 需求 | 验收 | 用例 | 证据 |\n|---|---|---|---|\n| DFR-01,09 | DAC-01 | TC-D12 | source-audit/preservation/legacy-before |\n| DFR-02 | DAC-02 | TC-D01..03 | preflight/postflight-tests |\n| DFR-03,04 | DAC-03 | TC-D04..07 | fit-indices/sample-counts/walk-forward |\n| DFR-04,05 | DAC-04 | TC-D05,06,11 | selection/independent-verification |\n| DFR-06 | DAC-05 | TC-D08,10 | holdout-metrics/walk-forward/uncertainty |\n| DFR-07 | DAC-06 | TC-D10 | bar-ledger/predictions/cv-predictions |\n| DFR-08,09 | DAC-07 | TC-D09,11 | preregistered/frozen/holdout-unlocked |\n| DFR-06,09 | DAC-08 | TC-D01..12 | logs/independent-verification/acceptance-record |\n\n具体文件均在当前run-id目录；软件检查与信号资格独立。\n")
    write(STUDY / "testing" / "test-summary.md", "# 测试总结 TS-D02\n\nPASS：9项针对性单元检查、26项既有回归，训练前后均通过；独立复算12组测试/CV指标、模型重载、训练缩放、冻结时序、完整覆盖、5355个旧文件前后哈希不变。\n\nFAIL：研究信号优势门槛。BLOCKED：本轮必需程序测试0项。NOT_TESTED：前向/实时/实盘/概率校准；h>1和新树模型为本轮明确不适用。来源代码/时区/日历/单位未核实。程序验收通过只说明本轮研究按规则执行，不构成预测能力或交易资格通过。\n")
    write(STUDY / "phase-report.md", f"# 本轮阶段记录\n\n| 阶段 | 产物/检查 | 实际结果 |\n|---|---|---|\n| 需求变更 | baseline三份v0.2文档、保留v0.1副本、decisions | 依据本轮明确用户变更和既有推荐代选授权先保存，再实现 |\n| 数据/特征 | source-audit、四短特征、真实热身5 | 审计150根，通过研究结构/可用性门禁，4日价差保留 |\n| 训练/验证 | 两C×两折、最终111条拟合 | 足量，选择C=.1，原80/10门槛保留 |\n| 冻结/历史计分 | model、frozen、一次unlock、逐根预测 | 28条二分类，16命中，研究优势FAIL |\n| 测试/审查 | 9+26检查、独立复算、5355文件保全 | 程序标准8项PASS；能力仍无可靠信号 |\n\n新增文件只在本实验目录，未改原始CSV、旧src/config/models/reports或旧v0.1。执行命令与退出码见testing/test-execution.md及{evidence}。当前可供审查的离线研究产物已完成；无真实交易或实时发布动作。下一步若需研究优势，只能在新增未暴露数据上另行冻结前向实验，未在本轮擅自执行。\n")
    with (STUDY / "AI_CHANGELOG.md").open("a", encoding="utf-8") as stream:
        stream.write(f"\n本轮run-id={result['run_id']}：新增run.py/test_daily.py/verify.py；generate_report.py仅从冻结结果生成报告。保存最终及4个折候选模型、580完整预测、120滚动验证、60候选预测、原始执行/测试/独立复算日志；七类测试资料、验收记录、README、阶段记录与结果报告独立保存。最终111条拟合、28条留出计分，研究优势FAIL；旧5355文件哈希不变。所有新产物摘要哈希见run-id/artifact-manifest.json。\n")
    files = {str(p.relative_to(STUDY)): run.sha256(p) for p in STUDY.rglob("*") if p.is_file() and p.name != "artifact-manifest.json"}
    run.write_json(OUTPUT / "artifact-manifest.json", {"created_at_utc": run.now(), "scope": "all new experiment files; manifest excludes itself", "sha256": files})
    print(json.dumps({"report": str(OUTPUT / "report.md"), "files_hashed": len(files), "result": result["conclusion"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
