"""Isolated, preregistered daily h=1 research; leaves the existing project intact."""
import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

STUDY = Path(__file__).resolve().parent
PROJECT = STUDY.parents[1]
sys.path.insert(0, str(PROJECT))

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from src.common import load_config, sha256, source_file, write_json
from src.data_loader import canonicalize, load_data
from src.evaluate import metrics
from src.labels import make_labels
from src.train import fit_model
from src.validation import assert_purged, samples_for, window

BASELINES = ["always_up", "always_down", "previous_direction"]
FEATURES = ["return_1", "return_3", "sma5_distance", "volatility5"]
SEED = 20261028


def now():
    return datetime.now(timezone.utc).isoformat()


def protected_files():
    result = {}
    for current, dirs, names in os.walk(PROJECT):
        dirs[:] = [d for d in dirs if d not in (".venv", "__pycache__", ".mplcache") and (Path(current) / d).resolve() != STUDY]
        for name in names:
            path = Path(current) / name
            result[path.relative_to(PROJECT).as_posix()] = sha256(path)
    for path in (PROJECT.parent / "2026-10-28").glob("*.csv"):
        result["../2026-10-28/" + path.name] = sha256(path)
    return result


def features(bars):
    close = bars.close
    returns = close.div(close.shift(1)).sub(1)
    return pd.DataFrame({"return_1": returns, "return_3": close.div(close.shift(3)).sub(1),
                         "sma5_distance": close.div(close.rolling(5, min_periods=5).mean()).sub(1),
                         "volatility5": returns.rolling(5, min_periods=5).std(ddof=1)})


def audit(config):
    raw, minute = load_data(source_file(config, 0)), load_data(source_file(config, 1))
    bars, _ = canonicalize(raw, 0, minute)
    grouped = minute.assign(trade_date=minute.timestamp.dt.normalize() + pd.to_timedelta(minute.timestamp.dt.hour.ge(19).astype(int), unit="D"))
    agg = grouped.groupby("trade_date").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                          close=("close", "last"), volume=("volume", "sum"), last=("timestamp", "last"))
    differences, checks = [], []
    for row in raw.itertuples():
        if row.timestamp not in agg.index:
            raise ValueError(f"Missing same-source minute day: {row.timestamp}")
        ref = agg.loc[row.timestamp]
        fields = [c for c in ("open", "high", "low", "close") if getattr(row, c) != ref[c]]
        if fields:
            differences.append({"date": str(row.timestamp.date()), "fields": fields,
                                "daily": {c: float(getattr(row, c)) for c in fields},
                                "minute": {c: float(ref[c]) for c in fields}})
        complete = ref["last"] == row.timestamp + pd.Timedelta(hours=16) and row.close == ref["close"]
        checks.append({"date": str(row.timestamp.date()), "minute_last": str(ref["last"]), "complete_under_assumption": bool(complete),
                       "daily_volume": float(row.volume), "minute_volume": float(ref["volume"]), "volume_equal": bool(row.volume == ref["volume"])})
    if not all(r["complete_under_assumption"] for r in checks):
        raise ValueError("Daily completion/close cannot be established under existing research policy")
    numbers = raw.select_dtypes(include="number").drop(columns="raw_position")
    labels = make_labels(bars, 1)
    q1, q3 = raw.volume.quantile([.25, .75])
    result = {"created_at_utc": now(), "raw_rows": len(raw), "valid_bars": len(bars), "first": str(raw.timestamp.iloc[0]),
              "last": str(raw.timestamp.iloc[-1]), "fields": raw.columns.tolist(), "missing": raw.isna().sum().to_dict(),
              "duplicate_timestamps": int(raw.timestamp.duplicated().sum()), "strictly_sorted": bool(raw.timestamp.is_monotonic_increasing),
              "nonfinite_numeric": int((~np.isfinite(numbers)).sum().sum()), "ohlc_errors": 0, "structural_errors": 0,
              "zero_volume": int(raw.volume.eq(0).sum()), "zero_turnover": int(raw.turnover.eq(0).sum()),
              "volume_high_outliers_IQR3": int(raw.volume.gt(q3 + 3 * (q3 - q1)).sum()),
              "h1_all_raw_labels": {s: int(labels.label_status.eq(s).sum()) for s in ("UP", "DOWN", "FLAT", "PENDING")},
              "numeric_summary": numbers.describe().to_dict(), "saturday_bars": int(raw.timestamp.dt.dayofweek.eq(5).sum()),
              "sunday_bars": int(raw.timestamp.dt.dayofweek.eq(6).sum()), "daily_minute_differences": differences,
              "completion_and_volume_checks": checks, "daily_volume_equal_days": sum(r["volume_equal"] for r in checks),
              "minute_rows": len(minute), "source_sha256": {source_file(config, p).name: sha256(source_file(config, p)) for p in (0, 1)},
              "metadata": {k: "UNCONFIRMED" for k in ("symbol_code", "platform_authenticity", "timezone", "official_calendar", "volume_unit")},
              "availability": "native naive trade-date 16:00; same-source minute last at 16:00 and close equal; research assumption",
              "calendar": config["calendar_policy"], "no_data_policy": "rest by user instruction, no fabricated bars",
              "daily_prices_replaced": False, "training_allowed": True}
    return bars, result


