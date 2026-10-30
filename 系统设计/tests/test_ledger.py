from pathlib import Path
import sqlite3
import tempfile
import unittest

from realtime.ledger import Ledger, wilson


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "replay.sqlite3"
        self.now = 101000
        self.deployment = dict(id="replay-v1", source="SYNTHETIC", symbol="TEST",
                               mode="REPLAY", model_sha256="a" * 64)
        self.ledger = Ledger(self.path, self.deployment, clock=lambda: self.now)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.ledger.close())

    def publish(self, anchor=100000, p=.8, signal="wait"):
        return self.ledger.publish(anchor, 100, p, signal, anchor + 500, "b" * 64)

    def test_pending_hit_miss_flat(self):
        for i, (p, close, status) in enumerate([(.8, 101, "HIT"), (.8, 99, "MISS"),
                                               (.2, 99, "HIT"), (.2, 101, "MISS"), (.8, 100, "FLAT")]):
            anchor = 100000 + i * 60000
            self.now = anchor + 1000
            prediction = self.publish(anchor, p)
            self.assertEqual(self.ledger.summary()["PENDING"], 1)
            result = self.ledger.settle(prediction["id"], anchor + 60000, close, self.now + 60000)
            self.assertEqual(result["status"], status)
            self.assertTrue(result["target_started_at_publication"])
        summary = self.ledger.summary()
        self.assertEqual([summary[k] for k in ["HIT", "MISS", "FLAT", "PENDING"]], [2, 2, 1, 0])

    def test_full_denominator_and_signal_subset(self):
        for i in range(10):
            anchor = 100000 + i * 60000
            self.now = anchor + 1000
            p = self.publish(anchor, signal="up" if i < 3 else "wait")
            self.ledger.settle(p["id"], anchor + 60000, 101 if i < 6 else 99, self.now + 60000)
        summary = self.ledger.summary()
        self.assertEqual(summary["scored"], 10)
        self.assertEqual(summary["hit_rate"], .6)
        self.assertEqual(summary["signal_scored"], 3)
        self.assertEqual(summary["signal_hit_rate"], 1)
        self.assertEqual(summary["signal_coverage"], .3)
        self.assertTrue(summary["effect_sample_insufficient"])
        self.assertEqual(wilson(6, 10), summary["wilson95"])

    def test_empty_denominator(self):
        self.assertIsNone(self.ledger.summary()["hit_rate"])
        self.assertIsNone(wilson(0, 0))
        low, high = wilson(6, 10)
        self.assertAlmostEqual(low, .3126737697, places=8)
        self.assertAlmostEqual(high, .8318196703, places=8)

    def test_recent_and_unknown_target_open_time(self):
        p=self.publish()
        self.assertEqual(self.ledger.recent()[0]['result']['status'],'PENDING')
        self.assertIsNone(self.ledger.recent()[0]['result']['target_started_at_publication'])
        self.ledger.settle(p['id'],280000,101,281000)
        recent=self.ledger.recent()[0]
        self.assertEqual(recent['result']['status'],'HIT')
        self.assertFalse(recent['result']['target_started_at_publication'])
        self.assertEqual(recent['publication']['published_at_ms'],101000)

    def test_missing_input_fingerprint_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.publish(100000,100,.8,'wait',100500,'')
        self.assertEqual(self.ledger.summary()['total'],0)

    def test_duplicate_restart_and_immutability(self):
        p = self.publish()
        self.assertEqual(self.publish()["id"], p["id"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.db.execute("UPDATE predictions SET payload='{}'")
        self.ledger.db.rollback()
        self.ledger.close()
        self.ledger = Ledger(self.path, self.deployment, clock=lambda: self.now)
        self.assertEqual(self.ledger.summary()["total"], 1)
        self.assertEqual(self.publish()["id"], p["id"])
        with self.assertRaises(ValueError):
            self.publish(p=.2)

    def test_late_and_known_target_do_not_score(self):
        self.now = 121000
        late = self.publish()
        self.ledger.settle(late["id"], 160000, 101, 161000)
        self.assertEqual(self.ledger.summary()["UNSCORABLE"], 1)
        self.now = 201000
        known = self.publish(200000)
        self.ledger.settle(known["id"], 200500, 101, 201500)
        self.assertEqual(self.ledger.summary()["UNSCORABLE"], 2)
        self.assertIsNone(self.ledger.summary()["hit_rate"])

    def test_unconfirmed_sequence_does_not_shift_target(self):
        p = self.publish()
        result = self.ledger.settle(p["id"], None, None, 161000, reason="MISSING_SEQUENCE")
        self.assertEqual(result["status"], "UNSCORABLE")
        self.assertIsNone(result["target_ms"])

    def test_result_revision_and_as_of(self):
        p = self.publish()
        first = self.ledger.settle(p["id"], 160000, 101, 161000)
        again = self.ledger.settle(p["id"], 160000, 101, 162000)
        self.assertEqual(first["revision"], again["revision"])
        second = self.ledger.settle(p["id"], 160000, 99, 163000)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(self.ledger.summary(as_of=161500)["hit_rate"], 1)
        self.assertEqual(self.ledger.summary()["hit_rate"], 0)
        self.assertEqual(self.ledger.summary()["revisions"], 1)

    def test_deployment_isolation_and_backup(self):
        self.publish()
        other = dict(self.deployment, id="replay-v2")
        with Ledger(self.path, other, clock=lambda: self.now) as ledger:
            self.assertEqual(ledger.summary()["total"], 0)
        with self.assertRaises(ValueError):
            Ledger(self.path, dict(self.deployment, source="OTHER"))
        backup = Path(self.temp.name) / "backup.sqlite3"
        self.ledger.backup(backup)
        with Ledger(backup, self.deployment) as restored:
            self.assertEqual(restored.summary()["total"], 1)
            self.assertEqual(restored.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_write_failure_cannot_publish(self):
        self.ledger.db.execute("PRAGMA query_only=ON")
        with self.assertRaises(sqlite3.OperationalError):
            self.publish()
        self.assertEqual(self.ledger.summary()["total"], 0)

    def test_boundaries_reject_bad_prediction_and_outcome(self):
        for p in [float("nan"), float("inf"), -.1, 1.1]:
            with self.subTest(p=p), self.assertRaises(ValueError):
                self.publish(p=p)
        with self.assertRaises(ValueError):
            self.publish(signal="down")
        p = self.publish()
        with self.assertRaises(ValueError):
            self.ledger.settle(p["id"], 160000, -1, 161000)
        with self.assertRaises(ValueError):
            self.ledger.settle(p["id"], 160000, 101, 159000)


if __name__ == "__main__":
    unittest.main()
