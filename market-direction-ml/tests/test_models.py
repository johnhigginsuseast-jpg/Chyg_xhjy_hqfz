import unittest
import json

import numpy as np
import pandas as pd

from src.common import ROOT, load_config, sha256
from src.evaluate import metrics, select_threshold
from src.train import CANDIDATES, fit_model, run_training


class ModelTests(unittest.TestCase):
    def test_existing_run_is_not_overwritten(self):
        run = ROOT / "reports/evidence/study-20261028-v1"
        if not (run / "frozen.json").exists():
            self.skipTest("需要已完成真实训练的现存实验，用于保存恢复验收")
        model = ROOT / "models/study-20261028-v1/3min-h1-logistic.joblib"
        before = sha256(model)
        with self.assertRaises(FileExistsError): run_training(load_config(), "study-20261028-v1")
        self.assertEqual(sha256(model), before)

    def test_metrics_and_probability_validation(self):
        result = metrics([0, 1, 1, 0], [.1, .8, .4, .7], .7)
        self.assertEqual(result["accuracy"], .5)
        self.assertEqual(result["confusion_matrix"], [[1, 1], [1, 1]])
        self.assertEqual(result["signal_coverage"], .75)
        self.assertAlmostEqual(result["brier"], (.01 + .04 + .36 + .49) / 4)
        self.assertIsNone(metrics([1, 1], [.7, .8])["auc"])
        with self.assertRaises(ValueError): metrics([1], [float("nan")])
        with self.assertRaises(ValueError): metrics([1], [1.5])

    def test_all_four_real_estimators_inner_stop(self):
        n = 160
        x = np.arange(n)
        training = pd.DataFrame({"f_x": np.sin(x), "f_z": np.cos(x / 2), "y": (np.sin(x) > 0).astype(int),
                                 "available_at": pd.date_range("2026-01-01", periods=n, freq="min"),
                                 "target_available_at": pd.date_range("2026-01-01 00:01", periods=n, freq="min"),
                                 "bar_position": x})
        config = load_config()
        for kind, candidates in CANDIDATES.items():
            with self.subTest(kind=kind):
                model, info = fit_model(kind, candidates[0], training, ["f_x", "f_z"], config)
                p = model.predict_proba(training[["f_x", "f_z"]])
                self.assertTrue(np.isfinite(p).all())
                self.assertLess(np.max(np.abs(p.sum(axis=1) - 1)), 1e-8)
                self.assertEqual(info["fit_n"], n)
                if kind != "logistic":
                    self.assertLess(pd.Timestamp(info["inner_early_stop"]["core_max_target"]),
                                    pd.Timestamp(info["inner_early_stop"]["boundary"]))

    def test_threshold_only_uses_supplied_validation(self):
        config = load_config()
        threshold = select_threshold(np.tile([0, 1], 40), np.tile([.1, .9], 40), config)
        self.assertIn(threshold, config["thresholds"])
        self.assertEqual(select_threshold([0, 1], [.4, .6], config), .5)


if __name__ == "__main__":
    unittest.main()