def segment(samples, start, end, cutoff):
    part = samples.loc[samples.bar_position.ge(start) & samples.bar_position.lt(end)]
    ready = part.loc[part.feature_ready]
    purged = ready.target_available_at.ge(cutoff)
    scored = ready.loc[~purged]
    counts = {s.lower(): int(scored.label_status.eq(s).sum()) for s in ("UP", "DOWN", "FLAT", "PENDING")}
    result = {"start_position": start, "end_position_exclusive": end, "first": str(part.available_at.iloc[0]),
              "last": str(part.available_at.iloc[-1]), "raw_rows": len(part), "warmup": int((~part.feature_ready).sum()),
              "forecast_anchors": len(ready), "purged": int(purged.sum()), **counts, "binary_samples": counts["up"] + counts["down"],
              "all_anchor_labels": {s.lower(): int(part.label_status.eq(s).sum()) for s in ("UP", "DOWN", "FLAT", "PENDING")}}
    assert sum(counts.values()) + result["purged"] == len(ready)
    assert result["warmup"] + len(ready) == len(part)
    return result


def gated_fit(training, columns, config):
    return fit_model("logistic", {"C": config["C"]}, training, columns, config)


def score(data, probabilities):
    if len(data) < 10 or data.y.nunique() != 2:
        return {"n": len(data), "status": "UNABLE_TO_EVALUATE", "reason": "requires >=10 binary samples and both classes"}
    return metrics(data.y, probabilities)


def baseline(data, name):
    if name == "always_up":
        return np.ones(len(data))
    if name == "always_down":
        return np.zeros(len(data))
    return data.f_return_1.ge(0).to_numpy(dtype=float)


def records(data, probabilities, name, version, role, fit_positions, executed):
    out = data[["bar_position", "source_timestamp", "available_at", "target_position", "target_available_at", "y", "label_status"]].copy()
    out["p_up"] = np.asarray(probabilities, dtype=np.float64)
    out["p_down"] = 1.0 - out.p_up
    out["predicted_direction"] = np.where(out.p_up.ge(.5), "UP", "DOWN")
    out["confidence"] = np.maximum(out.p_up, out.p_down)
    out["prediction_timestamp"] = out.available_at
    out["executed_at_utc"] = executed
    out["prediction_horizon"] = 1
    out["model"] = name
    out["model_version"] = version
    out["role"] = role
    out["sample_status"] = out.label_status
    out["target_used_in_fit"] = out.bar_position.isin(fit_positions) if name == "logistic" else False
    out["probability_status"] = "UNCALIBRATED" if name == "logistic" else "DETERMINISTIC_RULE"
    out["signal"] = "OBSERVE_RESEARCH_ONLY"
    out["timezone_status"] = "UNCONFIRMED"
    return out


