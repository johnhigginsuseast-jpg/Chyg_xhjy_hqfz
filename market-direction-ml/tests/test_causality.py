import unittest

import numpy as np
import pandas as pd

from src.features import make_features
from src.labels import filter_bars, make_labels
from src.validation import assert_purged, boundaries, samples_for, window
from test_data import frame


def bars(closes):
    data = frame(closes)
    data["available_at"] = data.timestamp
    data["bar_position"] = range(len(data))
    return data


class CausalityTests(unittest.TestCase):
    def test_three_then_two_and_reference(self):
        data = bars([100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89])
        accepted, ledger, state = filter_bars(data, 1)
        self.assertEqual(accepted.close.tolist(), [100, 99, 98, 97, 94, 93, 92, 89])
        self.assertEqual(ledger.status.eq("rule_skip").sum(), 4)
        label = make_labels(accepted, 1)
        self.assertAlmostEqual(label.ret.iloc[3], 94 / 97 - 1)

    def test_skip_values_do_not_enter_features(self):
        data = bars([100, 99, 98, 97, 96, 95, 94, 95])
        a, _, _ = filter_bars(data, 1)
        data.loc[[4, 5], ["open", "high", "low", "close", "volume"]] = 99999
        b, _, _ = filter_bars(data, 1)
        pd.testing.assert_frame_equal(make_features(a), make_features(b))

    def test_flat_resets_run(self):
        accepted, ledger, _ = filter_bars(bars([100, 99, 98, 98, 97, 96]), 1)
        self.assertEqual(len(accepted), 6)
        self.assertFalse(ledger.status.eq("rule_skip").any())

    def test_streaming_state_matches_batch(self):
        data = bars([100, 99, 98, 97, 96, 95, 94, 93])
        whole, _, expected = filter_bars(data, 1)
        first, _, state = filter_bars(data.iloc[:5], 1)
        second, _, state = filter_bars(data.iloc[5:], 1, state)
        self.assertEqual(pd.concat([first, second]).close.tolist(), whole.close.tolist())
        self.assertEqual(state, expected)

    def test_horizons_flat_and_pending(self):
        data = bars([100, 101, 100, 99, 102, 100, 105, 106, 107, 108, 109, 110])
        for horizon in (1, 3, 5, 10):
            label = make_labels(data, horizon)
            self.assertEqual(label.label_status.iloc[-horizon:].tolist(), ["PENDING"] * horizon)
            self.assertAlmostEqual(label.ret.iloc[0], data.close.iloc[horizon] / 100 - 1)
        self.assertEqual(make_labels(data, 5).label_status.iloc[0], "FLAT")

    def test_prefix_features_are_causal(self):
        data = bars(100 + np.sin(np.arange(240)) + np.arange(240) / 100)
        full = make_features(data)
        for end in (65, 110, 180):
            pd.testing.assert_frame_equal(full.iloc[:end], make_features(data.iloc[:end].copy()))
        changed = data.copy()
        changed.loc[180:, ["open", "high", "low", "close", "volume"]] *= 5
        pd.testing.assert_frame_equal(full.iloc[:180], make_features(changed).iloc[:180])

    def test_purge_actual_future_time(self):
        data = bars(100 - np.arange(180) / 10)
        accepted, _, _ = filter_bars(data, 1)
        features = pd.DataFrame({"test": np.ones(len(accepted))})
        samples = samples_for(accepted, features, make_labels(accepted, 10), 0)
        cutoff = data.available_at.iloc[100]
        train = window(samples, 0, 100, cutoff)
        assert_purged(train, cutoff)
        self.assertTrue(train.target_position.lt(100).all())
        with self.assertRaises(ValueError): assert_purged(samples[samples.bar_position < 100], cutoff)
        self.assertEqual(boundaries(data)["test_start"], 153)


if __name__ == "__main__":
    unittest.main()
