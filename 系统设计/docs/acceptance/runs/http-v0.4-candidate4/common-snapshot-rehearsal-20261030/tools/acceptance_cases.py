"""Additional acceptance cases on isolated REPLAY ledgers; never writes LIVE results."""
from datetime import datetime
from pathlib import Path
import json
import hashlib
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import realtime.__main__
from realtime.engine import Engine
from realtime.ledger import Ledger,canonical
from realtime.model import StudyPredictor,MODEL_HASH,MODEL
from realtime.native import epoch_ms


def stamp(value):
    return epoch_ms(datetime.fromisoformat('2026-10-28 '+value))


def bar(ts,close):
    return dict(ts=ts,open=close,high=close,low=close,close=close,volume=1,turnover=close)


class AcceptanceCases(unittest.TestCase):
    def test_anchor_invalidated_by_source_revision_is_not_left_pending(self):
        history=[bar(stamp('09:31')+i*60000,100+i%2)for i in range(120)]
        history += [bar(stamp('13:31')+i*60000,100+i%2)for i in range(150)]
        evening=[bar(stamp('19:00'),101)]+[bar(stamp('19:01')+i*60000,100+i%2)for i in range(5)]
        now=stamp('19:03:03')
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            config=dict(id='acceptance-revision',mode='REPLAY',source='SYNTHETIC',symbol='TEST',model_sha256=MODEL_HASH)
            with Ledger(Path(temp)/'replay.sqlite3',config,clock=lambda:now)as ledger:
                predictor=StudyPredictor()
                engine=Engine(ledger,history,predictor)
                meta=dict(market_snapshot_sha256='a'*64)
                engine.process(history+evening[:5],meta,now)
                now=stamp('19:04:03')
                state=engine.process(history+evening,meta,now)
                self.assertEqual(state['status'],'PREDICTED')
                self.assertEqual(ledger.summary()['PENDING'],1)
                revised=[dict(r)for r in evening]
                revised[1:4]=[bar(stamp('19:01')+i*60000,102+i)for i in range(3)]
                prepared=predictor.prepare(history+revised[:-1])
                self.assertEqual(prepared['status'],'rule_skip')
                self.assertNotIn(stamp('19:04'),set(prepared['kept'].ts))
                now=stamp('19:04:08')
                engine.process(history+revised,meta,now)
                self.assertEqual(ledger.summary()['UNSCORABLE'],1,'Original anchor is no longer effective; prediction cannot remain pending forever')
                self.assertEqual(ledger.summary()['PENDING'],0)

    def test_as_of_before_publication_does_not_invent_a_late_prediction(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            config=dict(id='acceptance-asof',mode='REPLAY',source='SYNTHETIC',symbol='TEST',model_sha256=MODEL_HASH)
            with Ledger(Path(temp)/'replay.sqlite3',config,clock=lambda:10000)as ledger:
                ledger.publish(1000,100,.8,'wait',1500,'a'*64)
                self.assertEqual(ledger.summary(as_of=5000)['total'],0,'No publication existed at the requested evidence time')
                self.assertEqual(ledger.summary(as_of=10000)['PENDING'],1)

    def test_hand_counted_full_denominator_and_revised_evidence_time(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            config=dict(id='acceptance-hand-count',mode='REPLAY',source='SYNTHETIC',symbol='TEST',model_sha256=MODEL_HASH)
            now=0
            with Ledger(Path(temp)/'replay.sqlite3',config,clock=lambda:now)as ledger:
                first_ten=[]
                for i in range(13):
                    anchor=100000+i*60000;now=anchor+(21000 if i==12 else 1000)
                    p=ledger.publish(anchor,100,.5,'up' if i<3 else 'wait',anchor+500,'b'*64)
                    if i<10:
                        ledger.settle(p['id'],anchor+60000,101 if i<6 else 99,now+60000)
                        first_ten.append(p)
                    elif i==10:ledger.settle(p['id'],anchor+60000,100,now+60000)
                summary=ledger.summary()
                self.assertEqual([summary[k]for k in ('HIT','MISS','FLAT','PENDING','UNSCORABLE')],[6,4,1,1,1])
                self.assertEqual(summary['hit_rate'],.6)
                self.assertEqual(summary['signal_hit_rate'],1)
                self.assertEqual(summary['signal_coverage'],.3)
                self.assertAlmostEqual(summary['wilson95'][0],.3126737697,places=9)
                self.assertAlmostEqual(summary['wilson95'][1],.8318196703,places=9)
                original_time=now+60000
                ledger.settle(first_ten[-1]['id'],first_ten[-1]['anchor_ms']+60000,101,original_time+1000)
                self.assertEqual(ledger.summary(as_of=original_time)['hit_rate'],.6)
                self.assertEqual(ledger.summary()['hit_rate'],.7)
                self.assertEqual(ledger.summary()['revisions'],1)

    def test_real_rule_target_skips_two_roots_and_restores_after_restart(self):
        history=[bar(stamp('09:31')+i*60000,100+i%2)for i in range(120)]
        history += [bar(stamp('13:31')+i*60000,100+i%2)for i in range(150)]
        history[-1]=bar(stamp('16:00'),100)
        evening=[bar(stamp('19:00'),100)]+[bar(stamp('19:01')+i*60000,c)for i,c in enumerate((102,103,104,90,99,105,106))]
        now=stamp('19:02:03')
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            config=dict(id='acceptance-horizon',mode='REPLAY',source='SYNTHETIC',symbol='TEST',model_sha256=MODEL_HASH)
            with Ledger(Path(temp)/'replay.sqlite3',config,clock=lambda:now)as ledger:
                predictor=StudyPredictor();engine=Engine(ledger,history,predictor)
                meta=dict(market_snapshot_sha256='c'*64)
                engine.process(history+evening[:4],meta,now)
                now=stamp('19:03:03');engine.process(history+evening[:5],meta,now)
                first=ledger.forecasts()[0]
                self.assertEqual(first['anchor_ms'],stamp('19:03'))
                now=stamp('19:04:03');self.assertEqual(engine.process(history+evening[:6],meta,now)['status'],'RULE_SKIP')
                now=stamp('19:05:03');self.assertEqual(engine.process(history+evening[:7],meta,now)['status'],'RULE_SKIP')
                self.assertEqual(ledger.summary()['total'],1)
                engine=Engine(ledger,history,StudyPredictor())
                now=stamp('19:06:03');engine.process(history+evening,meta,now)
                result=json.loads(ledger.db.execute('SELECT payload FROM settlements WHERE prediction=? ORDER BY revision DESC',(first['id'],)).fetchone()[0])
                self.assertEqual(result['target_ms'],stamp('19:06'))
                self.assertEqual(result['status'],'HIT' if first['predicted_direction']=='up' else 'MISS')
                self.assertEqual(ledger.summary()['total'],1,'Restart must not backfill another forecast')

    def test_receipted_backup_immutability_and_write_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            root=Path(temp);config=dict(id='acceptance-backup',mode='REPLAY',source='SYNTHETIC',symbol='TEST',model_sha256=MODEL_HASH)
            with Ledger(root/'replay.sqlite3',config,clock=lambda:101000)as ledger:
                p=ledger.publish(100000,100,.5,'wait',100500,'d'*64)
                with self.assertRaises(sqlite3.IntegrityError):ledger.db.execute('DELETE FROM predictions')
                ledger.db.rollback();ledger.backup(root/'backup.sqlite3')
                orphan=json.loads(ledger.db.execute('SELECT payload FROM predictions WHERE id=?',(p['id'],)).fetchone()[0])
                orphan.update(anchor_ms=100002,computed_at_ms=100502)
                orphan_id=hashlib.sha256(canonical([config['id'],100002,1]).encode()).hexdigest()
                with ledger.db:ledger.db.execute('INSERT INTO predictions VALUES(?,?,?,?)',(orphan_id,config['id'],100002,canonical(orphan)))
                with self.assertRaisesRegex(ValueError,'no publication receipt'):
                    ledger.publish(100002,100,.5,'wait',100502,'d'*64)
                self.assertEqual(ledger.summary()['UNSCORABLE'],1)
                ledger.db.execute('PRAGMA query_only=ON')
                with self.assertRaises(sqlite3.OperationalError):ledger.publish(100001,100,.5,'wait',100501,'d'*64)
                self.assertEqual(ledger.summary()['total'],2)
                self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='PUBLISHED'").fetchone()[0],1)
            with Ledger(root/'backup.sqlite3',config)as recovered:
                self.assertEqual(recovered.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(recovered.recent()[0]['id'],p['id'])
                self.assertEqual(recovered.recent()[0]['publication']['published_at_ms'],101000)

    def test_original_opening_merge_and_64_root_warmup(self):
        predictor=StudyPredictor()
        rows=[bar(stamp('09:31')+i*60000,100+i%2)for i in range(65)]
        for n in (63,64):
            with self.assertRaisesRegex(ValueError,'WARMUP'):predictor.predict(predictor.prepare(rows[:n]))
        self.assertIn('p_up',predictor.predict(predictor.prepare(rows)))
        event=bar(stamp('13:30'),100);event.update(volume=2,turnover=200)
        minute=bar(stamp('13:31'),102);minute.update(open=101,high=103,low=100,volume=3,turnover=306)
        merged=predictor.prepare([event,minute])['kept'].iloc[0]
        self.assertEqual([merged[k]for k in ('open','high','low','close','volume','turnover')],[100,103,100,102,5,506])

    def test_model_trusted_path_hash_and_original_source_guards_remain(self):
        predictor=StudyPredictor()
        from src.predict import load_bundle,predict_history
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as temp:
            path=Path(temp)/'outside-models.joblib';path.write_bytes(MODEL.read_bytes())
            with self.assertRaisesRegex(ValueError,'可信模型'):load_bundle(path)
        with patch('realtime.model.MODEL_HASH','0'*64):
            with self.assertRaisesRegex(ValueError,'MODEL_HASH'):StudyPredictor()
        with self.assertRaisesRegex(ValueError,'输入来源与模型不一致'):
            predict_history(MODEL,ROOT/'runtime/nonexistent-never-read.csv','2026-10-28 19:00','HTTP_CROSS_SOURCE_RESEARCH')
        predictor.verify()


if __name__=='__main__':unittest.main()
