"""Supplemental QA against frozen candidate2; all forecast fixtures use REPLAY."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
import io
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import realtime.__main__ as console
from realtime.engine import Engine
from realtime.ledger import Ledger
from realtime.model import StudyPredictor,MODEL_HASH
from realtime.native import epoch_ms
from tools import audit_forward


def stamp(value):
    return epoch_ms(datetime.fromisoformat(value))


def bar(ts,close=100):
    return dict(ts=ts,open=close,high=close,low=close,close=close,volume=1,turnover=close)


def history(day):
    rows=[bar(stamp(day+' 09:31')+i*60000,100+i%2)for i in range(120)]
    rows += [bar(stamp(day+' 13:31')+i*60000,100+i%2)for i in range(150)]
    rows[-1]=bar(stamp(day+' 16:00'),100)
    return rows


class SupplementCases(unittest.TestCase):
    def test_expiry_requires_two_observed_closed_trading_days(self):
        base=history('2026-10-30')
        opening=bar(stamp('2026-10-30 19:00'))
        anchor=bar(stamp('2026-10-30 19:01'),101)
        forming=bar(stamp('2026-10-30 19:02'),99)
        now=stamp('2026-10-30 19:00:03')
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            config=dict(id='supplement-expiry',mode='REPLAY',source='SYNTHETIC',symbol='TEST',model_sha256=MODEL_HASH)
            with Ledger(Path(temp)/'replay.sqlite3',config,clock=lambda:now)as ledger:
                engine=Engine(ledger,base,StudyPredictor())
                meta=dict(market_snapshot_sha256='a'*64)
                engine.process(base+[opening,anchor],meta,now)
                now=stamp('2026-10-30 19:01:03')
                self.assertEqual(engine.process(base+[opening,anchor,forming],meta,now)['status'],'PREDICTED')
                now=stamp('2026-11-01 12:00')
                self.assertEqual(engine.process(base+[opening,anchor,forming],meta,now)['status'],'NOMINAL_REST')
                self.assertEqual(ledger.summary()['PENDING'],1,'Two natural days alone cannot expire a prediction')
                saturday_close=bar(stamp('2026-10-31 16:00'),102)
                monday_forming=bar(stamp('2026-11-02 09:31'),103)
                incoming=base+[opening,anchor,saturday_close,monday_forming]
                now=stamp('2026-11-02 09:30:03')
                self.assertEqual(engine.process(incoming,meta,now)['status'],'MISSING_SEQUENCE')
                self.assertEqual(ledger.summary()['PENDING'],1,'Only one later trading day was observed complete')
                incoming += [bar(stamp('2026-11-02 21:00'),104),bar(stamp('2026-11-03 09:31'),105)]
                now=stamp('2026-11-03 09:30:03')
                self.assertEqual(engine.process(incoming,meta,now)['status'],'MISSING_SEQUENCE')
                result=ledger.recent()[0]['result']
                self.assertEqual(result['status'],'UNSCORABLE')
                self.assertEqual(result['reason'],'TWO_OBSERVED_TRADING_DAYS_MISSING_SEQUENCE')
                self.assertIsNone(result['target_ms'])
                self.assertEqual(ledger.summary()['total'],1)
                self.assertNotIn(forming['ts'],engine.closed,'Old forming data cannot be silently completed after disappearing')

    def test_console_states_interrupt_and_restart_preserve_ledger(self):
        base=history('2026-10-28')
        evening=[bar(stamp('2026-10-28 19:00'))]+[bar(stamp('2026-10-28 19:01')+i*60000,c)for i,c in enumerate((102,103,104,90,99,105,106))]
        meta=dict(market_snapshot_sha256='b'*64)
        sequence=[('19:02:03',base+evening[:4]),('19:03:03',base+evening[:5]),
                  ('19:04:03',base+evening[:6]),('19:05:03',base+evening[:7]),
                  ('19:06:03',base+evening),('19:06:08',OSError('SYNTHETIC_DISCONNECT')),
                  ('19:09:03',base+evening),('19:09:04',KeyboardInterrupt())]
        now=0
        def read(_):
            nonlocal now
            wall,rows=sequence.pop(0)
            now=stamp('2026-10-28 '+wall)
            if isinstance(rows,BaseException):raise rows
            return rows,meta
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            runtime=Path(temp)
            config=dict(id='supplement-console',mode='REPLAY',source='SYNTHETIC',symbol='TEST',model_sha256=MODEL_HASH)
            path=runtime/'deployment.json';path.write_text(json.dumps(config),encoding='utf-8')
            args=argparse.Namespace(backup=None,status=False,once=False)
            output=io.StringIO();predictor=StudyPredictor()
            with patch.object(console,'read_history',return_value=base),patch.object(console,'read_snapshot',side_effect=read),patch.object(console.time,'time',side_effect=lambda:now/1000),patch.object(console.time,'sleep'),redirect_stdout(output):
                console.run(args,runtime,path,predictor,None)
            text=output.getvalue()
            for expected in ('WARMUP_COMPLETE','暂无可计分样本','PREDICTED','RULE_SKIP','SOURCE_OR_MODEL_BLOCKED','STALE_SOURCE','已停止'):
                self.assertIn(expected,text)
            states=[json.loads(line)for line in text.splitlines()if line.startswith('{')]
            self.assertTrue(all(s.get('model_version')==predictor.bundle['model_version']for s in states),'The console must identify the frozen model, alongside source and deployment')
            self.assertEqual(states[-1]['state']['status'],'STALE_SOURCE')
            self.assertEqual(states[-1]['statistics']['total'],2)
            self.assertEqual(states[-1]['statistics']['scored'],1)
            self.assertTrue(all(s['statistics']['mode']=='REPLAY'for s in states))
            with Ledger(runtime/'forward.sqlite3',config)as ledger:
                self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='STOPPED'").fetchone()[0],1)
            args.once=True
            with patch.object(console,'read_history',return_value=base),patch.object(console,'read_snapshot',return_value=(base+evening,meta)),patch.object(console.time,'time',side_effect=lambda:now/1000),redirect_stdout(output):
                console.run(args,runtime,path,StudyPredictor(),None)
            with Ledger(runtime/'forward.sqlite3',config)as ledger:
                self.assertEqual(ledger.summary()['total'],2)
                self.assertEqual(ledger.summary()['scored'],1)
            print('\nREPLAY console evidence (not LIVE performance):\n'+text)

    def test_independent_auditor_checks_real_model_and_detects_corrupt_trace_and_target(self):
        base=history('2026-10-28')
        evening=[bar(stamp('2026-10-28 19:00'))]+[bar(stamp('2026-10-28 19:01')+i*60000,c)for i,c in enumerate((102,103,104,90,99,105,106))]
        candidate_id=json.loads((ROOT/'runtime/http-research/deployment.json').read_text(encoding='utf-8'))['candidate_id']
        candidate=json.loads((ROOT/'docs/candidates'/f'{candidate_id}.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            for corruption in ('none','feature','target'):
                fixture=Path(temp)/corruption
                runtime=fixture/'runtime/http-research';runtime.mkdir(parents=True)
                body=json.dumps(dict(rows=base)).encode()
                (runtime/'bootstrap.json').write_bytes(body)
                config=dict(id='auditor-fixture-'+corruption,mode='REPLAY',source='SYNTHETIC',symbol='TEST',
                            model_sha256=MODEL_HASH,bootstrap_sha256=hashlib.sha256(body).hexdigest(),candidate_id=candidate_id)
                (runtime/'deployment.json').write_text(json.dumps(config),encoding='utf-8')
                frozen=dict(candidate,deployment=config,files={str(ROOT/name):h for name,h in candidate['files'].items()})
                manifests=fixture/'docs/candidates';manifests.mkdir(parents=True)
                (manifests/f'{candidate_id}.json').write_text(json.dumps(frozen),encoding='utf-8')
                pins=fixture/'docs/evidence/20261028-preflight';pins.mkdir(parents=True)
                (pins/'model-baseline-sha256.json').write_bytes((ROOT/'docs/evidence/20261028-preflight/model-baseline-sha256.json').read_bytes())
                now=stamp('2026-10-28 19:02:03')
                with Ledger(runtime/'forward.sqlite3',config,clock=lambda:now)as ledger:
                    engine=Engine(ledger,base,StudyPredictor())
                    for end,wall in ((4,'19:02:03'),(5,'19:03:03'),(6,'19:04:03'),(7,'19:05:03'),(8,'19:06:03')):
                        now=stamp('2026-10-28 '+wall)
                        state=engine.process(base+evening[:end],dict(market_snapshot_sha256='c'*64),now)
                        ledger.event('POLL',dict(success=True,status=state['status']))
                    first=ledger.forecasts()[0]
                    self.assertEqual(ledger.summary()['total'],2)
                    if corruption=='feature':
                        now+=1000
                        ledger.event('MODEL_INPUT',dict(prediction=first['id'],feature_sha256='0'*64,actual_source='SYNTHETIC'))
                    if corruption=='target':
                        now+=1000
                        ledger.settle(first['id'],stamp('2026-10-28 19:04'),90,now)
                    ledger.event('POLL',dict(success=True,status='QA_COMPLETE'))
                with patch.object(audit_forward,'ROOT',fixture):
                    valid=audit_forward.audit(fixture/'audit')
                report=json.loads((fixture/'audit/report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['model_recomputed'],2)
                self.assertEqual(report['product_statistics']['mode'],'REPLAY')
                self.assertEqual(valid,corruption=='none')
                if corruption=='feature':self.assertIn('MODEL_INPUT_TRACE_DIFFERS',[i[1]for i in report['issues']])
                if corruption=='target':self.assertIn('TARGET_IS_NOT_NEXT_EFFECTIVE_BAR',[i[1]for i in report['issues']])


if __name__=='__main__':unittest.main()
