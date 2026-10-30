"""Append-only forward ledger, versioned results, and independently scorable totals."""
import hashlib
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
import time


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def wilson(hits, n):
    if not 0 <= hits <= n:
        raise ValueError("Invalid hit/sample counts")
    if not n:
        return None
    z = 1.959963984540054
    p, d = hits / n, 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0, center - radius), min(1, center + radius)]


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return value


class Ledger:
    def __init__(self, path, deployment, clock=None):
        if deployment.get("mode") not in ("LIVE", "REPLAY"):
            raise ValueError("Deployment must explicitly identify LIVE or REPLAY")
        for key in ("id", "source", "symbol", "model_sha256"):
            if not deployment.get(key):
                raise ValueError(f"Missing deployment {key}")
        self.deployment = dict(deployment)
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.db = sqlite3.connect(Path(path), timeout=5)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS deployments(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS predictions(
                id TEXT PRIMARY KEY, deployment TEXT NOT NULL REFERENCES deployments(id),
                anchor_ms INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(deployment, anchor_ms));
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY, deployment TEXT NOT NULL REFERENCES deployments(id),
                kind TEXT NOT NULL, at_ms INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settlements(
                prediction TEXT NOT NULL REFERENCES predictions(id), revision INTEGER NOT NULL,
                at_ms INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(prediction, revision));
            CREATE TABLE IF NOT EXISTS bars(
                deployment TEXT NOT NULL REFERENCES deployments(id), ts INTEGER NOT NULL,
                revision INTEGER NOT NULL, received_ms INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(deployment,ts,revision));
            CREATE INDEX IF NOT EXISTS event_deployment ON events(deployment, kind, at_ms);
        """)
        for table in ("deployments", "predictions", "events", "settlements", "bars"):
            for action in ("UPDATE", "DELETE"):
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS no_{action}_{table} BEFORE {action} ON {table} "
                                "BEGIN SELECT RAISE(ABORT, 'Append-only ledger'); END")
        old = self.db.execute("SELECT payload FROM deployments WHERE id=?", (deployment["id"],)).fetchone()
        if old and old[0] != canonical(deployment):
            self.db.close()
            raise ValueError("Deployment id already belongs to a different frozen configuration")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO deployments VALUES(?,?)", (deployment["id"], canonical(deployment)))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.db.close()

    def event(self, kind, payload, at_ms=None):
        with self.db:
            self.db.execute("INSERT INTO events(deployment,kind,at_ms,payload) VALUES(?,?,?,?)",
                            (self.deployment["id"], kind, self.clock() if at_ms is None else at_ms, canonical(payload)))

    def publish(self, anchor_ms, base_close, p_up, signal, computed_at_ms, input_sha256):
        if number(base_close) <= 0 or not 0 <= number(p_up) <= 1 or number(anchor_ms) > number(computed_at_ms):
            raise ValueError("Invalid prediction values or chronology")
        direction = "up" if p_up >= .5 else "down"
        if signal not in (direction, "wait"):
            raise ValueError("Signal must retain the frozen model's direction")
        if not isinstance(input_sha256,str) or len(input_sha256)!=64 or any(c not in '0123456789abcdef' for c in input_sha256):
            raise ValueError("Expected an input SHA256")
        payload = dict(anchor_ms=anchor_ms, base_close=base_close, p_up=p_up, p_down=1-p_up,confidence=max(p_up,1-p_up),
                       predicted_direction=direction, signal=signal, horizon=1,
                       computed_at_ms=computed_at_ms, input_sha256=input_sha256)
        identity = hashlib.sha256(canonical([self.deployment["id"], anchor_ms, 1]).encode()).hexdigest()
        old = self.db.execute("SELECT payload FROM predictions WHERE id=?", (identity,)).fetchone()
        if old:
            if json.loads(old[0]) != payload:
                raise ValueError("Anchor already has a different prediction; retain original and log the revision")
            receipt = self._receipt(identity)
            if receipt is None:
                raise ValueError("Stored prediction has no publication receipt; cannot backdate a retry")
            return dict(payload, id=identity, **receipt)
        with self.db:
            self.db.execute("INSERT INTO predictions VALUES(?,?,?,?)",
                            (identity, self.deployment["id"], anchor_ms, canonical(payload)))
        # Timestamp after the prediction commit; never use the anchor as its publication time.
        published = self.clock()
        eligible = computed_at_ms <= published and 0 <= published-anchor_ms <= 20000
        receipt = dict(prediction=identity, published_at_ms=published, eligible=eligible,
                       reason=None if eligible else "LATE_OR_CLOCK_ERROR")
        self.event("PUBLISHED", receipt, published)
        return dict(payload, id=identity, **receipt)

    def _receipt(self, prediction):
        for (payload,) in self.db.execute("SELECT payload FROM events WHERE deployment=? AND kind='PUBLISHED' ORDER BY id DESC",
                                          (self.deployment["id"],)):
            value = json.loads(payload)
            if value["prediction"] == prediction:
                return value
        return None

    def forecasts(self):
        return [dict(json.loads(payload), id=identity) for identity,payload in
                self.db.execute("SELECT id,payload FROM predictions WHERE deployment=? ORDER BY anchor_ms", (self.deployment["id"],))]

    def bars(self):
        latest = {}
        for ts,revision,payload in self.db.execute("SELECT ts,revision,payload FROM bars WHERE deployment=? ORDER BY revision DESC",
                                                 (self.deployment["id"],)):
            latest.setdefault(ts, (revision, json.loads(payload)))
        return latest

    def save_bars(self, rows, received_ms):
        current, changes = self.bars(), []
        for row in rows:
            old = current.get(row["ts"])
            if old is None or old[1] != row:
                changes.append((self.deployment["id"], row["ts"], old[0]+1 if old else 1, received_ms, canonical(row)))
        with self.db:
            self.db.executemany("INSERT INTO bars VALUES(?,?,?,?,?)", changes)
        return len(changes)

    def settle(self, prediction, target_ms, target_close, at_ms, reason=None):
        row = self.db.execute("SELECT payload FROM predictions WHERE id=? AND deployment=?",
                              (prediction, self.deployment["id"])).fetchone()
        if row is None:
            raise ValueError("Prediction does not belong to this deployment")
        p, receipt = json.loads(row[0]), self._receipt(prediction)
        if reason is None:
            if target_ms is None or number(target_close) <= 0 or target_ms <= p["anchor_ms"] or at_ms < target_ms:
                raise ValueError("Outcome is invalid, not a future target, or not yet available")
        if not receipt or not receipt["eligible"]:
            reason = "UNPUBLISHED_OR_LATE"
        elif target_ms is not None and receipt["published_at_ms"] >= target_ms:
            reason = "RESULT_KNOWN_AT_PUBLICATION"
        if reason:
            status = "UNSCORABLE"
        elif target_close == p["base_close"]:
            status = "FLAT"
        else:
            direction = "up" if target_close > p["base_close"] else "down"
            status = "HIT" if direction == p["predicted_direction"] else "MISS"
        target_open = target_ms-60000 if target_ms is not None else None
        value = dict(status=status, target_ms=target_ms, target_close=target_close, reason=reason,
                     target_open_ms=target_open,
                     target_started_at_publication=(receipt["published_at_ms"] >= target_open) if receipt and target_open is not None else None)
        previous = self.db.execute("SELECT revision,at_ms,payload FROM settlements WHERE prediction=? ORDER BY revision DESC LIMIT 1",
                                   (prediction,)).fetchone()
        if previous:
            old = json.loads(previous[2])
            if all(old[k] == v for k, v in value.items()):
                return old
            if at_ms < previous[1]:
                raise ValueError("Settlement revision cannot precede previous evidence")
        value["revision"] = previous[0]+1 if previous else 1
        with self.db:
            self.db.execute("INSERT INTO settlements VALUES(?,?,?,?)",
                            (prediction, value["revision"], at_ms, canonical(value)))
        return value

    def recent(self, limit=7):
        rows=[]
        for prediction in self.forecasts()[-limit:][::-1]:
            receipt=self._receipt(prediction["id"])
            result=self.db.execute("SELECT payload FROM settlements WHERE prediction=? ORDER BY revision DESC LIMIT 1",(prediction["id"],)).fetchone()
            rows.append(dict(prediction,publication=receipt,
                             result=json.loads(result[0]) if result else {"status":"PENDING" if receipt and receipt["eligible"] else "UNSCORABLE",
                                                                         "target_started_at_publication":None}))
        return rows

    def summary(self, as_of=None, since=None):
        as_of = 2**63-1 if as_of is None else as_of
        receipts = {}
        for (payload,) in self.db.execute("SELECT payload FROM events WHERE deployment=? AND kind='PUBLISHED' ORDER BY id",
                                          (self.deployment["id"],)):
            r = json.loads(payload)
            receipts[r["prediction"]] = r
        results = {}
        for prediction, payload in self.db.execute("SELECT s.prediction,s.payload FROM settlements s JOIN predictions p ON p.id=s.prediction "
                                                   "WHERE p.deployment=? AND s.at_ms<=? ORDER BY s.revision DESC",
                                                   (self.deployment["id"], as_of)):
            results.setdefault(prediction, json.loads(payload))
        counts = dict.fromkeys(("HIT", "MISS", "FLAT", "PENDING", "UNSCORABLE"), 0)
        signal_hits = signal_n = signal_total = revisions = late = 0
        for identity, payload in self.db.execute("SELECT id,payload FROM predictions WHERE deployment=?", (self.deployment["id"],)):
            p, receipt = json.loads(payload), receipts.get(identity)
            when = receipt["published_at_ms"] if receipt else p["computed_at_ms"]
            if when > as_of or (since is not None and when < since):
                continue
            status = results.get(identity, {}).get("status", "PENDING")
            if not receipt or not receipt["eligible"]:
                status = "UNSCORABLE"
                late += 1
            counts[status] += 1
            signal_total += p["signal"] != "wait"
            revisions += max(0, results.get(identity, {}).get("revision", 1)-1)
            if status in ("HIT", "MISS") and p["signal"] != "wait":
                signal_n += 1
                signal_hits += status == "HIT"
        n = counts["HIT"] + counts["MISS"]
        total = sum(counts.values())
        event_counts = dict(self.db.execute("SELECT kind,COUNT(*) FROM events WHERE deployment=? AND at_ms<=? AND at_ms>=? GROUP BY kind",
                                           (self.deployment["id"],as_of,since if since is not None else 0)))
        return dict(counts, total=total, scored=n, hit_rate=counts["HIT"]/n if n else None,
                    wilson95=wilson(counts["HIT"], n), signal_scored=signal_n,
                    signal_hit_rate=signal_hits/signal_n if signal_n else None,
                    signal_coverage=signal_n/n if n else None, revisions=revisions, late=late,
                    signal_total=signal_total,signal_coverage_all_predictions=signal_total/total if total else None,
                    rule_skip_events=event_counts.get("RULE_SKIP",0),backfill_events=event_counts.get("BACKFILL_ONLY",0),
                    source_state_events=event_counts.get("SOURCE_STATE",0),
                    effect_sample_insufficient=n < 500, mode=self.deployment["mode"])

    def backup(self, path):
        target = Path(path).resolve()
        if target.exists():
            raise ValueError("Backup must use a new filename")
        with closing(sqlite3.connect(target)) as destination:
            self.db.backup(destination)
