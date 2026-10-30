from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from realtime.engine import Engine
from realtime.ledger import Ledger
from realtime.native import epoch_ms
from realtime.http_feed import SOURCE, SYMBOL, NAME, TIME_POLICY, BOUNDARY_POLICY


def stamp(value):
    return epoch_ms(datetime.fromisoformat('2026-10-28 '+value))


def bar(ts,close=100):
    return dict(ts=ts,open=100,high=max(100,close),low=min(100,close),close=close,volume=1,turnover=100)


class FakeStudy:
    """Only tests engine timing/ledger behavior; not evidence for the real model."""
    def __init__(self):
        self.calls=0
        self.skipped=set()

    def prepare(self,rows):
        self.calls+=1
        accepted=[r for r in rows if r['ts'] not in (stamp('13:30'),stamp('19:00'))]
        latest=accepted[-1]['ts']
        frame=pd.DataFrame([r for r in accepted if r['ts'] not in self.skipped])
        return dict(kept=frame,latest=latest,status='rule_skip' if latest in self.skipped else 'accepted',state={})

    def predict(self,prepared):
        return dict(p_up=.8,signal='wait',base_close=float(prepared['kept'].close.iloc[-1]),
                    model_version='SYNTHETIC',feature_sha256='f'*64)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now=stamp('18:59')
        self.ledger=Ledger(Path(self.temp.name)/'replay.sqlite3',dict(id='replay',source='SYNTHETIC',symbol='TEST',mode='REPLAY',model_sha256='a'*64),clock=lambda:self.now)
        self.addCleanup(self.ledger.close)
        self.history=[bar(stamp('09:31')+i*60000)for i in range(120)]+[bar(stamp('13:31')+i*60000)for i in range(150)]
        self.predictor=FakeStudy()
        self.engine=Engine(self.ledger,self.history,self.predictor)
        self.meta={'market_snapshot_sha256':'1'*64}

    def process(self,rows,at):
        self.now=stamp(at)
        self.meta['market_snapshot_sha256']=str(self.now)
        return self.engine.process(rows,self.meta,self.now)

    def start(self):
        self.process(self.history,'18:59')
        self.process(self.history+[bar(stamp('19:00')),bar(stamp('19:01'))],'19:00:10')
        return self.process(self.history+[bar(stamp('19:00')),bar(stamp('19:01')),bar(stamp('19:02'),101)],'19:01:03')

    def test_forward_publish_settle_and_no_forming_leak(self):
        state=self.start()
        self.assertEqual(state['status'],'PREDICTED')
        self.assertEqual(state['detail']['base_close'],100)
        self.assertEqual(self.ledger.summary()['PENDING'],1)
        self.process(self.history+[bar(stamp('19:00')),bar(stamp('19:01')),bar(stamp('19:02'),101),bar(stamp('19:03'),105)],'19:02:03')
        self.assertEqual(self.ledger.summary()['HIT'],1)
        self.assertEqual(self.ledger.summary()['PENDING'],1)

    def test_bootstrap_and_restart_never_backfill(self):
        self.start()
        self.engine=Engine(self.ledger,self.history,FakeStudy())
        state=self.process(self.history+[bar(stamp('19:00')),bar(stamp('19:01')),bar(stamp('19:02'),101)],'19:01:08')
        self.assertEqual(state['status'],'WARMUP_COMPLETE')
        self.assertEqual(self.ledger.summary()['total'],1)

    def test_missing_forming_record_does_not_become_completed(self):
        self.start()
        state=self.process(self.history+[bar(stamp('19:00')),bar(stamp('19:01')),bar(stamp('19:03'),105),bar(stamp('19:04'),106)],'19:03:03')
        self.assertEqual(state['status'],'MISSING_SEQUENCE')
        self.assertEqual(self.ledger.summary()['PENDING'],1)
        self.assertEqual(self.ledger.summary()['scored'],0)

    def test_changed_forming_tail_does_not_repeat_full_prepare(self):
        self.start()
        calls=self.predictor.calls
        self.process(self.history+[bar(stamp('19:00')),bar(stamp('19:01')),bar(stamp('19:02'),109)],'19:01:08')
        self.assertEqual(self.predictor.calls,calls)
        self.assertEqual(self.ledger.summary()['total'],1)

    def test_source_conflict_prevents_forecast(self):
        changed=[dict(r)for r in self.history];changed[0]['volume']=2
        with self.assertRaisesRegex(ValueError,'SOURCE_CONFLICT'):
            self.process(changed,'18:59')
        self.assertEqual(self.ledger.summary()['total'],0)

    def test_rule_skip_never_requests_probability(self):
        self.predictor.skipped={stamp('19:01')}
        with patch.object(self.predictor,'predict',side_effect=AssertionError('must not predict skipped root')):
            state=self.start()
        self.assertEqual(state['status'],'RULE_SKIP')
        self.assertEqual(self.ledger.summary()['total'],0)
        self.assertEqual(self.ledger.summary()['rule_skip_events'],1)

    def test_target_is_next_effective_root_after_two_skips(self):
        self.start()
        first=self.ledger.forecasts()[0]
        self.predictor.skipped={stamp('19:02'),stamp('19:03')}
        rows=self.history+[bar(stamp('19:00')),bar(stamp('19:01')),bar(stamp('19:02'),99),bar(stamp('19:03'),98),bar(stamp('19:04'),101),bar(stamp('19:05'),102)]
        self.process(rows,'19:04:03')
        import json
        result=json.loads(self.ledger.db.execute('SELECT payload FROM settlements WHERE prediction=? ORDER BY revision DESC LIMIT 1',(first['id'],)).fetchone()[0])
        self.assertEqual(result['target_ms'],stamp('19:04'))
        self.assertEqual(result['status'],'HIT')

    def test_stale_snapshot_never_reports_current_prediction(self):
        self.process(self.history,'18:59')
        state=self.process(self.history,'19:10')
        self.assertEqual(state['status'],'STALE_SOURCE')
        self.assertEqual(self.ledger.summary()['total'],0)

    def test_stale_and_unverified_finality_cannot_publish(self):
        self.process(self.history,'18:59')
        rows=self.history+[bar(stamp('19:00')),bar(stamp('19:01')),bar(stamp('19:02'))]
        state=self.process(rows,'19:03')
        self.assertEqual(state['status'],'FINALITY_UNKNOWN')
        self.assertEqual(self.ledger.summary()['total'],0)

    def test_http_requires_explicit_waiver_identity_and_http_only_history(self):
        self.ledger.deployment.update(source=SOURCE,domain_shift_acknowledged=True,
                                      research_only=True,time_policy=TIME_POLICY,boundary_policy=BOUNDARY_POLICY)
        history=[dict(r,raw_ts=r['ts']-60000)for r in self.history]
        engine=Engine(self.ledger,history,self.predictor)
        meta=dict(self.meta,source_id=SOURCE,symbol=SYMBOL,name=NAME,period=1,time_policy=TIME_POLICY,boundary_policy=BOUNDARY_POLICY)
        state=engine.process(history,meta,self.now)
        self.assertEqual(state['status'],'WARMUP_COMPLETE')
        for key,value in [('domain_shift_acknowledged',False),('research_only',False),('time_policy','WRONG')]:
            old=self.ledger.deployment[key];self.ledger.deployment[key]=value
            with self.assertRaisesRegex(ValueError,'BINDING_REJECTED'):engine.process(history,meta,self.now)
            self.ledger.deployment[key]=old
        with self.assertRaisesRegex(ValueError,'BINDING_REJECTED'):engine.process(history,dict(meta,symbol='533'),self.now)
        mixed=Engine(self.ledger,self.history,self.predictor)
        with self.assertRaisesRegex(ValueError,'HISTORY_OR_TIME_POLICY'):mixed.process(history,meta,self.now)
        self.assertEqual(self.ledger.summary()['total'],0)
        event=dict(history[-1],ts=stamp('16:01'),raw_ts=stamp('16:00'),
                   quarantine_reason='NON_MINUTE_SINGLE_PRICE_AT_NOMINAL_SESSION_END')
        engine.process(history+[event],meta,self.now)
        self.assertNotIn(event['ts'],engine.closed)
        self.assertEqual(self.ledger.bars()[event['ts']][1],event)


if __name__=='__main__':unittest.main()
