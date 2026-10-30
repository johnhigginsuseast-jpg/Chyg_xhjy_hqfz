import json
import os
from pathlib import Path

from .common import ROOT, period_name, sha256, write_json

os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "reports/.mplcache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve

from .evaluate import metrics
from .labels import make_labels
from .predict import baseline_probability, load_bundle, model_probability
from .validation import boundaries, samples_for, window


def prediction_frame(test, probability, raw_probability, threshold, horizon, version):
    p = np.asarray(probability, dtype=np.float64)
    raw_p = np.asarray(raw_probability, dtype=np.float64)
    prediction = test[["available_at", "source_timestamp", "open_at", "open", "close", "bar_position", "raw_positions",
                       "target_available_at", "target_position", "y", "ret", "label_status", "market_state"]].copy()
    prediction = prediction.rename(columns={"available_at": "prediction_timestamp"})
    prediction["p_up"] = p
    prediction["p_down"] = 1 - p
    prediction["raw_p_up"] = raw_p
    prediction["predicted_direction"] = np.where(p >= .5, "up", "down")
    prediction["confidence"] = np.maximum(p, 1 - p)
    prediction["signal"] = np.where(prediction.confidence >= threshold, prediction.predicted_direction, "wait")
    prediction["prediction_horizon"] = horizon
    prediction["model_version"] = version
    prediction["threshold"] = threshold
    return prediction


def paired_block_comparison(y, model, baseline, timestamps, config):
    diff = (np.asarray(model) >= .5).astype(int) == np.asarray(y)
    diff = diff.astype(float) - ((np.asarray(baseline) >= .5).astype(int) == np.asarray(y))
    time = pd.to_datetime(timestamps)
    day = time.dt.normalize() + pd.to_timedelta(time.dt.hour.ge(19).astype(int), unit="D")
    daily = pd.DataFrame({"day": day.to_numpy(), "d": diff}).groupby("day").d.agg(["sum", "count"])
    result = {"accuracy_difference": float(diff.mean()), "observed_days": len(daily), "ci_low": None, "ci_high": None, "p_exploratory": 1.}
    if len(daily) < 10:
        result["note"] = "too_few_days_for_block_interval"
        return result
    rng = np.random.default_rng(config["seed"])
    size = len(daily)
    block = min(config["bootstrap_block_days"], size)
    starts = rng.integers(0, size, size=(config["bootstrap_repeats"], int(np.ceil(size / block))))
    indices = ((starts[:, :, None] + np.arange(block)) % size).reshape(config["bootstrap_repeats"], -1)[:, :size]
    values = daily["sum"].to_numpy()[indices].sum(axis=1) / daily["count"].to_numpy()[indices].sum(axis=1)
    result.update(ci_low=float(np.quantile(values, .025)), ci_high=float(np.quantile(values, .975)),
                  p_exploratory=float((np.sum(values <= 0) + 1) / (len(values) + 1)),
                  note="paired circular 5-observed-day block bootstrap; exploratory one-sided tail probability")
    return result


