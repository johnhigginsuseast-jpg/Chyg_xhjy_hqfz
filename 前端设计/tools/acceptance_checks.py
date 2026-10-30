"""Supplementary acceptance checks; every write is to a temporary frontend fixture."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests.test_dashboard import DashboardTests, NOW
from data import DataError, Reader, SHANGHAI, SYSTEM
from demo import seed
from realtime.ledger import Ledger

results={}
case=DashboardTests();case.setUp()
try:
    path,config,_=case.fixture();reader=Reader(path,config,mode='REPLAY',clock=lambda:NOW+10000)
    with Ledger(path,config,clock=lambda:NOW+5000)as ledger:
        p=ledger.publish(NOW,100,.6,'up',NOW+2000,'a'*64)
        assert reader.dashboard({})['statistics']['cumulative']['total']==13
        ledger.event('POLL',dict(success=True,status='PREDICTED',received_ms=NOW+5000))
        after=reader.dashboard({'prediction_id':[p['id']]})
        assert after['statistics']['cumulative']==ledger.summary(as_of=NOW+5000)
        assert after['statistics']['cumulative']['total']==14 and after['detail']['id']==p['id']
        ledger.event('STOPPED',{'reason':'QA_AFTER_CUTOFF'},at_ms=NOW+6000)
        diagnostic=reader.dashboard({})
        assert diagnostic['snapshot']==after['snapshot']
        assert diagnostic['status']['last_stop_event']['at_ms']>diagnostic['snapshot']['data_as_of_ms']
    results['unfinished_then_finished_poll_and_later_diagnostic']='PASS'
finally:case.tearDown()

with tempfile.TemporaryDirectory(dir=ROOT/'runtime',prefix='acceptance-')as folder:
    path=Path(folder)/'pages.sqlite3';config=seed(path,now=NOW)
    with closing(sqlite3.connect(path))as db,db:
        rows=db.execute("SELECT id,payload FROM events WHERE kind='PUBLISHED'ORDER BY id LIMIT 2").fetchall()
        same=json.loads(rows[0][1])['published_at_ms']
        for identity,text in rows:
            value=json.loads(text);value['published_at_ms']=same
            db.execute('UPDATE events SET payload=? WHERE id=?',(json.dumps(value),identity))
        publications={p['prediction']:p for text, in db.execute("SELECT payload FROM events WHERE kind='PUBLISHED'")for p in [json.loads(text)]}
        predicted=[dict(json.loads(text),id=i)for i,text in db.execute('SELECT id,payload FROM predictions')]
        settled={i:json.loads(text)for i,text in db.execute('SELECT prediction,payload FROM settlements')}
    expected=sorted(predicted,key=lambda p:(publications[p['id']]['published_at_ms'],p['id']),reverse=True)
    reader=Reader(path,config,mode='DEMO',clock=lambda:NOW);actual=[];query={}
    while True:
        response=reader.dashboard(query);actual += [p['id']for p in response['records']]
        if not response['next_before']:break
        query={'before':[response['next_before']]}
    assert actual==[p['id']for p in expected] and len(actual)==len(set(actual))==120
    start=int(datetime(2026,10,28,tzinfo=SHANGHAI).timestamp()*1000)
    wanted=[p['id']for p in expected if start<=publications[p['id']]['published_at_ms']<start+86400000 and publications[p['id']]['eligible'] and settled.get(p['id'],{}).get('status')=='MISS']
    filtered=reader.dashboard({'from':['2026-10-28'],'to':['2026-10-28'],'status':['MISS'],'limit':['100']})
    assert [p['id']for p in filtered['records']]==wanted
    assert filtered['statistics']==response['statistics']
    results['all_120_ids_ties_combined_date_status_and_global_statistics']='PASS'
    big=Path(folder)/'bars.sqlite3';c=seed(big,count=400,now=NOW)
    class CheckedReader(Reader):
        def _read(self,db,*args):
            assert db.execute('PRAGMA query_only').fetchone()[0]==1
            try:db.execute("DELETE FROM bars")
            except sqlite3.OperationalError:pass
            else:raise AssertionError('Reader connection permitted a write')
            return super()._read(db,*args)
    bars=CheckedReader(big,c,mode='DEMO',clock=lambda:NOW).dashboard({})
    assert len(bars['market']['bars'])==240
    with closing(sqlite3.connect(big))as db,db:db.execute('DELETE FROM bars')
    empty=Reader(big,c,mode='DEMO',clock=lambda:NOW).dashboard({})
    assert empty['market']['bars']==[] and empty['market']['latest_observed_bar']is None
    results['actual_reader_query_only_default_240_and_empty_market']='PASS'
    real=json.loads((SYSTEM/'runtime/http-research/deployment.json').read_text(encoding='utf-8'));real['model_sha256']='0'*64
    try:Reader(big,real,mode='LIVE').dashboard({})
    except DataError as error:assert error.code=='BINDING_MISMATCH'
    else:raise AssertionError('Wrong real model binding accepted')
    results['wrong_live_model_binding']='PASS'
print(json.dumps(results,indent=2))
