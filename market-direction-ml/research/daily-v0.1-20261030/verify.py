"""Independently verify this run from original daily closes; writes only its own evidence."""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

STUDY = Path(__file__).resolve().parent
PROJECT = STUDY.parents[1]
RUN = STUDY / "run-01"


def main():
    raw = pd.read_csv(PROJECT.parent / "2026-10-28/日线.csv", encoding="utf-8-sig")
    pred = pd.read_csv(RUN / "predictions.csv")
    records = json.loads((RUN / "metrics.json").read_text(encoding="utf-8"))
    close = raw["收盘"].to_numpy(float)
    for row in pred.itertuples():
        i = int(row.bar_position)
        direction = 1 if row.model == "always_up" else 0 if row.model == "always_down" else int(close[i] >= close[i - (1 if row.model == "previous_direction" else 5)])
        assert row.direction == ("up" if direction else "down") and row.close == close[i]
        if i + 1 == len(raw):
            assert row.label_status == "PENDING" and pd.isna(row.y) and not row.scored
        else:
            actual = close[i + 1] / close[i] - 1
            assert abs(row.ret - actual) < 1e-12
            if actual == 0:
                assert row.label_status == "FLAT" and pd.isna(row.y) and not row.scored
            else:
                assert row.y == int(actual > 0)
        end = {"train": 105, "validation": 127, "test": 150}[row.split]
        assert row.scored == bool(i + 1 < end and close[i + 1] != close[i])
    for record in records:
        part = pred[(pred.split == record["split"]) & (pred.model == record["model"]) & pred.scored]
        y, d = part.y.to_numpy(int), part.direction.eq("up").to_numpy(int)
        confusion = [[int(((y == a) & (d == b)).sum()) for b in (0, 1)] for a in (0, 1)]
        assert confusion == record["confusion_matrix"] and len(y) == record["n"]
        assert abs(float((y == d).mean()) - record["accuracy"]) < 1e-12
    counts = pred.groupby("split").size().to_dict()
    assert len(pred) == 344 and counts == {"train": 164, "validation": 88, "test": 92}
    assert not list(RUN.glob("*.joblib"))
    assert (RUN / "frozen.json").stat().st_mtime_ns <= (RUN / "test-unlocked.json").stat().st_mtime_ns <= (RUN / "metrics.json").stat().st_mtime_ns
    log = (RUN / "legacy-regression.txt").read_text(encoding="utf-8")
    assert "Ran 26 tests" in log and re.search(r"\nOK\s*$", log)
    preservation = json.loads((RUN / "preservation.json").read_text(encoding="utf-8"))
    assert preservation["status"] == "PASS" and preservation["modified"] == [] and preservation["deleted"] == []
    result = {"status": "PASS", "independent_prediction_checks": len(pred), "metric_groups_checked": len(records),
              "forecast_rows_per_split_all_four_baselines": counts, "no_logistic_model_fabricated": True,
              "freeze_precedes_test_metrics": True, "legacy_regression": "26 passed", "legacy_protected_files": preservation["protected_files"]}
    (RUN / "independent-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
