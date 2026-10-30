import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_loader import canonicalize, load_data


def frame(closes=(100, 99, 98, 97, 96, 95, 94), start="2026-10-20 09:31"):
    close = pd.Series(closes, dtype=float)
    opened = close.shift().fillna(close.iloc[0])
    return pd.DataFrame({"timestamp": pd.date_range(start, periods=len(close), freq="min"), "open": opened,
                         "high": pd.concat([opened, close], axis=1).max(axis=1) + 1,
                         "low": pd.concat([opened, close], axis=1).min(axis=1) - 1,
                         "close": close, "volume": 10., "raw_position": range(len(close))})


class DataTests(unittest.TestCase):
    def test_confirmed_weekend_closures_rejected(self):
        for start in ("2026-10-25 09:31", "2026-10-24 19:01"):
            with self.subTest(start=start):
                with self.assertRaises(ValueError): canonicalize(frame((100,), start), 1)

    def test_three_formats_and_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = frame().drop(columns="raw_position")
            for ext in ("csv", "xlsx", "parquet"):
                p = Path(tmp) / f"bars.{ext}"
                data = original.rename(columns={"timestamp": "时间", "open": "开盘", "high": "最高", "low": "最低", "close": "收盘", "volume": "成交量"})
                if ext == "csv": data.to_csv(p, index=False, encoding="utf-8-sig")
                elif ext == "xlsx": data.to_excel(p, index=False)
                else: data.to_parquet(p, index=False)
                actual = load_data(p)
                self.assertEqual(actual.close.tolist(), original.close.tolist())
                self.assertEqual(actual.timestamp.tolist(), original.timestamp.tolist())

    def test_bad_input_is_rejected(self):
        cases = [frame().drop(columns="volume"), frame().assign(close=float("nan")),
                 frame().assign(high=1), frame().assign(volume=-1), frame().iloc[::-1],
                 pd.concat([frame(), frame().iloc[[0]]]), frame().assign(timestamp="bad")]
        with tempfile.TemporaryDirectory() as tmp:
            for i, data in enumerate(cases):
                with self.subTest(i=i):
                    p = Path(tmp) / "invalid.csv"
                    data.to_csv(p, index=False)
                    with self.assertRaises(ValueError): load_data(p)

    def test_opening_event_merge_preserves_values(self):
        data = frame((100, 101), "2026-10-20 13:30")
        data.loc[0, ["open", "high", "low", "close"]] = 100
        clean, events = canonicalize(data, 1)
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean.volume.sum(), 20)
        self.assertEqual(clean.open.iloc[0], 100)
        self.assertEqual(clean.raw_positions.iloc[0], "0,1")
        self.assertEqual(len(events), 1)

    def test_incomplete_opening_event_stops(self):
        data = frame((100,), "2026-10-20 13:30")
        data.loc[0, ["open", "high", "low", "close"]] = 100
        with self.assertRaises(ValueError): canonicalize(data, 1)

    def test_short_bucket_availability(self):
        data = frame((100,), "2026-09-15 20:14")
        clean, _ = canonicalize(data, 15)
        self.assertEqual(str(clean.available_at.iloc[0]), "2026-09-15 20:15:00")
        self.assertEqual(str(clean.source_timestamp.iloc[0]), "2026-09-15 20:14:00")
        data = frame((100,), "2026-10-20 16:00")
        clean, _ = canonicalize(data, 60)
        self.assertEqual(str(clean.available_at.iloc[0]), "2026-10-20 16:00:00")
        self.assertEqual(str(clean.open_at.iloc[0]), "2026-10-20 15:30:00")

    def test_daily_not_available_at_midnight(self):
        minute = frame((100, 101), "2026-10-20 09:31")
        daily = frame((101,), "2026-10-20 00:00")
        clean, _ = canonicalize(daily, 0, minute)
        self.assertEqual(str(clean.available_at.iloc[0]), "2026-10-20 16:00:00")
        self.assertEqual(str(clean.open_at.iloc[0]), "2026-10-20 09:30:00")


if __name__ == "__main__":
    unittest.main()
