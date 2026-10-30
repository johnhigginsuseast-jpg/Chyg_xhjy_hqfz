"""Recompute frozen experiment evidence without fitting or reshooting its holdout."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import run


def verify(output):
    def read(name):
        return json.loads((output / name).read_text(encoding="utf-8"))

    checks = []
    raw = pd.read_csv(run.PROJECT.parent / "2026-10-28" / "日线.csv")
    close = raw["收盘"].to_numpy(dtype=float)
    expected_y = np.full(len(close), np.nan)
    diff = np.diff(close)
    expected_y[:-1] = np.where(diff > 0, 1., np.where(diff < 0, 0., np.nan))
    prediction = pd.read_csv(output / "predictions.csv")
    cv_prediction = pd.read_csv(output / "cv-predictions.csv")
    models = ["logistic", *run.BASELINES]
    assert len(raw) == 150 and len(prediction) == 145 * 4
    assert len(cv_prediction) == 30 * 4
    for name, group in prediction.groupby("model"):
        assert group.bar_position.tolist() == list(range(5, 150))
        np.testing.assert_allclose(group.y, expected_y[group.bar_position], equal_nan=True)
        np.testing.assert_allclose(group.p_up + group.p_down, 1., rtol=0, atol=1e-15)
        assert np.isfinite(group[["p_up", "p_down"]]).all().all()
        assert group.p_up.between(0, 1).all()
        assert group.prediction_timestamp.equals(group.available_at)
        assert group.model_version.nunique() == 1
        if name != "logistic":
            pos = group.bar_position.to_numpy()
            p = np.ones(len(pos)) if name == "always_up" else np.zeros(len(pos)) if name == "always_down" else (close[pos] >= close[pos - 1]).astype(float)
            np.testing.assert_array_equal(group.p_up, p)
    checks.append("580 predictions, 120 CV predictions; labels/probabilities/baselines/full coverage")

    def independent_score(group, positions, expected):
        part = group.loc[group.bar_position.isin(positions)]
        y = expected_y[part.bar_position]
        p = part.p_up.to_numpy() >= .5
        cm = [[int(((y == actual) & (p == pred)).sum()) for pred in (0, 1)] for actual in (0, 1)]
        acc = float((y == p).mean())
        ba = .5 * (cm[0][0] / sum(cm[0]) + cm[1][1] / sum(cm[1]))
        assert cm == expected["confusion_matrix"]
        assert len(part) == expected["n"]
        assert abs(acc - expected["accuracy"]) < 1e-14
        assert abs(ba - expected["balanced_accuracy"]) < 1e-14

    test_positions = [i for i in range(120, 149) if not np.isnan(expected_y[i])]
    holdout = read("holdout-metrics.json")
    for metric in holdout["models"]:
        independent_score(prediction.loc[prediction.model.eq(metric["model"])], test_positions, metric)
    indices = read("fit-indices.json")
    chosen = read("selection.json")["selected_C"]
    rolling = read("walk-forward.json")
    for fold, (start, end) in enumerate(((90, 105), (105, 120)), 1):
        fit = [i for i in range(5, start - 1) if not np.isnan(expected_y[i])]
        val = [i for i in range(start, end - 1) if not np.isnan(expected_y[i])]
        assert fit == indices[fold - 1]["training"] and val == indices[fold - 1]["validation"]
        assert len(fit) >= 80 and len(val) >= 10
        assert max(i + 1 for i in fit) < start and max(i + 1 for i in val) < end
        for name in models:
            group = cv_prediction.loc[cv_prediction.fold.eq(fold) & cv_prediction.model.eq(name)]
            metric_name = f"logistic_C{chosen}" if name == "logistic" else name
            independent_score(group, val, rolling[fold - 1]["models"][metric_name])
    checks.append("12 reported test/CV metric groups independently recomputed; raw-index purge verified")

    prereg, frozen, unlocked = read("preregistered.json"), read("frozen.json"), read("holdout-unlocked.json")
    assert prereg["created_at_utc"] < frozen["created_at_utc"] < unlocked["created_at_utc"] < holdout["created_at_utc"]
    assert run.sha256(output / "config.json") == prereg["configuration_sha256"]
    assert run.sha256(output / "model.joblib") == frozen["model_sha256"]
    assert run.sha256(output / "selection.json") == frozen["selection_sha256"]
    assert run.sha256(output / "preregistered.json") == frozen["preregistered_sha256"]
    assert run.sha256(output / "frozen.json") == unlocked["frozen_sha256"]
    assert unlocked["evaluations"] == 1
    for name, digest in prereg["code_and_baseline_sha256"].items():
        assert run.sha256(run.PROJECT / name) == digest, name
    for name, digest in prereg["source_sha256"].items():
        assert run.sha256(run.PROJECT.parent / "2026-10-28" / name) == digest
    checks.append("data/code/baseline/config/model hashes; freeze precedes one historical unlock")

    bundle = run.joblib.load(output / "model.joblib")
    bars, _ = run.audit(run.load_config())
    feat = run.features(bars).add_prefix("f_")
    model = bundle["estimator"]
    fit_pos = [i for i in range(5, 119) if not np.isnan(expected_y[i])]
    assert fit_pos == frozen["training_positions"] == bundle["fit_positions"]
    np.testing.assert_allclose(model[0].mean_, feat.iloc[fit_pos].mean().to_numpy(), rtol=1e-12)
    np.testing.assert_allclose(model[0].var_, feat.iloc[fit_pos].var(ddof=0).to_numpy(), rtol=1e-12)
    lr = prediction.loc[prediction.model.eq("logistic")]
    np.testing.assert_allclose(model.predict_proba(feat.iloc[5:])[:, 1], lr.p_up, rtol=0, atol=2e-16)
    assert lr.loc[lr.bar_position.ge(120), "target_used_in_fit"].eq(False).all()
    assert prediction.loc[prediction.bar_position.eq(149), "label_status"].eq("PENDING").all()
    assert len(pd.read_csv(output / "bar-ledger.csv")) == 150
    checks.append("model reload prediction equality; scaler fit only on 111 preregistered development samples; pending retained")

    before = read("legacy-before.json")
    after = run.protected_files()
    assert before == after
    assert read("preservation.json")["status"] == "PASS"
    checks.append(f"{len(before)} legacy/source files preserved")
    result = {"status": "PASS", "created_at_utc": run.now(), "checks": checks, "refit": False, "holdout_rescored_for_model_selection": False}
    run.write_json(output / "independent-verification.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    verify(args.path)
