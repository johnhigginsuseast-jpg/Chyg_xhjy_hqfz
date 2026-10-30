"""Compare two independent complete training runs, without opening repeat-test labels."""
import argparse
import json

import numpy as np
import pandas as pd

from src.common import ROOT, period_name, sha256, write_json
from src.predict import load_bundle, model_probability
from src.train import prepared


def verify(first_id, second_id):
    first, second = [ROOT / "reports/evidence" / r for r in (first_id, second_id)]
    config = json.loads((first / "config.json").read_text(encoding="utf-8"))
    assert sha256(first / "config.json") == sha256(second / "config.json")
    for name in ("candidate-grid.json", "feature-info.json", "fit-index-audit.json", "pretest-label-distribution.csv", "walk-forward.csv"):
        assert sha256(first / name) == sha256(second / name), name
    assert not (second / "final-test-started.json").exists()
    a, b = [json.loads((p / "decisions.json").read_text(encoding="utf-8")) for p in (first, second)]
    assert len(a) == len(b)
    by_key = {(r["period"], r["horizon"], r["model"]): r for r in b}
    checked = []
    for period in config["periods"]:
        raw, kept, features, _, _ = prepared(config, period)
        validation = kept.bar_position.ge(int(len(raw) * .7)) & kept.bar_position.lt(int(len(raw) * .85))
        inputs = features.loc[validation].add_prefix("f_")
        assert sha256(first / f"{period_name(period)}-coverage.csv") == sha256(second / f"{period_name(period)}-coverage.csv")
        for original in [r for r in a if r["period"] == period]:
            repeated = by_key[(period, original["horizon"], original["model"])]
            for field in ("status", "candidate", "params", "threshold", "validation", "raw_validation"):
                assert original.get(field) == repeated.get(field), (period, original["horizon"], original["model"], field)
            if "model_path" not in original:
                continue
            one, two = [load_bundle(ROOT / r["model_path"]) for r in (original, repeated)]
            assert one["training_rule_state"] == two["training_rule_state"]
            difference = float(np.max(np.abs(model_probability(one, inputs).astype(float) - model_probability(two, inputs).astype(float))))
            raw_difference = float(np.max(np.abs(model_probability(one, inputs, False).astype(float) - model_probability(two, inputs, False).astype(float))))
            assert difference <= 1e-8 and raw_difference <= 1e-8
            checked.append({"period": period, "horizon": original["horizon"], "model": original["model"],
                            "validation_forecasts": len(inputs), "max_probability_difference": difference, "max_raw_difference": raw_difference})
    result = {"status": "PASS", "first": first_id, "second": second_id, "decision_cases": len(a),
              "model_cases": len(checked), "identical_walk_forward_and_selection": True,
              "identical_splits_labels_coverage": True, "repeat_test_opened": False,
              "max_probability_difference": max(r["max_probability_difference"] for r in checked), "checks": checked}
    write_json(first / "reproducibility.json", result)
    print(json.dumps({k: result[k] for k in ("status", "decision_cases", "model_cases", "max_probability_difference", "repeat_test_opened")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    args = parser.parse_args()
    verify(args.first, args.second)