def wilson(correct, n):
    z = 1.959963984540054
    p = correct / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    radius = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [float(mid - radius), float(mid + radius)]


def paired_interval(delta):
    rng = np.random.default_rng(SEED)
    delta = np.asarray(delta)
    chunks = [delta[i:i + 5] for i in range(0, len(delta), 5)]
    draws = [np.concatenate([chunks[i] for i in rng.integers(0, len(chunks), len(chunks))]).mean() for _ in range(2000)]
    return np.quantile(draws, [.025, .975]).tolist()


def main(run_id):
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
        raise ValueError("Invalid run-id")
    output = STUDY / "runs" / run_id
    output.mkdir(parents=True, exist_ok=False)

    def log(message):
        line = f"{now()} {message}"
        print(line, flush=True)
        with (output / "execution.log").open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    before = protected_files()
    write_json(output / "legacy-before.json", before)
    try:
        log("START isolated daily h=1; no previous results overwritten")
        config = load_config()
        assert config["min_fit_samples"] == 80
        bars, audit_result = audit(config)
        write_json(output / "source-audit.json", audit_result)
        log(f"AUDIT rows={len(bars)} differences={len(audit_result['daily_minute_differences'])}")
        feat = features(bars)
        assert feat.columns.tolist() == FEATURES
        ready = np.isfinite(feat).all(axis=1)
        warmup = int(np.flatnonzero(ready)[0])
        assert len(bars) == 150 and warmup == 5 and ready.iloc[warmup:].all()
        spec = {"run_id": run_id, "created_at_utc": now(), "horizons": [1], "features": FEATURES, "warmup": warmup,
                "test_start": 120, "development_end": 120, "folds": [[90, 105], [105, 120]], "C_candidates": [.1, 1.],
                "seed": SEED, "threads": 4, "min_fit_samples": 80, "min_validation_samples": 10, "min_test_samples": 10,
                "selection": "mean fold balanced_accuracy; ties choose smaller C", "threshold": .5,
                "baselines": BASELINES, "probabilities": "UNCALIBRATED", "test_identity": "ALREADY_EXPOSED_RETROSPECTIVE",
                "metrics": ["accuracy", "balanced_accuracy", "confusion_matrix", "mcc", "f1", "auc", "log_loss", "brier"],
                "uncertainty": {"accuracy": "Wilson95 descriptive; dependence not corrected", "paired": "nonoverlapping consecutive blocks of 5, bootstrap 2000, seed20261028"},
                "signal_gate": "majority CV folds strict accuracy advantage over best baseline; holdout accuracy and BA strict advantage over all baselines and all paired CI lower bounds >0"}
        write_json(output / "config.json", spec)
        development_labels = make_labels(bars, 1, bars.available_at.iloc[120])
        development = samples_for(bars, feat, development_labels, warmup)
        cols = ["f_" + name for name in FEATURES]
        source_hashes = audit_result["source_sha256"]
        code_paths = [STUDY / name for name in ("run.py", "test_daily.py", "verify.py")]
        code_paths += sorted((PROJECT / "src").glob("*.py"))
        doc_paths = sorted((STUDY / "baseline").glob("*.md")) + [STUDY / "decisions.md"]
        manifest = {str(p.relative_to(PROJECT)): sha256(p) for p in code_paths + doc_paths}
        prereg = {"created_at_utc": now(), "configuration_sha256": sha256(output / "config.json"), "source_sha256": source_hashes,
                  "code_and_baseline_sha256": manifest, "holdout_metrics_computed": False}
        write_json(output / "preregistered.json", prereg)
        log("PREREGISTERED config/features/splits/candidates/metrics/gates; no holdout score")
        cv, fit_indices, candidate_rows, cv_predictions, cv_train_predictions = [], [], [], [], []
        cv_models = {}
        with threadpool_limits(limits=4):
            for fold, (start, end) in enumerate(spec["folds"], 1):
                train_cut, val_cut = bars.available_at.iloc[start], bars.available_at.iloc[end]
                training = window(development, 0, start, train_cut)
                valid = window(development, start, end, val_cut)
                assert_purged(training, train_cut)
                assert_purged(valid, val_cut)
                fit_indices.append({"fold": fold, "training": training.bar_position.tolist(), "validation": valid.bar_position.tolist(),
                                    "fit_target_max": str(training.target_available_at.max()), "validation_start": str(train_cut)})
                fold_summary = {"fold": fold, "training": segment(development, 0, start, train_cut),
                                "validation": segment(development, start, end, val_cut), "models": {}}
                for name in BASELINES:
                    fold_summary["models"][name] = score(valid, baseline(valid, name))
                for c in spec["C_candidates"]:
                    candidate = f"logistic_C{c}"
                    if len(valid) < 10 or valid.y.nunique() != 2:
                        fold_summary["models"][candidate] = {"status": "UNABLE_TO_EVALUATE", "n": len(valid)}
                        continue
                    try:
                        model, info = gated_fit(training, cols, {**config, "C": c})
                    except ValueError as exc:
                        if not str(exc).startswith("INSUFFICIENT_DATA:"):
                            raise
                        fold_summary["models"][candidate] = {"status": "UNABLE_TO_EVALUATE", "reason": str(exc)}
                        continue
                    probability = model.predict_proba(valid[cols])[:, 1]
                    fold_summary["models"][candidate] = {**score(valid, probability), "fit": info}
                    cv_models[(fold, c)] = model
                    joblib.dump(model, output / f"cv-fold{fold}-C{c}.joblib")
                    candidate_rec = records(development.iloc[start:end], model.predict_proba(development.iloc[start:end][cols])[:, 1],
                                            candidate, f"{run_id}-fold{fold}-C{c}", "EXPANDING_VALIDATION", training.bar_position, now())
                    candidate_rec.loc[candidate_rec.bar_position.eq(end - 1), "sample_status"] = "CROSS_VALIDATION_PURGED"
                    candidate_rows.append(candidate_rec)
                cv.append(fold_summary)
                log(f"CV fold={fold} fit={len(training)} validation={len(valid)}")
            write_json(output / "walk-forward.json", cv)
            write_json(output / "fit-indices.json", fit_indices)
            choices = []
            for c in spec["C_candidates"]:
                results = [f["models"][f"logistic_C{c}"] for f in cv]
                if all(r.get("status") == "OK" for r in results):
                    choices.append((float(np.mean([r["balanced_accuracy"] for r in results])), -c, c))
            if not choices:
                write_json(output / "result.json", {"status": "UNABLE_TO_EVALUATE", "reason": "no candidate met every unchanged sample gate"})
                log("UNABLE_TO_EVALUATE; holdout remains unscored")
                return
            chosen_c = max(choices)[2]
            write_json(output / "selection.json", {"selected_C": chosen_c, "candidate_mean_BA": {str(x[2]): x[0] for x in choices},
                                                     "created_at_utc": now(), "used_holdout": False})
            training = window(development, 0, 120, bars.available_at.iloc[120])
            assert_purged(training, bars.available_at.iloc[120])
            model, final_fit = gated_fit(training, cols, {**config, "C": chosen_c})
            bundle = {"estimator": model, "feature_names": FEATURES, "feature_columns": cols, "config": spec,
                      "selected_C": chosen_c, "fit_positions": training.bar_position.tolist(), "model_version": run_id,
                      "research_only": True, "probability_status": "UNCALIBRATED", "source_sha256": source_hashes}
            joblib.dump(bundle, output / "model.joblib")
            write_json(output / "final-fit.json", final_fit)
            freeze = {"created_at_utc": now(), "preregistered_sha256": sha256(output / "preregistered.json"),
                      "model_sha256": sha256(output / "model.joblib"), "selection_sha256": sha256(output / "selection.json"),
                      "training_positions": training.bar_position.tolist(), "fit_target_max": str(training.target_available_at.max()),
                      "holdout_first_available_at": str(bars.available_at.iloc[120]), "test_identity": spec["test_identity"]}
            write_json(output / "frozen.json", freeze)
            log(f"FROZEN selected_C={chosen_c} final_fit={len(training)}; holdout not scored")
            marker = output / "holdout-unlocked.json"
            with marker.open("x", encoding="utf-8") as stream:
                json.dump({"created_at_utc": now(), "frozen_sha256": sha256(output / "frozen.json"), "evaluations": 1}, stream)
            # Historical labels become available to this experiment only after the model is frozen.
            samples = samples_for(bars, feat, make_labels(bars, 1), warmup)
            test = samples.loc[samples.bar_position.ge(120) & samples.feature_ready & samples.y.notna()]
            ledger = samples[["bar_position", "source_timestamp", "available_at", "feature_ready", "label_status", "target_available_at"]].copy()
            ledger["role"] = np.where(ledger.bar_position.ge(120), "HISTORICAL_HOLDOUT", "DEVELOPMENT")
            ledger["status"] = np.where(ledger.feature_ready, ledger.label_status, "WARMUP")
            ledger.loc[ledger.bar_position.eq(119), "status"] = "CROSS_HOLDOUT_PURGED"
            ledger.to_csv(output / "bar-ledger.csv", index=False)
            all_ready = samples.loc[samples.feature_ready]
            all_predictions, comparison = [], []
            for name in ["logistic", *BASELINES]:
                probability = model.predict_proba(all_ready[cols])[:, 1] if name == "logistic" else baseline(all_ready, name)
                out = records(all_ready, probability, name, run_id, "DEVELOPMENT_NOT_FITTED", training.bar_position, now())
                out.loc[out.bar_position.isin(training.bar_position), "role"] = "TRAIN_IN_SAMPLE" if name == "logistic" else "DEVELOPMENT_RULE"
                out.loc[out.bar_position.ge(120), "role"] = "HISTORICAL_HOLDOUT"
                out.loc[out.bar_position.eq(119), "sample_status"] = "CROSS_HOLDOUT_PURGED"
                all_predictions.append(out)
                test_p = model.predict_proba(test[cols])[:, 1] if name == "logistic" else baseline(test, name)
                result = score(test, test_p)
                if result["status"] == "OK":
                    correct = int(((test_p >= .5) == test.y).sum())
                    result["wilson95_accuracy_descriptive"] = wilson(correct, len(test))
                comparison.append({"model": name, **result})
            for fold, (start, end) in enumerate(spec["folds"], 1):
                fit_pos = fit_indices[fold - 1]["training"]
                val = samples.iloc[start:end]
                tr = samples.loc[samples.bar_position.isin(fit_pos)]
                for name in ["logistic", *BASELINES]:
                    fitted = cv_models[(fold, chosen_c)]
                    p = fitted.predict_proba(val[cols])[:, 1] if name == "logistic" else baseline(val, name)
                    rec = records(val, p, name, f"{run_id}-fold{fold}", "EXPANDING_VALIDATION", fit_pos, now())
                    rec.loc[rec.bar_position.eq(end - 1), "sample_status"] = "CROSS_VALIDATION_PURGED"
                    rec["fold"] = fold
                    cv_predictions.append(rec)
                    p_tr = fitted.predict_proba(tr[cols])[:, 1] if name == "logistic" else baseline(tr, name)
                    train_rec = records(tr, p_tr, name, f"{run_id}-fold{fold}", "TRAIN_IN_SAMPLE_AUDIT_ONLY", fit_pos, now())
                    train_rec["fold"] = fold
                    cv_train_predictions.append(train_rec)
            pd.concat(all_predictions).to_csv(output / "predictions.csv", index=False)
            pd.concat(cv_predictions).to_csv(output / "cv-predictions.csv", index=False)
            pd.concat(cv_train_predictions).to_csv(output / "cv-training-predictions.csv", index=False)
            pd.concat(candidate_rows).to_csv(output / "candidate-predictions.csv", index=False)
            write_json(output / "holdout-metrics.json", {"created_at_utc": now(), "models": comparison,
                                                       "confusion_order": "rows=true DOWN,UP; columns=predicted DOWN,UP"})
            pd.DataFrame(comparison).to_csv(output / "model-comparison.csv", index=False)
            summary = {"full": segment(samples, 0, 150, pd.Timestamp.max),
                       "development_fit": segment(samples, 0, 120, bars.available_at.iloc[120]),
                       "historical_holdout": segment(samples, 120, 150, pd.Timestamp.max), "folds": cv}
            write_json(output / "sample-counts.json", summary)
            logistic_p = model.predict_proba(test[cols])[:, 1]
            lr_correct = (logistic_p >= .5) == test.y.to_numpy()
            intervals = {name: {"mean_accuracy_difference": float((lr_correct.astype(float) - ((baseline(test, name) >= .5) == test.y.to_numpy())).mean()),
                                "paired_block95": paired_interval(lr_correct.astype(float) - ((baseline(test, name) >= .5) == test.y.to_numpy()))} for name in BASELINES} if comparison[0]["status"] == "OK" else {}
            cv_wins = sum(f["models"][f"logistic_C{chosen_c}"]["accuracy"] > max(f["models"][name]["accuracy"] for name in BASELINES) for f in cv)
            lr = comparison[0]
            sufficient_test = lr["status"] == "OK"
            test_advantage = sufficient_test and all(lr[metric] > r[metric] for r in comparison[1:] for metric in ("accuracy", "balanced_accuracy"))
            qualified = cv_wins > len(cv) / 2 and test_advantage and all(r["paired_block95"][0] > 0 for r in intervals.values())
            write_json(output / "uncertainty.json", {"paired_differences": intervals, "cv_strict_wins": cv_wins,
                                                     "limitations": "small correlated historical sample, already exposed; C selection adds uncertainty; no forward qualification"})
            result = {"status": "TRAINED_RESEARCH_ONLY" if sufficient_test else "UNABLE_TO_EVALUATE", "created_at_utc": now(),
                      "run_id": run_id, "selected_C": chosen_c, "fit_n": len(training), "test_n": len(test), "cv_strict_wins": cv_wins,
                      "research_signal_gate": "PASS_RETROSPECTIVE_ONLY" if qualified else "FAIL", "reliable_predictive_signal": False,
                      "conclusion": "历史数值条件满足，仍需未暴露前向数据确认" if qualified else "未得到可靠预测信号",
                      "not_tested": ["future_forward_validation", "real_time", "live_trading", "probability_calibration"],
                      "unverified": ["symbol_code", "timezone", "official_calendar", "volume_unit", "platform_authenticity"]}
            write_json(output / "result.json", result)
            write_json(output / "environment.json", {"python": sys.version, "platform": platform.platform(), "executable": sys.executable,
                                                     "packages": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scikit-learn", "scipy", "joblib", "threadpoolctl")}})
            shutil.copy2(STUDY / "preflight-tests.txt", output / "preflight-tests.txt")
            log(f"DONE fit={len(training)} test={len(test)} research_gate={result['research_signal_gate']}")
    except Exception:
        log(traceback.format_exc())
        raise
    finally:
        after = protected_files()
        changed = [name for name in before.keys() | after.keys() if before.get(name) != after.get(name)]
        write_json(output / "preservation.json", {"created_at_utc": now(), "files_checked": len(before), "changed": changed, "status": "PASS" if not changed else "FAIL"})
        log(f"PRESERVATION files={len(before)} changed={len(changed)}")
        if changed:
            raise AssertionError(f"Protected files changed: {changed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    main(args.run_id)
