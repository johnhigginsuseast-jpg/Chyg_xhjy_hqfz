import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier, early_stopping
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from xgboost import XGBClassifier

from .common import ROOT, load_config, period_name, sha256, source_file, write_json
from .evaluate import metrics, select_threshold
from .features import make_features
from .labels import filter_bars, make_labels
from .predict import baseline_probability, model_probability
from .validation import assert_purged, boundaries, samples_for, walk_forward_windows, window

BASELINES = ["always_up", "always_down", "previous_direction", "momentum"]
CANDIDATES = {"logistic": [{"C": .1}, {"C": 1.}],
              "lightgbm": [{"max_depth": 2, "num_leaves": 4}, {"max_depth": 3, "num_leaves": 8}],
              "xgboost": [{"max_depth": 2}, {"max_depth": 3}],
              "catboost": [{"depth": 2}, {"depth": 3}]}


def prepared(config, period):
    audit = json.loads((ROOT / "reports/evidence/stage1/audit.json").read_text(encoding="utf-8"))
    if not audit["research_training_allowed"]:
        raise ValueError("审计未通过，不允许训练")
    source = source_file(config, period)
    expected = next(r["sha256"] for r in audit["files"] if r["period"] == period)
    if sha256(source) != expected:
        raise ValueError("源文件已变更，请先重新审计")
    raw = pd.read_parquet(ROOT / f"data/cleaned/{period_name(period)}.parquet")
    kept, ledger, state = filter_bars(raw, period)
    return raw, kept, make_features(kept), ledger, state


def estimator(kind, params, config, rounds=100, stopping=False):
    common = dict(random_state=config["seed"])
    if kind == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(**params, **common, max_iter=500))
    if kind == "lightgbm":
        return LGBMClassifier(**params, **common, n_estimators=rounds, learning_rate=.05, min_child_samples=40,
                              reg_lambda=5, reg_alpha=.1, n_jobs=config["threads"], verbosity=-1,
                              deterministic=True, force_col_wise=True)
    if kind == "xgboost":
        return XGBClassifier(**params, **common, n_estimators=rounds, learning_rate=.05, min_child_weight=20,
                             reg_lambda=5, subsample=1., colsample_bytree=1., n_jobs=config["threads"],
                             tree_method="hist", eval_metric="logloss", early_stopping_rounds=12 if stopping else None)
    return CatBoostClassifier(**params, random_seed=config["seed"], iterations=rounds, learning_rate=.05,
                              l2_leaf_reg=10, thread_count=config["threads"], verbose=False,
                              allow_writing_files=False, loss_function="Logloss")


def fit_model(kind, params, training, feature_cols, config):
    if len(training) < config["min_fit_samples"] or training.y.nunique() < 2:
        raise ValueError("INSUFFICIENT_DATA: 拟合样本不足或单类")
    rounds, inner_info = 100, None
    if kind != "logistic":
        cut = training.iloc[int(len(training) * .8)].available_at
        core = training.loc[training.target_available_at.lt(cut)]
        stop = training.loc[training.available_at.ge(cut)]
        if len(core) >= 30 and len(stop) >= 10 and core.y.nunique() == 2 and stop.y.nunique() == 2:
            assert_purged(core, cut)
            probe = estimator(kind, params, config, stopping=True)
            extra = {"eval_set": [(stop[feature_cols], stop.y.astype(int))]}
            if kind == "lightgbm": extra = {"eval_X": stop[feature_cols], "eval_y": stop.y.astype(int), "callbacks": [early_stopping(12, verbose=False)]}
            elif kind == "xgboost": extra["verbose"] = False
            else: extra.update(early_stopping_rounds=12, use_best_model=True)
            probe.fit(core[feature_cols], core.y.astype(int), **extra)
            best = probe.best_iteration_ if kind == "lightgbm" else probe.best_iteration if kind == "xgboost" else probe.get_best_iteration()
            rounds = max(1, int(best) + (kind != "lightgbm"))
            inner_info = {"core_n": len(core), "stop_n": len(stop), "boundary": str(cut),
                          "core_max_target": str(core.target_available_at.max()), "best_rounds": rounds}
    model = estimator(kind, params, config, rounds)
    model.fit(training[feature_cols], training.y.astype(int))
    return model, {"kind": kind, "params": params, "rounds": rounds, "fit_n": len(training),
                   "fit_max_position": int(training.bar_position.max()), "fit_max_target": str(training.target_available_at.max()),
                   "inner_early_stop": inner_info}


