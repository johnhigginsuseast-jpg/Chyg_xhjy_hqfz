import json
import csv
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.common import ROOT, load_config, sha256, write_json
from src.data_loader import canonicalize, load_data
from src.features import make_features
from src.final_report import paired_block_comparison, prediction_frame
from src.predict import load_bundle, predict_history


class DeliveryTests(unittest.TestCase):
    def test_float32_probability_export_round_trip(self):
        timestamps = pd.date_range("2026-01-01", periods=3, freq="min")
        data = pd.DataFrame({"available_at": timestamps, "source_timestamp": timestamps, "open_at": timestamps,
                             "open": 100., "close": 100., "bar_position": range(3), "raw_positions": ["0", "1", "2"],
                             "target_available_at": timestamps, "target_position": range(3), "y": [0, 1, 1],
                             "ret": 0., "label_status": "UP", "market_state": "fixture"})
        p = np.asarray([.47000002, .60000002, .55000001], dtype=np.float32)
        exported = prediction_frame(data, p, p, .55, 1, "synthetic-fixture")
        records = list(csv.DictReader(io.StringIO(exported.to_csv(index=False))))
        for i, record in enumerate(records):
            self.assertAlmostEqual(float(record["p_up"]) + float(record["p_down"]), 1., places=12)
            self.assertEqual(float(record["p_up"]), float(p[i]))

    def test_paired_blocks_have_valid_interval(self):
        timestamps = pd.Series(pd.date_range("2026-01-01", periods=200, freq="3h"))
        result = paired_block_comparison(np.tile([0, 1], 100), np.tile([.1, .9], 100), np.ones(200), timestamps, load_config())
        self.assertEqual(result["accuracy_difference"], .5)
        self.assertLessEqual(result["ci_low"], result["ci_high"])
        self.assertGreaterEqual(result["p_exploratory"], 0)

    def test_saved_model_cli_replay_and_invalid_input(self):
        (ROOT / "models").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "models") as tmp:
            tmp = Path(tmp)
            times = pd.date_range("2026-10-20 09:33", "2026-10-20 11:30", freq="3min").append(pd.date_range("2026-10-20 13:33", "2026-10-20 16:00", freq="3min"))
            c = 100 + np.sin(np.arange(len(times)))
            data = pd.DataFrame({"timestamp": times, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 10})
            data_path = tmp / "synthetic.csv"
            data.to_csv(data_path, index=False)
            bars, _ = canonicalize(load_data(data_path), 3)
            f = make_features(bars).add_prefix("f_")
            usable = f.iloc[64:]
            model = make_pipeline(StandardScaler(), LogisticRegression()).fit(usable, np.arange(len(usable)) % 2)
            bundle = {"estimator": model, "calibrator": None, "feature_columns": list(f.columns), "period": 3,
                      "horizon": 1, "warmup": 64, "threshold": .6, "source_identity": "synthetic-test-only", "model_version": "fixture"}
            path = tmp / "fixture.joblib"
            joblib.dump(bundle, path)
            write_json(path.with_suffix(".json"), {"sha256": sha256(path)})
            result = predict_history(path, data_path, "2026-10-20 16:00", "synthetic-test-only")
            self.assertAlmostEqual(result["p_up"], model.predict_proba(f.iloc[[-1]])[0, 1])
            command = [sys.executable, "-X", "utf8", "-m", "src.predict", "--model", str(path), "--input", str(data_path),
                       "--as-of", "2026-10-20 16:00", "--source-identity", "synthetic-test-only"]
            child = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", check=True)
            self.assertAlmostEqual(json.loads(child.stdout)["p_up"], result["p_up"])
            with self.assertRaises(ValueError): predict_history(path, data_path, "2026-10-20 15:59", "synthetic-test-only")
            with self.assertRaises(ValueError): predict_history(path, data_path, "2026-10-20 16:00", "wrong-source")
            wrong_period = data.copy()
            wrong_period.timestamp = pd.date_range("2026-10-20 09:31", periods=len(data), freq="min")
            wrong_path = tmp / "wrong-period.csv"
            wrong_period.to_csv(wrong_path, index=False)
            with self.assertRaises(ValueError): predict_history(path, wrong_path, "2026-10-20 16:00", "synthetic-test-only")
            with path.open("ab") as handle: handle.write(b"corrupt")
            with self.assertRaises(ValueError): load_bundle(path)


if __name__ == "__main__":
    unittest.main()
