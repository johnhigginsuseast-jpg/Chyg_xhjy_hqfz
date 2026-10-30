"""Isolated v0.1 daily research; never changes the existing project or lowers its fit gate."""
import json
import os
import subprocess
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parent
PROJECT = STUDY.parents[1]
sys.path.insert(0, str(PROJECT))

import joblib
import numpy as np
import pandas as pd

from src.common import load_config, sha256, source_file, write_json
from src.data_loader import canonicalize, load_data
from src.evaluate import metrics
from src.features import make_features
from src.labels import make_labels
from src.predict import baseline_probability
from src.train import BASELINES, fit_model
from src.validation import assert_purged, boundaries, samples_for, walk_forward_windows, window


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


def summary(samples, start, end, cutoff):
    part = samples.loc[samples.bar_position.ge(start) & samples.bar_position.lt(end)]
    ready = part.loc[part.feature_ready]
    purged = ready.target_available_at.ge(cutoff)
    known = ready.loc[~purged]
    result = {"raw_rows": len(part), "warmup_or_not_ready": int((~part.feature_ready).sum()), "forecast_anchors": len(ready),
              "up": int(known.label_status.eq("UP").sum()), "down": int(known.label_status.eq("DOWN").sum()),
              "flat": int(known.label_status.eq("FLAT").sum()), "pending": int(known.label_status.eq("PENDING").sum()),
              "purged": int(purged.sum())}
    assert sum(result[k] for k in ("up", "down", "flat", "pending", "purged")) == len(ready)
    result["binary_samples"] = result["up"] + result["down"]
    return result


def attempt(training, validation, columns, config):
    if len(training) >= config["min_fit_samples"] and (len(validation) < 10 or validation.y.nunique() < 2):
        return None, {"status": "INSUFFICIENT_DATA", "reason": "validation requires >=10 binary samples and both classes"}
    try:
        model, evidence = fit_model("logistic", {"C": .1}, training, columns, config)
    except ValueError as exc:
        if not str(exc).startswith("INSUFFICIENT_DATA:"):
            raise
        return None, {"status": "INSUFFICIENT_DATA", "reason": str(exc), "fit_n": len(training), "required_fit": config["min_fit_samples"]}
    return model, {"status": "FITTED_RESEARCH_ONLY", **evidence}


