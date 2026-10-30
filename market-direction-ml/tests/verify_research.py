"""Independent arithmetic/source checks of the frozen research outputs."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src.common import ROOT, period_name, sha256, write_json
from src.features import make_features
from src.predict import load_bundle


def reference_keep(close, minute_rule):
    if not minute_rule:
        return np.arange(len(close))
    keep, history, i = [], [], 0
    while i < len(close):
        keep.append(i)
        history.append(close[i])
        if len(history) >= 4:
            moves = np.sign(np.diff(history[-4:]))
            if abs(moves.sum()) == 3:
                history = [close[i]]
                i += 3
                continue
        i += 1
    return np.asarray(keep)


def independently_recompute(data, threshold):
    data = data[data.y.notna()]
    y, p = data.y.to_numpy(int), data.p_up.to_numpy(float)
    prediction = (p >= .5).astype(int)
    tn = int(((y == 0) & (prediction == 0)).sum())
    fp = int(((y == 0) & (prediction == 1)).sum())
    fn = int(((y == 1) & (prediction == 0)).sum())
    tp = int(((y == 1) & (prediction == 1)).sum())
    divide = lambda a, b: a / b if b else 0.
    denom = np.sqrt(float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)))
    recall = [divide(tn, tn + fp), divide(tp, tp + fn)]
    actual_recalls = [r for r, count in zip(recall, [tn + fp, tp + fn]) if count]
    signal = np.maximum(p, 1 - p) >= threshold
    clipped = np.clip(p, 1e-8, 1 - 1e-8)
    n1, n0 = int(y.sum()), int((y == 0).sum())
    ranks = pd.Series(p).rank(method="average").to_numpy()
    return {"n": len(y), "accuracy": divide(tp + tn, len(y)), "balanced_accuracy": float(np.mean(actual_recalls)),
            "mcc": divide(tp * tn - fp * fn, denom), "f1": divide(2 * tp, 2 * tp + fp + fn),
            "precision_down": divide(tn, tn + fn), "precision_up": divide(tp, tp + fp),
            "recall_down": recall[0], "recall_up": recall[1],
            "brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(-np.mean(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))),
            "auc": (ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else None,
            "signal_coverage": float(signal.mean()),
            "signal_accuracy": float((prediction[signal] == y[signal]).mean()) if signal.any() else None,
            "confusion_matrix": [[tn, fp], [fn, tp]]}


def verify(run_id):
    run = ROOT / "reports/evidence" / run_id
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    frozen = json.loads((run / "frozen.json").read_text(encoding="utf-8"))
    decisions = json.loads((run / "decisions.json").read_text(encoding="utf-8"))
    comparison = pd.read_csv(ROOT / "reports/model_comparison.csv", float_precision="round_trip")
    for name, digest in frozen["source_hashes"].items():
        assert sha256(Path(config["data_path"]) / name) == digest
    for name, digest in frozen["code_hashes"].items():
        actual = sha256(ROOT / name)
        if actual != digest:
            if Path(name).as_posix() == "src/data_loader.py":
                validation = json.loads((run / "calendar-validation-repair.json").read_text(encoding="utf-8"))
                assert validation["original_sha256"] == digest and validation["new_sha256"] == actual
                assert validation["all_existing_canonical_data_unchanged"] is True
                continue
            repair = json.loads((run / "report-repair.json").read_text(encoding="utf-8"))
            assert name == repair["file"] and Path(name).as_posix() == "src/final_report.py"
            assert digest == repair["original_sha256"] and actual == repair["new_sha256"]
            assert repair["models_or_selection_changed"] is False
    checked, calibrations, source_rows = [], [], []
    for period in config["periods"]:
        raw = pd.read_parquet(ROOT / f"data/cleaned/{period_name(period)}.parquet")
        source = pd.read_csv(config["data_path"] + "/" + ("日线.csv" if period == 0 else f"{period}分钟K线.csv"), encoding="utf-8-sig")
        expected_close = np.asarray([float(source.iloc[int(str(g).split(",")[-1])]["收盘"]) for g in raw.raw_positions])
        np.testing.assert_array_equal(raw.close, expected_close)
        keep = reference_keep(expected_close, period == 1)
        ledger = pd.read_csv(run / f"{period_name(period)}-coverage.csv")
        np.testing.assert_array_equal(ledger.loc[ledger.status == "accepted", "bar_position"], keep)
        kept = raw.iloc[keep].reset_index(drop=True)
        features = make_features(kept).add_prefix("f_")
        n = len(raw)
        train_end, cal_end, test_start = int(n * .7), int(n * .775), int(n * .85)
        expected_test = keep[keep >= test_start]
        source_rows.append({"period": period, "raw_completed_bars": n, "retained": len(keep), "eligible_test": len(expected_test)})
        for decision in [d for d in decisions if d["period"] == period]:
            name, h = decision["model"], decision["horizon"]
            if decision["status"] != "OK":
                row = comparison[(comparison.period == period) & (comparison.horizon == h) & (comparison.model == name)].iloc[0]
                assert row.status == "INSUFFICIENT_DATA" and row.predicted_count == 0
                continue
            data = pd.read_csv(run / f"predictions/{period_name(period)}-h{h}-{name}.csv", float_precision="round_trip")
            np.testing.assert_array_equal(data.bar_position, expected_test)
            np.testing.assert_allclose(data.p_up + data.p_down, 1., atol=1e-12, rtol=0)
            assert np.isfinite(data.p_up).all() and data.p_up.between(0, 1).all()
            np.testing.assert_array_equal(data.predicted_direction, np.where(data.p_up >= .5, "up", "down"))
            for record in data.itertuples():
                j = int(np.searchsorted(keep, record.bar_position))
                assert record.close == expected_close[record.bar_position]
                if j + h >= len(keep):
                    assert record.label_status == "PENDING" and pd.isna(record.y)
                else:
                    ret = expected_close[keep[j + h]] / expected_close[record.bar_position] - 1
                    assert abs(record.ret - ret) < 1e-12
                    assert pd.Timestamp(record.target_available_at) == raw.available_at.iloc[keep[j + h]]
                    if ret == 0:
                        assert record.label_status == "FLAT" and pd.isna(record.y)
                    else:
                        assert record.y == int(ret > 0)
            score = independently_recompute(data, decision["threshold"])
            row = comparison[(comparison.period == period) & (comparison.horizon == h) & (comparison.model == name)].iloc[0]
            for metric, value in score.items():
                if metric == "confusion_matrix":
                    assert json.loads(row[metric]) == value
                elif value is None:
                    assert pd.isna(row[metric])
                else:
                    assert abs(row[metric] - value) < 1e-10, (period, h, name, metric, row[metric], value)
            checked.append({"period": period, "horizon": h, "model": name, "forecasts": len(data), "scored": score["n"], "metrics": "MATCH"})
            if "model_path" not in decision:
                continue
            bundle = load_bundle(ROOT / decision["model_path"])
            target_time = kept.available_at.shift(-h)
            future_close = kept.close.shift(-h)
            y = future_close.gt(kept.close).astype(float).where(future_close.ne(kept.close) & future_close.notna())
            ready = np.arange(len(kept)) >= config["warmup"]
            cal = kept.bar_position.ge(train_end) & kept.bar_position.lt(cal_end) & target_time.lt(raw.available_at.iloc[cal_end]) & y.notna() & ready
            val = kept.bar_position.ge(cal_end) & kept.bar_position.lt(test_start) & target_time.lt(raw.available_at.iloc[test_start]) & y.notna() & ready
            raw_p = bundle["estimator"].predict_proba(features.loc[cal, bundle["feature_columns"]])[:, 1]
            logits = np.log(np.clip(raw_p, 1e-6, 1 - 1e-6) / np.clip(1 - raw_p, 1e-6, 1))
            replica = LogisticRegression(C=1., random_state=config["seed"], max_iter=500).fit(logits.reshape(-1, 1), y.loc[cal].astype(int))
            np.testing.assert_allclose(replica.coef_, bundle["calibrator"].coef_, rtol=0, atol=1e-8)
            np.testing.assert_allclose(replica.intercept_, bundle["calibrator"].intercept_, rtol=0, atol=1e-8)
            assert target_time.loc[cal].max() < raw.available_at.iloc[cal_end]
            assert target_time.loc[val].max() < raw.available_at.iloc[test_start]
            val_raw = bundle["estimator"].predict_proba(features.loc[val, bundle["feature_columns"]])[:, 1]
            val_logit = np.log(np.clip(val_raw, 1e-6, 1 - 1e-6) / np.clip(1 - val_raw, 1e-6, 1))
            val_p = replica.predict_proba(val_logit.reshape(-1, 1))[:, 1]
            choices = []
            for tau in config["thresholds"]:
                signals = np.maximum(val_p, 1 - val_p) >= tau
                if signals.sum() >= 30 and signals.mean() >= config["minimum_signal_coverage"]:
                    choices.append((float(((val_p[signals] >= .5).astype(int) == y.loc[val].to_numpy(int)[signals]).mean()), -tau, tau))
            expected_threshold = max(choices)[2] if choices else .5
            assert bundle["threshold"] == expected_threshold
            calibrations.append({"period": period, "horizon": h, "model": name, "calibration_n": int(cal.sum()),
                                 "threshold_n": int(val.sum()), "calibration_max_target": str(target_time.loc[cal].max()),
                                 "threshold_start": str(raw.available_at.iloc[cal_end]), "frozen_calibrator_reproduced": True})
    fits = json.loads((run / "fit-index-audit.json").read_text(encoding="utf-8"))
    for fit in fits:
        bars = pd.read_parquet(ROOT / f"data/cleaned/{period_name(fit['period'])}.parquet")
        train_end = int(len(bars) * .7)
        edge = train_end if fit["fold"] == "final_train" else int(np.linspace(train_end // 2, train_end, config["walk_forward_folds"] + 1, dtype=int)[fit["fold"]])
        assert pd.Timestamp(fit["fit_max_target"]) < bars.available_at.iloc[edge]
        assert fit["fit_max_position"] < edge
        if fit["inner_early_stop"]:
            inner = fit["inner_early_stop"]
            assert pd.Timestamp(inner["core_max_target"]) < pd.Timestamp(inner["boundary"])
    assert len(comparison) == len(config["periods"]) * len(config["horizons"]) * 8
    result = {"status": "PASS", "scope": "source/independent rule replay/all forecasts/labels/metrics/calibration role reproduction",
              "successful_cases": len(checked), "insufficient_cases": int(comparison.status.eq("INSUFFICIENT_DATA").sum()),
              "source_rows": source_rows, "prediction_checks": checked, "calibration_checks": calibrations,
              "purged_fit_records": len(fits),
              "note": "replica fits use only the frozen past calibration role; no saved model or threshold changed"}
    write_json(run / "independent-verification.json", result)
    print(json.dumps({k: result[k] for k in ("status", "successful_cases", "insufficient_cases", "scope")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    verify(parser.parse_args().run_id)