def diagnostic_figure(predictions, selected, destination):
    selected_data = predictions[selected]
    scored = selected_data[selected_data.y.notna()]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for name, data in predictions.items():
        good = data[data.y.notna()]
        if not len(good): continue
        correct = good.predicted_direction.eq(np.where(good.y.eq(1), "up", "down"))
        axes[0, 0].plot(pd.to_datetime(good.prediction_timestamp), correct.expanding().mean(), label=name, alpha=.75)
        if name in ("logistic", "lightgbm", "xgboost", "catboost") and good.y.nunique() == 2:
            actual, mean = calibration_curve(good.y, good.p_up, n_bins=8, strategy="quantile")
            axes[0, 1].plot(mean, actual, marker="o", label=name)
    axes[0, 0].set(title="Cumulative full-coverage direction accuracy", ylim=(0, 1))
    locator = mdates.AutoDateLocator(minticks=3, maxticks=5)
    axes[0, 0].xaxis.set_major_locator(locator)
    axes[0, 0].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    axes[0, 0].legend(fontsize=6, ncol=2)
    axes[0, 1].plot([0, 1], [0, 1], "k--", alpha=.5)
    axes[0, 1].set(title="Reliability: learned models", xlabel="Mean predicted p_up", ylabel="Observed up rate")
    axes[0, 1].legend(fontsize=7)
    if len(scored):
        correct = scored.predicted_direction.eq(np.where(scored.y.eq(1), "up", "down"))
        axes[1, 0].hist([scored.loc[correct, "confidence"], scored.loc[~correct, "confidence"]], bins=10, label=["Correct", "Wrong"], alpha=.65)
        axes[1, 0].set(title=f"Validation-selected {selected}: confidence", xlabel="Confidence", ylabel="Predictions")
        axes[1, 0].legend()
        table = pd.crosstab(scored.market_state, correct).reindex(columns=[False, True], fill_value=0)
        table.columns = ["Wrong", "Correct"]
        table.plot.bar(stacked=True, ax=axes[1, 1], color=["#e17865", "#49a89b"])
        axes[1, 1].set(title="Correct / wrong by training-defined market state", xlabel="State", ylabel="Count")
        axes[1, 1].tick_params(axis="x", rotation=20)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=120)
    plt.close(fig)