def main():
    output = STUDY / "run-01"
    output.mkdir(exist_ok=False)
    before = protected_files()
    write_json(output / "legacy-before.json", before)
    config = load_config()
    assert config["warmup"] == 64 and config["min_fit_samples"] == 80
    preflight = json.loads((STUDY / "preflight.json").read_text(encoding="utf-8"))
    assert sha256(source_file(config, 0)) == preflight["daily_sha256"]
    assert sha256(source_file(config, 1)) == preflight["minute_sha256"]
    daily, minute = load_data(source_file(config, 0)), load_data(source_file(config, 1))
    bars, _ = canonicalize(daily, 0, minute)
    features, b = make_features(bars), boundaries(bars)
    assert len(bars) == 150 and (b["train_end"], b["test_start"]) == (105, 127)
    pd.testing.assert_frame_equal(features.iloc[:127], make_features(bars.iloc[:127].copy()))
    altered = bars.copy()
    altered.loc[127:, ["open", "high", "low", "close", "volume"]] *= 7
    pd.testing.assert_frame_equal(features.iloc[:127], make_features(altered).iloc[:127])
    grouped = minute.assign(trade_date=minute.timestamp.dt.normalize() + pd.to_timedelta(minute.timestamp.dt.hour.ge(19).astype(int), unit="D"))
    aggregated = grouped.groupby("trade_date").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    differences = []
    for row in daily.itertuples():
        fields = [c for c in ("open", "high", "low", "close") if getattr(row, c) != aggregated.loc[row.timestamp, c]]
        if fields:
            differences.append({"date": str(row.timestamp.date()), "fields": fields,
                                "daily": {c: float(getattr(row, c)) for c in fields}, "minute": {c: float(aggregated.loc[row.timestamp, c]) for c in fields}})
    assert differences == preflight["daily_minute_differences"]
    write_json(output / "source-audit.json", {"daily_rows": len(bars), "first": str(daily.timestamp.iloc[0]), "last": str(daily.timestamp.iloc[-1]),
                                             "daily_sha256": sha256(source_file(config, 0)), "minute_sha256": sha256(source_file(config, 1)),
                                             "differences": differences, "replaced_daily_values": False, "timezone": "UNCONFIRMED", "availability": "trade_date 16:00 research assumption"})
    specification = {"requirements_sha256": sha256(STUDY / "baseline/requirements-v0.1.md"), "acceptance_sha256": sha256(STUDY / "baseline/acceptance-v0.1.md"),
                     "boundaries": b, "warmup": 64, "min_fit_samples": 80, "min_validation_samples": 10, "feature_count": len(features.columns),
                     "focus_horizon": 1, "readiness_horizons": [1, 3, 5, 10], "logistic_C": .1, "seed": config["seed"],
                     "baselines": BASELINES, "calibration": "NONE; no reliability claim", "threshold": .5, "test_status": "ALREADY_EXPOSED_RETROSPECTIVE",
                     "fit_gate_origin": "unchanged configs/default.json and src/train.py", "official_source_metadata": "UNCONFIRMED"}
    write_json(output / "config.json", specification)
    columns = ["f_" + c for c in features.columns]
    eligibility, indices, rolling, h1_model = [], {}, [], None
    for horizon in (1, 3, 5, 10):
        labels = make_labels(bars, horizon, bars.available_at.iloc[b["test_start"]])
        samples = samples_for(bars, features, labels, 64)
        train = window(samples, 0, b["train_end"], bars.available_at.iloc[b["train_end"]])
        valid = window(samples, b["train_end"], b["test_start"], bars.available_at.iloc[b["test_start"]])
        assert_purged(train, bars.available_at.iloc[b["train_end"]])
        assert_purged(valid, bars.available_at.iloc[b["test_start"]])
        reference = [i for i in range(64, b["train_end"]) if i + horizon < b["train_end"] and bars.close.iloc[i + horizon] != bars.close.iloc[i]]
        assert train.bar_position.tolist() == reference
        indices[str(horizon)] = {"training": train.bar_position.tolist(), "validation": valid.bar_position.tolist()}
        reason = "minimum fitting count" if len(train) < 80 else "eligible"
        eligibility.append({"horizon": horizon, "training": summary(samples, 0, b["train_end"], bars.available_at.iloc[b["train_end"]]),
                            "validation": summary(samples, b["train_end"], b["test_start"], bars.available_at.iloc[b["test_start"]]),
                            "required_fit": 80, "status": "INSUFFICIENT_DATA" if len(train) < 80 else "ELIGIBLE", "reason": reason})
        if horizon == 1:
            h1_model, evidence = attempt(train, valid, columns, config)
            write_json(output / "logistic-attempt.json", evidence)
            for fold, (start, end) in enumerate(walk_forward_windows(b["train_end"], 5)):
                fit = window(samples, 0, start, bars.available_at.iloc[start])
                held = window(samples, start, end, bars.available_at.iloc[end])
                assert_purged(fit, bars.available_at.iloc[start])
                _, info = attempt(fit, held, columns, config)
                rolling.append({"fold": fold, "fit_n": len(fit), "validation_n": len(held), "start": start, "end": end, **info})
    write_json(output / "readiness.json", eligibility)
    write_json(output / "fit-indices.json", indices)
    write_json(output / "walk-forward.json", rolling)
    if h1_model is not None:
        joblib.dump(h1_model, output / "daily-h1-logistic.joblib")
    frozen_files = {"run.py": sha256(__file__), "config.json": sha256(output / "config.json"), "fit-indices.json": sha256(output / "fit-indices.json"),
                    "daily_source": sha256(source_file(config, 0)), "minute_source": sha256(source_file(config, 1))}
    component_hashes = {p.name: sha256(p) for p in (PROJECT / "src").glob("*.py")}
    write_json(output / "frozen.json", {"status": "FROZEN_BEFORE_TEST_METRICS", "files": frozen_files, "components": component_hashes,
                                       "selected_horizon": 1, "model_status": "INSUFFICIENT_DATA" if h1_model is None else "FITTED_RESEARCH_ONLY"})
    assert sha256(__file__) == frozen_files["run.py"] and sha256(output / "config.json") == frozen_files["config.json"]
    with (output / "test-unlocked.json").open("x", encoding="utf-8") as handle:
        json.dump({"status": "RETROSPECTIVE_BASELINE_EVALUATION", "fresh_blind_test": False}, handle)
    samples = samples_for(bars, features, make_labels(bars, 1), 64)
    predictions, scores, distributions = [], [], []
    for split, start, end in (("train", 0, 105), ("validation", 105, 127), ("test", 127, 150)):
        cutoff = bars.available_at.iloc[end] if end < len(bars) else pd.Timestamp.max
        data = samples.loc[samples.bar_position.ge(start) & samples.bar_position.lt(end) & samples.feature_ready].copy()
        count = summary(samples, start, end, cutoff)
        distributions.append({"split": split, **count})
        scored = data.y.notna() & data.target_available_at.lt(cutoff)
        for name in BASELINES + (["logistic"] if h1_model is not None else []):
            p = baseline_probability(data, name) if name != "logistic" else h1_model.predict_proba(data[columns])[:, 1]
            record = data[["bar_position", "available_at", "close", "target_available_at", "target_position", "y", "ret", "label_status"]].copy()
            record["split"], record["model"] = split, name
            record["direction"] = np.where(p >= .5, "up", "down")
            record["score_up"] = np.asarray(p, dtype=float)
            record["scored"] = scored
            predictions.append(record)
            score = metrics(data.loc[scored, "y"], np.asarray(p)[scored.to_numpy()])
            correct = int(((np.asarray(p)[scored.to_numpy()] >= .5) == data.loc[scored, "y"].to_numpy(int)).sum())
            assert abs(score["accuracy"] - correct / int(scored.sum())) < 1e-12
            scores.append({"split": split, "model": name, "forecast_count": len(data), "correct": correct,
                           "probability_status": "deterministic_rule_not_calibrated" if name != "logistic" else "raw_not_calibrated", **score})
    pd.concat(predictions).to_csv(output / "predictions.csv", index=False)
    pd.DataFrame(scores).to_csv(output / "model-comparison.csv", index=False)
    write_json(output / "metrics.json", scores)
    write_json(output / "label-distribution.json", distributions)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    regression = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=PROJECT,
                                env=env, capture_output=True, encoding="utf-8")
    (output / "legacy-regression.txt").write_text(regression.stdout + regression.stderr, encoding="utf-8")
    assert regression.returncode == 0
    after = protected_files()
    assert before == after, "既有工程或原始数据变动，停止并保留证据"
    write_json(output / "preservation.json", {"status": "PASS", "protected_files": len(before), "modified": [], "deleted": [], "added_outside_study": [],
                                              "legacy_regression_exit": regression.returncode, "legacy_regression_tests": 26})
    write_json(output / "result.json", {"status": "RESEARCH_COMPLETE_WITH_INSUFFICIENT_DATA", "daily_rows": 150,
                                        "logistic_status": "INSUFFICIENT_DATA" if h1_model is None else "FITTED_RESEARCH_ONLY",
                                        "model_file_created": h1_model is not None, "readiness": eligibility, "baseline_test_metrics": [s for s in scores if s["split"] == "test"],
                                        "fresh_blind_test": False, "reliable_probability_claim": False, "real_time_claim": False, "formal_delivery": False,
                                        "legacy_preserved": True})
    print(json.dumps({"study": str(STUDY), "status": "RESEARCH_COMPLETE_WITH_INSUFFICIENT_DATA", "h1_training_samples": eligibility[0]["training"]["binary_samples"],
                      "required_fit": 80, "model_created": h1_model is not None, "baseline_test_metrics": [s for s in scores if s["split"] == "test"],
                      "protected_files": len(before)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
