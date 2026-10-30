"""Source-bound forward processing; bootstrap/backfill never creates historical forecasts."""
from datetime import datetime
import hashlib
import json

from .ledger import canonical
from .native import SHANGHAI, check_lineage, local_time
from .http_feed import SOURCE, SYMBOL, NAME, TIME_POLICY, BOUNDARY_POLICY


def trading_label(ts):
    wall = datetime.fromtimestamp(ts/1000, SHANGHAI)
    m = wall.hour*60 + wall.minute
    return wall.weekday() != 6 and (571 <= m <= 690 or 811 <= m <= 960 or (wall.weekday() < 5 and 1141 <= m <= 1260))


def missing_labels(start, end, available):
    return [t for t in range(start+60000,end+1,60000) if trading_label(t) and t not in available]


class Engine:
    def __init__(self, ledger, history, predictor):
        self.ledger, self.history, self.predictor = ledger, history, predictor
        self.known = {r["ts"]:r for r in history}
        self.known.update({ts:row for ts,(_,row) in ledger.bars().items()})
        restored_cursor = history[-1]["ts"]
        for kind,payload in ledger.db.execute("SELECT kind,payload FROM events WHERE deployment=? AND kind IN ('CURSOR','BOOTSTRAP') ORDER BY id", (ledger.deployment["id"],)):
            value = json.loads(payload)
            restored_cursor = max(restored_cursor,value.get("anchor",value.get("cursor",restored_cursor)))
        self.closed = {ts:row for ts,row in self.known.items() if ts <= restored_cursor and not row.get('quarantine_reason')}
        self.cursor = None
        self.prepared_cutoff = None
        self.prepared = None
        self.finality_observed = bool(ledger.db.execute("SELECT 1 FROM events WHERE deployment=? AND kind='END_LABEL_OBSERVED' LIMIT 1", (ledger.deployment["id"],)).fetchone())
        self.last_snapshot = None
        self.last_state = None

    def state(self, code, detail=None):
        value = dict(status=code, detail=detail)
        if value != self.last_state:
            self.ledger.event("SOURCE_STATE", value)
            self.last_state = value
        return value

    def idle(self, received_ms, latest):
        detail = dict(anchor=local_time(latest),age_seconds=max(0,received_ms-latest)/1000,
                      nominal_calendar_only=True)
        if trading_label(received_ms+60000) and received_ms-latest > 80000:
            return self.state("STALE_SOURCE",detail)
        return self.state("WAITING_NEW_COMPLETE_BAR" if trading_label(received_ms+60000) else "NOMINAL_REST",detail)

    def process(self, incoming, metadata, received_ms):
        if self.ledger.deployment["source"] == SOURCE:
            deployment = self.ledger.deployment
            if not (deployment.get("domain_shift_acknowledged") is True and deployment.get("research_only") is True
                    and deployment.get("time_policy") == TIME_POLICY
                    and deployment.get('boundary_policy') == BOUNDARY_POLICY
                    and metadata.get("source_id") == SOURCE and metadata.get("symbol") == SYMBOL
                    and metadata.get("name") == NAME and metadata.get("period") == 1
                    and metadata.get("time_policy") == TIME_POLICY and metadata.get('boundary_policy') == BOUNDARY_POLICY):
                raise ValueError("HTTP_RESEARCH_BINDING_REJECTED")
            if any(r.get("raw_ts") != r["ts"]-60000 for r in self.history+incoming):
                raise ValueError("HTTP_HISTORY_OR_TIME_POLICY_REJECTED")
            binding = dict(source=SOURCE,domain_shift_acknowledged=True,same_source_equivalence=False)
        else:
            binding = check_lineage(self.history, incoming)
        if any(received_ms < r["ts"] <= received_ms+60000 for r in incoming[-3:]):
            if not self.finality_observed:
                self.ledger.event("END_LABEL_OBSERVED", dict(received_ms=received_ms, tail=incoming[-3:]))
            self.finality_observed = True
        changed = [r for r in incoming if self.known.get(r["ts"]) != r]
        self.known.update({r["ts"]:r for r in incoming})
        if changed or self.last_snapshot is None:
            self.ledger.save_bars(list(self.known.values()) if self.last_snapshot is None else changed, received_ms)
            self.ledger.event("SOURCE_SNAPSHOT", dict(metadata=metadata, received_ms=received_ms, lineage=binding))
            self.last_snapshot = metadata["market_snapshot_sha256"]
        # A later source record proves the predecessor's interval ended; never score a forming tail.
        watermark = min(received_ms-2000, incoming[-1]["ts"]-1)
        self.closed.update({r["ts"]:r for r in incoming if r["ts"] <= watermark and not r.get('quarantine_reason')})
        complete = [self.closed[t] for t in sorted(self.closed) if t <= watermark]
        if not complete:
            return self.state("WARMUP")
        if complete[-1]["ts"] == self.prepared_cutoff and not any(r["ts"] <= watermark for r in changed):
            return self.idle(received_ms,self.cursor)
        gaps = missing_labels(self.history[-1]["ts"],complete[-1]["ts"],self.closed)
        if gaps:
            self._expire(received_ms)
            return self.state("MISSING_SEQUENCE",dict(first=local_time(gaps[0]),count=len(gaps)))
        prepared = self.predictor.prepare(complete)
        self.prepared_cutoff = complete[-1]["ts"]
        latest = prepared["latest"]
        if self.cursor is None:
            self.cursor = latest
            self.prepared = prepared
            self.ledger.event("BOOTSTRAP", dict(cursor=latest, history_only=True))
            self._settle(prepared, received_ms)
            if trading_label(received_ms+60000) and received_ms-latest > 80000:
                return self.idle(received_ms,latest)
            return self.state("WARMUP_COMPLETE", dict(cursor=local_time(latest), finality_observed=self.finality_observed))
        gaps = missing_labels(self.cursor, latest, self.closed)
        if gaps:
            self._expire(received_ms)
            return self.state("MISSING_SEQUENCE", dict(first=local_time(gaps[0]), count=len(gaps)))
        self._settle(prepared, received_ms)
        if latest <= self.cursor:
            return self.idle(received_ms,latest)
        old_cursor = self.cursor
        self.cursor, self.prepared = latest, prepared
        self.ledger.event("CURSOR", dict(anchor=latest, previous=old_cursor))
        if not self.finality_observed:
            return self.state("FINALITY_UNKNOWN", "No live end-label observation; no formal prediction")
        if received_ms-latest > 20000:
            self.ledger.event("BACKFILL_ONLY", dict(anchor=latest, received_ms=received_ms))
            return self.state("STALE_OR_BACKFILL", dict(anchor=local_time(latest)))
        if prepared["status"] == "rule_skip":
            self.ledger.event("RULE_SKIP", dict(anchor=latest, rule_state=prepared["state"]))
            return self.state("RULE_SKIP", dict(anchor=local_time(latest)))
        prediction = self.predictor.predict(prepared)
        computed = self.ledger.clock()
        row = self.ledger.publish(latest, prediction["base_close"], prediction["p_up"], prediction["signal"], computed,
                                  hashlib.sha256(canonical(complete).encode()).hexdigest())
        self.ledger.event("MODEL_INPUT", dict(prediction=row["id"], feature_sha256=prediction["feature_sha256"],
                                              model_version=prediction["model_version"], rule_state=prepared["state"],
                                              snapshot_sha256=metadata["market_snapshot_sha256"], training_source="supplied-20261028-native-csv",
                                              actual_source=self.ledger.deployment["source"]))
        return self.state("PREDICTED" if row["eligible"] else "LATE", row)

    def _settle(self, prepared, at_ms):
        kept = prepared["kept"]
        positions = {int(row.ts):i for i,row in kept.iterrows()}
        for p in self.ledger.forecasts():
            index = positions.get(p["anchor_ms"])
            if index is None:
                if p['anchor_ms'] in self.closed:
                    self.ledger.settle(p['id'],None,None,at_ms,reason='ANCHOR_NO_LONGER_EFFECTIVE')
                continue
            if index+1 >= len(kept):
                continue
            target = kept.iloc[index+1]
            if missing_labels(p["anchor_ms"],int(target.ts),self.closed):
                continue
            if float(kept.iloc[index].close) != p["base_close"]:
                self.ledger.settle(p["id"],int(target.ts),float(target.close),at_ms,reason="ANCHOR_REVISED")
                continue
            previous = self.ledger.db.execute("SELECT payload FROM settlements WHERE prediction=? ORDER BY revision DESC LIMIT 1", (p["id"],)).fetchone()
            if previous:
                old = json.loads(previous[0])
                if old["target_ms"] is not None and old["target_ms"] != int(target.ts):
                    self.ledger.settle(p["id"],old["target_ms"],old["target_close"],at_ms,reason="EFFECTIVE_TARGET_REVISED")
                    continue
            self.ledger.settle(p["id"], int(target.ts), float(target.close), at_ms)

    def _expire(self, at_ms):
        completed_days = set()
        for t in self.closed:
            wall = datetime.fromtimestamp(t/1000,SHANGHAI)
            terminal = "16:00" if wall.weekday()==5 else "21:00"
            if wall.strftime("%H:%M")==terminal and t < at_ms:
                completed_days.add(wall.date())
        for p in self.ledger.forecasts():
            day = datetime.fromtimestamp(p["anchor_ms"]/1000,SHANGHAI).date()
            if sum(d > day for d in completed_days) >= 2:
                settled = self.ledger.db.execute("SELECT 1 FROM settlements WHERE prediction=?", (p["id"],)).fetchone()
                if not settled:
                    self.ledger.settle(p["id"], None, None, at_ms, reason="TWO_OBSERVED_TRADING_DAYS_MISSING_SEQUENCE")