def verify_freeze(run):
    frozen = json.loads((run / "frozen.json").read_text(encoding="utf-8"))
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    if frozen["status"] != "FROZEN" or sha256(run / "config.json") != frozen["config_hash"]:
        raise ValueError("实验配置未冻结或已经改变")
    for name, digest in frozen["code_hashes"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError(f"冻结后源码已变更: {name}")
    for name, digest in frozen["source_hashes"].items():
        if sha256(Path(config["data_path"]) / name) != digest:
            raise ValueError(f"冻结后源数据已变更: {name}")
    for name, key in (("candidate-grid.json", "candidate_grid_hash"), ("decisions.json", "decisions_hash")):
        if sha256(run / name) != frozen[key]: raise ValueError(f"冻结清单变化: {name}")
    return frozen, config


def evaluate_frozen(run_id):
    from .train import BASELINES, CANDIDATES, prepared
    run = ROOT / "reports/evidence" / run_id
    frozen, config = verify_freeze(run)
    marker = run / "final-test-started.json"
    with marker.open("x", encoding="utf-8") as handle:
        json.dump({"status": "UNLOCKED", "purpose": "single frozen historical evaluation", "model_changes_allowed": False}, handle)
    decisions = json.loads((run / "decisions.json").read_text(encoding="utf-8"))
    rows, counts, contrasts, diagnostics, prediction_paths = [], [], [], [], []
    pred_dir = run / "predictions"
    pred_dir.mkdir()
    for period in config["periods"]:
        raw, kept, features, ledger, _ = prepared(config, period)
        b = boundaries(raw)
        for horizon in config["horizons"]:
            labels = make_labels(kept, horizon)
            samples = samples_for(kept, features, labels, config["warmup"])
            test = samples.loc[samples.bar_position.ge(b["test_start"])].copy()
            if not test.feature_ready.all():
                raise ValueError("最终测试存在未预测有效根，不能降低覆盖率")
            training = window(samples, 0, b["train_end"], raw.available_at.iloc[b["train_end"]])
            volatility_cut = float(training.f_volatility.median()) if len(training) else 0
            trend_cut = float(training.f_trend_strength.median()) if len(training) else 0
            test["market_state"] = np.where(test.f_volatility > volatility_cut, "high_vol", "low_vol") + np.where(test.f_trend_strength > trend_cut, "/trend", "/range")
            for split, start, end in (("train", 0, b["train_end"]), ("validation", b["train_end"], b["test_start"]), ("test", b["test_start"], b["end"])):
                subset = samples.loc[samples.bar_position.ge(start) & samples.bar_position.lt(end) & samples.feature_ready]
                cutoff = raw.available_at.iloc[end] if end < len(raw) else pd.Timestamp.max
                purged = subset.target_available_at.ge(cutoff)
                valid = subset.loc[~purged]
                counts.append({"period": period, "horizon": horizon, "split": split, "eligible": len(subset),
                               "up": int(valid.label_status.eq("UP").sum()), "down": int(valid.label_status.eq("DOWN").sum()),
                               "flat": int(valid.label_status.eq("FLAT").sum()), "pending": int(valid.label_status.eq("PENDING").sum()),
                               "purged": int(purged.sum())})
                known = sum(counts[-1][key] for key in ("up", "down", "flat"))
                counts[-1]["known_label_count"] = known
                for key in ("up", "down", "flat"):
                    counts[-1][key + "_fraction"] = counts[-1][key] / known if known else None
            predictions = {}
            case = [d for d in decisions if d["period"] == period and d["horizon"] == horizon]
            for decision in case:
                name = decision["model"]
                if decision["status"] != "OK":
                    rows.append({"period": period, "horizon": horizon, "model": name, "status": decision["status"],
                                 "reason": decision["reason"], "n": 0, "eligible_forecasts": len(test), "predicted_count": 0})
                    continue
                if name in BASELINES:
                    p = baseline_probability(test, name)
                    raw_p = p
                    train_score = metrics(training.y, baseline_probability(training, name))
                else:
                    bundle = load_bundle(ROOT / decision["model_path"])
                    if sha256(ROOT / decision["model_path"]) != decision["model_sha256"]:
                        raise ValueError("模型与冻结决策不一致")
                    p = model_probability(bundle, test)
                    raw_p = model_probability(bundle, test, False)
                    train_score = metrics(training.y, model_probability(bundle, training))
                prediction = prediction_frame(test, p, raw_p, decision["threshold"], horizon,
                                              f"{run_id}-{period_name(period)}-h{horizon}-{name}")
                path = pred_dir / f"{period_name(period)}-h{horizon}-{name}.csv"
                prediction.to_csv(path, index=False)
                prediction_paths.append(str(path.relative_to(ROOT)))
                predictions[name] = prediction
                scored = prediction.y.notna()
                score = metrics(prediction.loc[scored, "y"], prediction.loc[scored, "p_up"], decision["threshold"])
                raw_score = metrics(prediction.loc[scored, "y"], prediction.loc[scored, "raw_p_up"])
                rows.append(dict(period=period, horizon=horizon, model=name, threshold=decision["threshold"],
                                 eligible_forecasts=len(test), predicted_count=len(prediction), forecast_coverage=1.,
                                 signal_coverage_all_forecasts=float(prediction.signal.ne("wait").mean()),
                                 signal_count_all_forecasts=int(prediction.signal.ne("wait").sum()),
                                 predicted_up_rate=float(prediction.loc[scored, "predicted_direction"].eq("up").mean()),
                                 observed_up_rate=float(prediction.loc[scored, "y"].mean()),
                                 flat_count=int(prediction.label_status.eq("FLAT").sum()), pending_count=int(prediction.label_status.eq("PENDING").sum()),
                                 validation_accuracy=decision["validation"].get("accuracy"), training_accuracy=train_score.get("accuracy"),
                                 raw_brier=raw_score.get("brier"), raw_log_loss=raw_score.get("log_loss"),
                                 probability_status="sigmoid_calibrated" if name not in BASELINES else "deterministic_uncalibrated_baseline", **score))
                for state, group in prediction.loc[scored].groupby("market_state"):
                    diagnostics.append(dict(period=period, horizon=horizon, model=name, state=state, **metrics(group.y, group.p_up, decision["threshold"])))
            champion = next((r for r in frozen["champions"] if r["period"] == period and r["horizon"] == horizon), None)
            if champion:
                selected = champion["model"]
                base = max((d for d in case if d["model"] in BASELINES), key=lambda d: d["validation"].get("accuracy", -1))["model"]
                scored = predictions[selected].y.notna()
                contrast = paired_block_comparison(predictions[selected].loc[scored, "y"], predictions[selected].loc[scored, "p_up"],
                                                   predictions[base].loc[scored, "p_up"], predictions[selected].loc[scored, "prediction_timestamp"], config)
                contrasts.append(dict(period=period, horizon=horizon, selected_model=selected, validation_selected_baseline=base,
                                      stable_signal_verified=False, **contrast))
                diagnostic_figure(predictions, selected, ROOT / f"reports/figures/{period_name(period)}-h{horizon}.png")
            print(f"FINAL {period_name(period)} h={horizon}: {len(test)} eligible forecasts/model", flush=True)
    order = sorted(range(len(contrasts)), key=lambda i: contrasts[i]["p_exploratory"])
    previous = 0.
    for rank, i in enumerate(order):
        previous = max(previous, min(1., (len(config["periods"]) * len(config["horizons"]) - rank) * contrasts[i]["p_exploratory"]))
        contrasts[i]["holm_adjusted_exploratory_p"] = previous
    comparison = pd.DataFrame(rows)
    comparison.to_csv(ROOT / "reports/model_comparison.csv", index=False)
    pd.DataFrame(counts).to_csv(ROOT / "reports/label_distribution.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(ROOT / "reports/market_state_diagnostics.csv", index=False)
    write_json(run / "final-contrasts.json", contrasts)
    write_json(run / "prediction-files.json", prediction_paths)
    write_json(run / "final-metrics.json", rows)
    lines = ["# 最终历史留出评估", "", f"实验：{run_id}；模型、参数、特征、阈值均在解锁前冻结。",
             "本次为70/15/15的末15%历史留出。此前其他研究可能已查看重叠行情，不能称全新盲测或实时预测能力。",
             "当前数据未验证出稳定可用的预测信号。工程实现与科研有效性分别验收。", "",
             "| 周期 | h有效根 | 验证选中模型 | 测试全覆盖准确率 | 计分数 | 二分类信号覆盖率 | 基线 | 准确率差95%区间 |",
             "|---|---:|---|---:|---:|---:|---|---|"]
    for c in contrasts:
        r = next(r for r in rows if r["period"] == c["period"] and r["horizon"] == c["horizon"] and r["model"] == c["selected_model"])
        interval = "不足以估计" if c["ci_low"] is None else f"[{c['ci_low']:.4f}, {c['ci_high']:.4f}]"
        lines.append(f"| {period_name(c['period'])} | {c['horizon']} | {c['selected_model']} | {r['accuracy']:.4f} | {r['n']} | {r['signal_coverage']:.4f} | {c['validation_selected_baseline']} | {interval} |")
    lines += ["", "## 覆盖、概率与局限", "", "每个已训练模型对测试有效完整根全量输出，平盘和尾部未结算仍保留概率；二分类分母单独排除平盘/未知。",
              "三连规则跳过和开盘事件均有来源账目。观望只影响行动，不能删方向预测。",
              "四个规则基线是确定性规则，其0/1概率未经校准；四个学习模型使用独立校准段的sigmoid，报告raw/calibrated评分与曲线。",
              "日线仅150根，学习模型若不满足预登记拟合/校准门槛，保留INSUFFICIENT_DATA；不得视作模型效果通过。",
              "训练准确率只用于诊断过拟合；表中模型选择来自验证，未按测试选择周期/跨度。各方向P/R、MCC、F1、AUC、概率评分、全覆盖及信号覆盖在model_comparison.csv中。",
              "市场状态阈值来自训练段中位数，详细正确/错误及状态分布见figures/和market_state_diagnostics.csv。",
              "置信区间按观察交易日成块；多组合探索性尾概率做Holm调整，不把它当未暴露测试的正式显著性认证。",
              "全新数据、真实实时交付、交易可执行性与真实平台成本均未验证。"]
    learned = comparison[comparison.model.isin(CANDIDATES) & comparison.status.eq("OK")]
    if len(learned):
        gaps = learned.training_accuracy - learned.validation_accuracy
        deterioration = learned.brier.gt(learned.raw_brier)
        bias = (learned.predicted_up_rate - learned.observed_up_rate).abs()
        lines += ["", "## 模型诊断", "",
                  f"过拟合：{int(gaps.gt(.1).sum())}/{len(learned)}个学习模型组合的训练准确率高于验证超过10个百分点；最大差{gaps.max():.4f}。训练分数只用于诊断。",
                  f"概率失真：校准后Brier比原始概率更差的组合为{int(deterioration.sum())}/{len(learned)}；校准不保证改善，原始与校准评分均保留。",
                  f"类别偏置：预测上涨比例与真实上涨比例的最大绝对差为{bias.max():.4f}；双向P/R和Balanced Accuracy在对比表，不能只看总体准确率。",
                  "状态稳定性：market_state_diagnostics.csv逐状态提供样本量、准确率、MCC和概率评分；样本少/单类不构成稳定性证据。",
                  "与基线：每个跨度的对照基线事先由验证选择，成块区间与多比较结果在final-contrasts.json；既往暴露尚未排除，任何单段优势仅是回顾性研究。"]
    (ROOT / "reports/final_test_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rolling = pd.read_csv(run / "walk-forward.csv")
    report = ["# Walk-forward Validation", "", "仅在最初70%内做5轮扩展窗口；每类两组候选，按平均全覆盖准确率选参数，平局取先登记的简单候选。",
              "树模型早停使用每轮训练内部末20%时间段，先purge，再用选定迭代数重拟合该轮训练，不使用外层评估窗口早停。",
              "逐折区间、样本量、准确率和Balanced Accuracy见本实验walk-forward.csv，包含每个候选，未隐藏失败窗口。", "",
              "| 周期 | h | 模型 | 选中候选 | 折数 | 平均准确率 | 标准差 | 最差 | 最好 |", "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for d in decisions:
        if d["status"] != "OK": continue
        sub = rolling[(rolling.period == d["period"]) & (rolling.horizon == d["horizon"]) & (rolling.model == d["model"]) & (rolling.candidate == d.get("candidate", 0))]
        if len(sub):
            report.append(f"| {period_name(d['period'])} | {d['horizon']} | {d['model']} | {d.get('candidate',0)} | {len(sub)} | {sub.accuracy.mean():.4f} | {sub.accuracy.std(ddof=0):.4f} | {sub.accuracy.min():.4f} | {sub.accuracy.max():.4f} |")
    (ROOT / "reports/walk_forward_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    feature_info = json.loads((run / "feature-info.json").read_text(encoding="utf-8"))
    (ROOT / "reports/feature_report.md").write_text("# 特征报告\n\n所有特征仅来自当时已完成且按规则接纳的K线；固定前64个有效根热身，不按准确率选择删行。\n\n特征：\n\n" + "\n".join(f"- {name}" for name in feature_info[0]["columns"]) + "\n\n日收益来自接纳序列的交易日末收盘，最早16:00可用；未知日收益为0并附known指示，不填充价格。小时/星期特征禁用。\nLogistic缩放仅拟合训练；滚动波动率分位只用历史窗口。\n", encoding="utf-8")
    fits = json.loads((run / "fit-index-audit.json").read_text(encoding="utf-8"))
    (ROOT / "reports/leakage_audit.md").write_text(f"# 泄漏审计\n\n冻结实验：{run_id}。共{len(fits)}条拟合索引摘要，见fit-index-audit.json。\n\n- 外层按原始完整K线时间切70/15/15，过滤不改变时间边界。\n- 每次拟合目标结束时间严格早于后续窗口；不能用h个原始行替代实际有效根目标。\n- 特征前缀/未来扰动、跳过内容隔离与重放状态有自动化测试。\n- 概率校准与阈值分为互不重叠的验证时间角色，边界均purge；不做默认随机CV。\n- 最终标签在frozen.json之后由唯一解锁标记打开，没有根据测试再调模型。\n- 新增回测代码不得改变本次冻结模型和选择；所有预测保留平盘/未结算及观望。\n\n既往历史暴露未排除，因此本报告不证明全新盲测资格。\n", encoding="utf-8")
    write_json(run / "final-test-completed.json", {"status": "COMPLETED", "comparison_rows": len(rows),
                                                 "successful_model_cases": int(comparison.status.eq("OK").sum()),
                                                 "insufficient_model_cases": int(comparison.status.eq("INSUFFICIENT_DATA").sum()),
                                                 "stable_signal_verified": False, "research_only": True})
    print(f"FINAL COMPLETE: {len(rows)} model/period/horizon cases", flush=True)