def run_training(config, run_id):
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
        raise ValueError("run-id只允许字母、数字、横线、下划线")
    run = ROOT / "reports/evidence" / run_id
    run.mkdir(parents=True, exist_ok=False)
    models = ROOT / "models" / run_id
    models.mkdir(parents=True, exist_ok=False)
    write_json(run / "config.json", config)
    write_json(run / "candidate-grid.json", CANDIDATES)
    decisions, rolling, distributions, features_info, fits = [], [], [], [], []
    with threadpool_limits(limits=config["threads"]):
        for period in config["periods"]:
            raw, kept, features, ledger, state = prepared(config, period)
            b = boundaries(raw)
            ledger.to_csv(run / f"{period_name(period)}-coverage.csv", index=False)
            feature_cols = ["f_" + c for c in features.columns]
            features_info.append({"period": period, "raw_bars": len(raw), "retained": len(kept),
                                  "rule_skip": int(ledger.status.eq("rule_skip").sum()), "columns": list(features.columns), "boundaries": b})
            for horizon in config["horizons"]:
                print(f"TRAIN {period_name(period)} h={horizon}", flush=True)
                labels = make_labels(kept, horizon, raw.available_at.iloc[b["test_start"]])
                samples = samples_for(kept, features, labels, config["warmup"])
                training = window(samples, 0, b["train_end"], raw.available_at.iloc[b["train_end"]])
                calibration = window(samples, b["train_end"], b["calibration_end"], raw.available_at.iloc[b["calibration_end"]])
                threshold_data = window(samples, b["calibration_end"], b["test_start"], raw.available_at.iloc[b["test_start"]])
                for name, subset in (("train", training), ("calibration", calibration), ("threshold", threshold_data)):
                    distributions.append({"period": period, "horizon": horizon, "subset": name, "n": len(subset),
                                          "up": int(subset.y.eq(1).sum()), "down": int(subset.y.eq(0).sum()),
                                          "flat_total_pretest": int(samples.label_status.eq("FLAT").sum()), "test_labels": "LOCKED"})
                for name in BASELINES:
                    val = metrics(threshold_data.y, baseline_probability(threshold_data, name))
                    decisions.append({"period": period, "horizon": horizon, "model": name, "status": "OK",
                                      "threshold": .5, "validation": val, "probability_status": "deterministic_uncalibrated_baseline"})
                    for fold, (start, end) in enumerate(walk_forward_windows(b["train_end"], config["walk_forward_folds"])):
                        held = window(samples, start, end, raw.available_at.iloc[end])
                        score = metrics(held.y, baseline_probability(held, name))
                        rolling.append(dict(period=period, horizon=horizon, model=name, candidate=0, fold=fold,
                                            start=start, end=end, n=len(held), accuracy=score.get("accuracy"), balanced_accuracy=score.get("balanced_accuracy")))
                for kind, candidates in CANDIDATES.items():
                    if (len(training) < config["min_fit_samples"] or len(calibration) < config["min_calibration_samples"] or
                        len(threshold_data) < 10 or min(training.y.nunique(), calibration.y.nunique(), threshold_data.y.nunique()) < 2):
                        decisions.append({"period": period, "horizon": horizon, "model": kind, "status": "INSUFFICIENT_DATA",
                                          "reason": "fixed fit/calibration/threshold minimum or both-class requirement",
                                          "n_train": len(training), "n_calibration": len(calibration), "n_threshold": len(threshold_data)})
                        continue
                    candidate_scores = []
                    for ci, params in enumerate(candidates):
                        scores = []
                        for fold, (start, end) in enumerate(walk_forward_windows(b["train_end"], config["walk_forward_folds"])):
                            train_fold = window(samples, 0, start, raw.available_at.iloc[start])
                            held = window(samples, start, end, raw.available_at.iloc[end])
                            if len(train_fold) < config["min_fit_samples"] or train_fold.y.nunique() < 2 or not len(held):
                                raise ValueError(f"预登记滚动窗口样本不足: {period} {horizon} {fold}")
                            assert_purged(train_fold, raw.available_at.iloc[start])
                            model, fit_info = fit_model(kind, params, train_fold, feature_cols, config)
                            fits.append(dict(period=period, horizon=horizon, candidate=ci, fold=fold, **fit_info))
                            p = model.predict_proba(held[feature_cols])[:, 1]
                            score = metrics(held.y, p)
                            scores.append(score["accuracy"])
                            rolling.append(dict(period=period, horizon=horizon, model=kind, candidate=ci, fold=fold,
                                                start=start, end=end, n=len(held), accuracy=score["accuracy"], balanced_accuracy=score["balanced_accuracy"]))
                        candidate_scores.append(float(np.mean(scores)))
                    chosen = int(np.argmax(candidate_scores))
                    model, fit_info = fit_model(kind, candidates[chosen], training, feature_cols, config)
                    fits.append(dict(period=period, horizon=horizon, candidate=chosen, fold="final_train", **fit_info))
                    bundle = {"estimator": model, "calibrator": None, "period": period, "horizon": horizon,
                              "feature_columns": feature_cols, "warmup": config["warmup"], "threshold": .5,
                              "model_version": f"{run_id}-{period_name(period)}-h{horizon}-{kind}",
                              "source_identity": config["source_identity"], "research_only": True,
                              "training_rule_state": filter_bars(raw.loc[raw.bar_position.lt(b["train_end"])], period)[2]}
                    p_cal = model_probability(bundle, calibration, calibrated=False)
                    logits = np.log(np.clip(p_cal, 1e-6, 1 - 1e-6) / np.clip(1 - p_cal, 1e-6, 1))
                    bundle["calibrator"] = LogisticRegression(C=1., random_state=config["seed"], max_iter=500).fit(logits.reshape(-1, 1), calibration.y.astype(int))
                    p_val = model_probability(bundle, threshold_data)
                    bundle["threshold"] = select_threshold(threshold_data.y, p_val, config)
                    path = models / f"{period_name(period)}-h{horizon}-{kind}.joblib"
                    temporary = path.with_suffix(".tmp")
                    joblib.dump(bundle, temporary)
                    temporary.replace(path)
                    write_json(path.with_suffix(".json"), {"sha256": sha256(path), "source_identity": config["source_identity"], "model_version": bundle["model_version"]})
                    decisions.append({"period": period, "horizon": horizon, "model": kind, "status": "OK",
                                      "candidate": chosen, "params": candidates[chosen], "walk_mean_accuracy": candidate_scores[chosen],
                                      "threshold": bundle["threshold"], "model_path": str(path.relative_to(ROOT)), "model_sha256": sha256(path),
                                      "validation": metrics(threshold_data.y, p_val, bundle["threshold"]),
                                      "raw_validation": metrics(threshold_data.y, model_probability(bundle, threshold_data, False))})
                    print(f"  {kind}: candidate={chosen} val_n={len(threshold_data)} threshold={bundle['threshold']}", flush=True)
                write_json(run / "decisions.json", decisions)
                write_json(run / "fit-index-audit.json", fits)
                pd.DataFrame(rolling).to_csv(run / "walk-forward.csv", index=False)
                pd.DataFrame(distributions).to_csv(run / "pretest-label-distribution.csv", index=False)
    write_json(run / "feature-info.json", features_info)
    source_hashes = {p.name: sha256(p) for p in Path(config["data_path"]).glob("*.csv")}
    code_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in (ROOT / "src").glob("*.py")}
    champions = []
    for period in config["periods"]:
        for h in config["horizons"]:
            available = [d for d in decisions if d["period"] == period and d["horizon"] == h and d["model"] in CANDIDATES and d["status"] == "OK"]
            if available:
                chosen = max(available, key=lambda d: d["validation"]["accuracy"])
                champions.append({"period": period, "horizon": h, "model": chosen["model"]})
    write_json(run / "frozen.json", {"status": "FROZEN", "run_id": run_id, "config_hash": sha256(run / "config.json"),
                                    "source_hashes": source_hashes, "code_hashes": code_hashes, "champions": champions,
                                    "candidate_grid_hash": sha256(run / "candidate-grid.json"), "decisions_hash": sha256(run / "decisions.json"),
                                    "test_status": "LOCKED", "prior_exposure": "cannot_rule_out; retrospective_holdout_only"})
    print(f"FROZEN {run_id}; final test labels have not been scored", flush=True)


def main():
    parser = argparse.ArgumentParser(description="训练/滚动验证/校准/阈值选择，最后冻结；不评估测试")
    parser.add_argument("--config")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    run_training(load_config(args.config), args.run_id)


if __name__ == "__main__":
    main()
