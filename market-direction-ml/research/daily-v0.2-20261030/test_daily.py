"""Focused checks on synthetic fixtures; real predictive ability is evaluated separately."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import run
from src.labels import make_labels
from src.validation import samples_for, window


def fixture(n=150):
    close = 100 + np.arange(n) * .03 + np.sin(np.arange(n))
    times = pd.date_range("2025-01-01", periods=n, freq="D") + pd.Timedelta(hours=16)
    return pd.DataFrame({"close": close, "available_at": times, "bar_position": np.arange(n)})


class DailyChecks(unittest.TestCase):
    def test_features_use_only_available_prefix(self):
        bars = fixture()
        original = run.features(bars)
        for end in (10, 90, 120):
            pd.testing.assert_frame_equal(original.iloc[:end], run.features(bars.iloc[:end]))
        altered = bars.copy()
        altered.loc[120:, "close"] *= 7
        pd.testing.assert_frame_equal(original.iloc[:120], run.features(altered).iloc[:120])

    def test_warmup_is_real_not_imputed(self):
        bars = fixture()
        feat = run.features(bars)
        self.assertEqual(feat.columns.tolist(), run.FEATURES)
        self.assertEqual(np.flatnonzero(feat.notna().all(axis=1))[0], 5)
        self.assertTrue(feat.iloc[:5].isna().any(axis=1).all())
        self.assertTrue(np.isfinite(feat.iloc[5:]).all().all())
        self.assertAlmostEqual(feat.return_3.iloc[5], bars.close.iloc[5] / bars.close.iloc[2] - 1)
        self.assertAlmostEqual(feat.volatility5.iloc[5], bars.close.pct_change(fill_method=None).iloc[1:6].std(ddof=1))

    def test_h1_flat_and_pending(self):
        bars = fixture(4)
        bars["close"] = [100., 101., 101., 99.]
        labels = make_labels(bars, 1)
        self.assertEqual(labels.label_status.tolist(), ["UP", "FLAT", "DOWN", "PENDING"])
        self.assertTrue(pd.isna(labels.y.iloc[1]))
        self.assertTrue(pd.isna(labels.y.iloc[-1]))

    def test_temporal_purge_and_holdout_mask(self):
        bars = fixture()
        labels = make_labels(bars, 1, bars.available_at.iloc[120])
        data = samples_for(bars, run.features(bars), labels, 5)
        training = window(data, 0, 90, bars.available_at.iloc[90])
        valid = window(data, 90, 105, bars.available_at.iloc[105])
        self.assertEqual(training.bar_position.tolist(), list(range(5, 89)))
        self.assertEqual(valid.bar_position.tolist(), list(range(90, 104)))
        self.assertTrue(training.target_available_at.lt(bars.available_at.iloc[90]).all())
        self.assertTrue(data.loc[data.bar_position.ge(119), "y"].isna().all())

    def test_fit_gate_not_lowered(self):
        bars = fixture()
        data = samples_for(bars, run.features(bars), make_labels(bars, 1), 5)
        training = window(data, 0, 90, bars.available_at.iloc[90])
        columns = ["f_" + name for name in run.FEATURES]
        config = {"C": .1, "min_fit_samples": 80, "seed": run.SEED}
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_DATA"):
            run.gated_fit(training.iloc[:79], columns, config)
        single = training.copy()
        single["y"] = 1
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_DATA"):
            run.gated_fit(single, columns, config)
        model, info = run.gated_fit(training, columns, config)
        np.testing.assert_allclose(model[0].mean_, training[columns].mean().to_numpy(), rtol=1e-12)
        self.assertEqual(info["fit_n"], len(training))

    def test_validation_gate_and_baseline_tie(self):
        data = pd.DataFrame({"y": [0, 1] * 5, "f_return_1": [-.1, .1] * 5})
        self.assertEqual(run.score(data.iloc[:9], np.zeros(9))["status"], "UNABLE_TO_EVALUATE")
        self.assertEqual(run.score(data.assign(y=1), np.ones(10))["status"], "UNABLE_TO_EVALUATE")
        self.assertEqual(run.score(data, run.baseline(data, "previous_direction"))["accuracy"], 1.)
        self.assertEqual(run.baseline(pd.DataFrame({"f_return_1": [0]}), "previous_direction")[0], 1.)

    def test_counts_account_for_warmup_flat_purge(self):
        bars = fixture()
        bars.loc[20, "close"] = bars.close.iloc[19]
        data = samples_for(bars, run.features(bars), make_labels(bars, 1), 5)
        counts = run.segment(data, 0, 90, bars.available_at.iloc[90])
        self.assertEqual(counts["warmup"], 5)
        self.assertEqual(counts["flat"], 1)
        self.assertEqual(counts["purged"], 1)
        self.assertEqual(counts["binary_samples"], 83)

    def test_intervals_are_deterministic(self):
        self.assertEqual(run.paired_interval(np.ones(29)), [1., 1.])
        lo, hi = run.wilson(14, 29)
        self.assertLess(lo, 14 / 29)
        self.assertGreater(hi, 14 / 29)

    def test_existing_run_and_invalid_id_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            study = Path(temporary)
            (study / "runs" / "existing").mkdir(parents=True)
            with patch.object(run, "STUDY", study):
                with self.assertRaises(FileExistsError):
                    run.main("existing")
                with self.assertRaises(ValueError):
                    run.main("../outside")


if __name__ == "__main__":
    unittest.main(verbosity=2)
