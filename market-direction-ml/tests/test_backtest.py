import unittest

import numpy as np
import pandas as pd

from src.backtest import simulate


def fixture():
    bars = pd.DataFrame({"open_at": pd.date_range("2026-01-01 09:30", periods=5, freq="min"),
                         "available_at": pd.date_range("2026-01-01 09:31", periods=5, freq="min"),
                         "open": [100., 100., 100., 110., 120.], "close": [100., 100., 105., 110., 120.],
                         "bar_position": range(5)})
    prediction = pd.DataFrame({"prediction_timestamp": pd.to_datetime(["2026-01-01 09:31", "2026-01-01 09:33"]), "signal": ["up", "down"]})
    return bars, prediction


class BacktestTests(unittest.TestCase):
    def test_no_same_time_fill_and_hand_profit(self):
        bars, prediction = fixture()
        result, equity, fills, trades = simulate(bars, prediction, {"fee_bps": 0, "half_spread_bps": 0, "slippage_bps": 0})
        self.assertEqual(fills.timestamp.tolist(), [pd.Timestamp("2026-01-01 09:32"), pd.Timestamp("2026-01-01 09:34")])
        self.assertEqual(fills.side.tolist(), ["buy", "sell"])
        self.assertAlmostEqual(result["total_return"], .2)
        self.assertEqual(result["trade_count"], 1)
        self.assertAlmostEqual(result["average_win"], .2)
        self.assertIsNone(result["profit_factor"])

    def test_both_sides_fee_spread_slippage_hand_calculation(self):
        bars, prediction = fixture()
        result, _, fills, trades = simulate(bars, prediction, {"fee_bps": 10, "half_spread_bps": 10, "slippage_bps": 10})
        expected = (120 * .998 * .999) / (100 * 1.002 * 1.001) - 1
        self.assertAlmostEqual(result["total_return"], expected)
        self.assertEqual(len(fills), 2)
        self.assertGreater(result["total_fees"], 0)

    def test_no_trade_and_no_fake_exit(self):
        bars, prediction = fixture()
        cost = {"fee_bps": 0, "half_spread_bps": 0, "slippage_bps": 0}
        prediction.signal = "down"
        result, _, fills, trades = simulate(bars, prediction, cost)
        self.assertEqual(result["total_return"], 0)
        self.assertEqual(result["trade_count"], 0)
        self.assertIsNone(result["win_rate"])
        prediction.signal = "up"
        result, _, fills, trades = simulate(bars, prediction, cost)
        self.assertEqual(fills.side.tolist(), ["buy"])
        self.assertEqual(result["trade_count"], 0)
        self.assertGreater(result["open_position_units"], 0)

    def test_loss_drawdown_and_no_overlapping_capital(self):
        bars, prediction = fixture()
        bars.loc[4, ["open", "close"]] = 80
        result, equity, fills, trades = simulate(bars, prediction, {"fee_bps": 0, "half_spread_bps": 0, "slippage_bps": 0})
        self.assertAlmostEqual(result["total_return"], -.2)
        self.assertAlmostEqual(result["average_loss"], -.2)
        self.assertEqual(result["profit_factor"], 0)
        self.assertAlmostEqual(result["max_drawdown"], 1 - .8 / 1.1)
        self.assertTrue(((equity.cash == 0) | (equity.position_units == 0)).all())

    def test_invalid_costs_rejected(self):
        bars, prediction = fixture()
        for fee in (-1, float("nan"), 10000):
            with self.subTest(fee=fee):
                with self.assertRaises(ValueError): simulate(bars, prediction, {"fee_bps": fee, "half_spread_bps": 0, "slippage_bps": 0})


if __name__ == "__main__":
    unittest.main()
