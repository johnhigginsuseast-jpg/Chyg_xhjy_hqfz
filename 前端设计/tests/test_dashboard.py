from contextlib import closing, contextmanager, redirect_stderr
from datetime import datetime
import hashlib
import http.client
import io
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT.parent/'系统设计'))
from data import DataError, Reader, SHANGHAI, options, summary
from demo import seed
from server import LocalServer, handler_for
from realtime.ledger import Ledger

NOW=int(datetime(2026,10,29,0,20,tzinfo=SHANGHAI).timestamp()*1000)
BASE=int(datetime(2026,10,28,23,57,tzinfo=SHANGHAI).timestamp()*1000)


@contextmanager
def serving(reader):
    server=LocalServer(('127.0.0.1',0),handler_for(reader))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server.server_port
    finally:server.shutdown();server.server_close();thread.join()


def request(port,path='/api/dashboard',method='GET',headers=None):
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
    try:
        conn.request(method,path,headers=headers or {})
        response=conn.getresponse()
        return response.status,response.read(),dict(response.getheaders())
    finally:conn.close()


class DashboardTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'runtime').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'runtime',prefix='qa-')
        self.folder=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def fixture(self):
        path=self.folder/'case.sqlite3'
        config=dict(id='qa-v1',mode='REPLAY',source='SYNTHETIC_QA',symbol='531',model_sha256='0'*64)
        clock=[BASE]
        identities=[]
        with Ledger(path,config,clock=lambda:clock[0]) as ledger:
            for i in range(13):
                anchor=BASE+i*60000;clock[0]=anchor+(30000 if i==12 else 3500)
                p=ledger.publish(anchor,100,.7,'wait' if i==0 else 'up',anchor+2000,hashlib.sha256(str(i).encode()).hexdigest())
                identities.append(p['id'])
                if i!=11:
                    ledger.settle(p['id'],anchor+60000,102 if i<6 else 98 if i<10 else 100,anchor+63000)
            clock[0]=NOW
            ledger.event('SOURCE_STATE',dict(status='NOMINAL_REST',detail={'nominal_calendar_only':True}))
            ledger.event('POLL',dict(success=True,status='NOMINAL_REST',received_ms=NOW))
        return path,config,identities

    def demo(self,scenario='normal',count=120):
        path=self.folder/'demo.sqlite3';config=seed(path,count,scenario,now=NOW)
        return path,config,Reader(path,config,mode='DEMO',clock=lambda:NOW)

    def test_parameters_and_readonly_guard(self):
        for q in ({'path':['x']},{'limit':['101']},{'bars':['0']},{'from':['2026-02-30']},{'from':['2026-10-30'],'to':['2026-10-29']},{'status':['DROP']},{'status':['HIT','MISS']},{'before':['broken']},{'prediction_id':['not-an-id']}):
            with self.subTest(q=q),self.assertRaises(DataError):options(q)
        path,config,reader=self.demo()
        before=hashlib.sha256(path.read_bytes()).hexdigest();reader.dashboard({})
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True))as db,db:
            with self.assertRaises(sqlite3.OperationalError):db.execute("INSERT INTO events VALUES(999999,'x','x',0,'{}')")
        self.assertFalse((self.folder/'missing.sqlite3').exists())
        with self.assertRaises(DataError):Reader(self.folder/'missing.sqlite3',config,mode='DEMO').dashboard({})
        self.assertFalse((self.folder/'missing.sqlite3').exists())

    def test_midnight_publication_orphan_tie_and_other_deployment(self):
        path=self.folder/'midnight.sqlite3'
        config=dict(id='midnight',mode='REPLAY',source='QA',symbol='531',model_sha256='0'*64)
        midnight=int(datetime(2026,10,29,tzinfo=SHANGHAI).timestamp()*1000);clock=[midnight-1]
        with Ledger(path,config,clock=lambda:clock[0])as ledger:
            a=ledger.publish(midnight-10000,100,.5,'wait',midnight-2,'a'*64)
            orphan=dict((k,v)for k,v in a.items()if k not in ('id','prediction','published_at_ms','eligible','reason'))
            orphan.update(anchor_ms=midnight-20000)
            ledger.db.execute('INSERT INTO predictions VALUES(?,?,?,?)',('c'*64,config['id'],orphan['anchor_ms'],json.dumps(orphan)));ledger.db.commit()
            ledger.event('POLL',dict(success=True,status='PREDICTED',received_ms=clock[0]))
            clock[0]=midnight+3;b=ledger.publish(midnight+1,100,.4,'down',midnight+2,'b'*64)
            ledger.settle(a['id'],midnight+60000,102,midnight+63000)
            ledger.settle(b['id'],midnight+60001,98,midnight+63001)
            for cutoff in (midnight-1,midnight,midnight+70000):
                clock[0]=cutoff;ledger.event('POLL',dict(success=True,status='PREDICTED',received_ms=cutoff))
                value=Reader(path,config,mode='REPLAY',clock=lambda:cutoff).dashboard({'prediction_id':[a['id']]})
                day_start=int(datetime.fromtimestamp(cutoff/1000,SHANGHAI).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000)
                self.assertEqual(value['statistics']['cumulative'],ledger.summary(as_of=cutoff))
                self.assertEqual(value['statistics']['today'],ledger.summary(as_of=cutoff,since=day_start))
                self.assertEqual(value['detail']['predicted_direction'],'up');self.assertEqual(value['detail']['signal'],'wait')
                self.assertNotIn('trace',value['detail'])
                if cutoff==midnight:self.assertEqual(value['statistics']['today']['total'],0)
            self.assertEqual(value['statistics']['today']['total'],1)
            self.assertEqual(value['statistics']['cumulative']['UNSCORABLE'],1)
        other=dict(config,id='other-deployment')
        with Ledger(path,other,clock=lambda:midnight+5)as ledger:
            foreign=ledger.publish(midnight+1,100,.6,'up',midnight+2,'d'*64)
        with self.assertRaises(DataError)as error:Reader(path,config,mode='REPLAY',clock=lambda:midnight+70000).dashboard({'prediction_id':[foreign['id']]})
        self.assertEqual(error.exception.status,404)

    def test_status_boundaries_and_stopped_remain_unknown_process(self):
        path,config,reader=self.demo()
        codes=('NOMINAL_REST','WARMUP','HTTP_ERROR','SOURCE_OR_MODEL_BLOCKED','MISSING_SEQUENCE','FINALITY_UNKNOWN','LATE','STOPPED','QA_UNKNOWN_CODE')
        with closing(sqlite3.connect(path))as db:
            for code in codes:
                with db:
                    for kind in ('SOURCE_STATE','POLL'):
                        db.execute('INSERT INTO events(deployment,kind,at_ms,payload)VALUES(?,?,?,?)',(config['id'],kind,NOW,json.dumps(dict(status=code,success=False,received_ms=None))))
                value=reader.dashboard({});self.assertEqual(value['status']['code'],code)
                self.assertEqual(value['status']['process'],'UNKNOWN');self.assertIsNone(value['current_prediction'])
            with db:db.execute('INSERT INTO events(deployment,kind,at_ms,payload)VALUES(?,?,?,?)',(config['id'],'STOPPED',NOW,json.dumps({'reason':'QA'})))
            self.assertEqual(reader.dashboard({})['status']['last_stop_event']['at_ms'],NOW)
            self.assertFalse(Reader(path,config,mode='DEMO',clock=lambda:NOW+15001).dashboard({})['status']['poll_recent'])
        with self.assertRaises(DataError):Reader(path,dict(config,model_sha256='wrong'),mode='DEMO').dashboard({})

    def test_port_conflict_preserves_first_service(self):
        _,_,reader=self.demo()
        with serving(reader)as port:
            with self.assertRaises(OSError):LocalServer(('127.0.0.1',port),handler_for(reader))
            self.assertEqual(request(port)[0],200)

    def test_hand_counts_original_parity_today_and_wait(self):
        path,config,_=self.fixture();value=Reader(path,config,mode='REPLAY',clock=lambda:NOW).dashboard({})
        with Ledger(path,config)as ledger:
            self.assertEqual(value['statistics']['cumulative'],ledger.summary(as_of=NOW))
            midnight=int(datetime(2026,10,29,tzinfo=SHANGHAI).timestamp()*1000)
            self.assertEqual(value['statistics']['today'],ledger.summary(as_of=NOW,since=midnight))
        stats=value['statistics']['cumulative']
        self.assertEqual([stats[k]for k in ('HIT','MISS','FLAT','PENDING','UNSCORABLE','total','scored')],[6,4,1,1,1,13,10])
        self.assertEqual(stats['hit_rate'],.6)
        self.assertEqual(stats['signal_scored'],9)

    def test_unfinished_poll_excludes_new_published_prediction(self):
        path,config,_=self.fixture()
        with Ledger(path,config,clock=lambda:NOW+5000)as ledger:
            ledger.publish(NOW,100,.6,'up',NOW+2000,'a'*64)
        reader=Reader(path,config,mode='REPLAY',clock=lambda:NOW+10000)
        response=reader.dashboard({})
        self.assertEqual(response['snapshot']['data_as_of_ms'],NOW)
        self.assertEqual(response['statistics']['cumulative']['total'],13)
        with Ledger(path,config)as ledger:self.assertEqual(response['statistics']['cumulative'],ledger.summary(as_of=NOW))

    def test_revision_trend_keeps_historical_knowledge(self):
        path,config,ids=self.fixture();reader=Reader(path,config,mode='REPLAY',clock=lambda:NOW+10000)
        before=reader.dashboard({})
        with Ledger(path,config,clock=lambda:NOW+5000)as ledger:
            ledger.settle(ids[6],BASE+7*60000,102,NOW+5000)
            ledger.event('POLL',dict(success=True,status='WAITING_NEW_COMPLETE_BAR',received_ms=NOW+5000))
        after=reader.dashboard({})
        self.assertEqual(after['statistics']['cumulative']['hit_rate'],.7)
        self.assertEqual(after['statistics']['cumulative']['revisions'],1)
        self.assertEqual(after['trend'][:-1],before['trend'])
        with Ledger(path,config)as ledger:
            for p in after['trend']:
                expected=ledger.summary(as_of=p['as_of_ms'])
                self.assertEqual(p['hit_rate'],expected['hit_rate'])
                self.assertEqual(p['scored'],expected['scored'])

    def test_filter_pagination_and_detail(self):
        path,config,reader=self.demo()
        first=reader.dashboard({'limit':['50']})
        second=reader.dashboard({'limit':['50'],'before':[first['next_before']]})
        self.assertEqual(len(first['records']),50);self.assertEqual(len(second['records']),50)
        self.assertFalse({p['id']for p in first['records']}&{p['id']for p in second['records']})
        filtered=reader.dashboard({'status':['MISS']})
        self.assertTrue(all(p['result']['status']=='MISS'for p in filtered['records']))
        self.assertEqual(filtered['statistics'],first['statistics'])
        p=first['records'][0];detail=reader.dashboard({'prediction_id':[p['id']]})['detail']
        self.assertEqual(detail['id'],p['id']);self.assertIn('feature_sha256',detail['trace'])
        self.assertIsNone(p['result'].get('target_ms'))
        self.assertIsNone(p['actual_direction'])
        with self.assertRaises(DataError):reader.dashboard({'prediction_id':['0'*64]})

    def test_bars_boundary_forming_and_process_unknown(self):
        path,config,reader=self.demo()
        value=reader.dashboard({'bars':['60']})
        self.assertEqual(len(value['market']['bars']),60)
        self.assertTrue(all(b['complete']for b in value['market']['bars']))
        self.assertFalse(value['market']['latest_observed_bar']['complete'])
        self.assertEqual(value['status']['process'],'UNKNOWN')
        self.assertTrue(value['status']['poll_recent'])
        self.assertIsNotNone(value['current_prediction'])
        old=Reader(path,config,mode='DEMO',clock=lambda:NOW+20000).dashboard({})
        self.assertFalse(old['status']['poll_recent']);self.assertIsNone(old['current_prediction'])
        bar=dict(value['market']['latest_observed_bar'],ts=NOW+60000,raw_ts=NOW,quarantine_reason='QA_NON_MINUTE')
        with closing(sqlite3.connect(path))as db,db:db.execute('INSERT INTO bars VALUES(?,?,?,?,?)',(config['id'],bar['ts'],1,NOW,json.dumps(bar)))
        self.assertEqual(reader.dashboard({})['market']['latest_observed_bar']['ts'],NOW)

    def test_zero_no_poll_binding_and_scenarios(self):
        path,config,reader=self.demo('zero')
        value=reader.dashboard({});self.assertEqual(value['statistics']['cumulative']['total'],0)
        self.assertIsNone(value['statistics']['cumulative']['hit_rate']);self.assertIsNone(value['last_prediction'])
        with closing(sqlite3.connect(path))as db,db:db.execute("DELETE FROM events WHERE kind='POLL'")
        self.assertIsNone(reader.dashboard({})['statistics'])
        bad=dict(config,id='wrong')
        with self.assertRaises(DataError):Reader(path,bad,mode='DEMO').dashboard({})
        for scenario,code in [('rest','NOMINAL_REST'),('stale','STALE_SOURCE'),('warmup','WARMUP'),('error','HTTP_TRANSPORT_ERROR'),('skip','RULE_SKIP')]:
            other=self.folder/(scenario+'.sqlite3');c=seed(other,scenario=scenario,now=NOW)
            value=Reader(other,c,mode='DEMO',clock=lambda:NOW).dashboard({})
            self.assertEqual(value['prediction_context'],code)
            self.assertIsNone(value['current_prediction'])

    def test_http_security_static_and_error(self):
        _,_,reader=self.demo()
        with serving(reader)as port:
            status,body,headers=request(port);self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['identity']['mode'],'DEMO')
            self.assertNotIn('Access-Control-Allow-Origin',headers)
            self.assertEqual(request(port,'/')[0],200)
            html=request(port,'/')[1].decode('utf-8')
            self.assertIn('<body data-mode="DEMO">',html)
            self.assertNotIn('id="demo-banner" class="notice demo" hidden',html)
            self.assertEqual(request(port,'/app.js')[0],200)
            self.assertEqual(request(port,'/styles.css',method='HEAD')[1],b'')
            for method in ('POST','PUT','DELETE','PATCH','OPTIONS'):self.assertEqual(request(port,method=method)[0],405)
            for path in ('/../data.py','/%2e%2e/data.py','/forward.sqlite3','/docs/','/api/dashboard?path=C:/Windows','/api/dashboard?sql=select+1'):
                self.assertIn(request(port,path)[0],(400,404))
            self.assertEqual(request(port,headers={'Host':'evil.example'})[0],403)
            self.assertEqual(request(port,headers={'Origin':'https://evil.example'})[0],403)
            self.assertEqual(request(port,headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        class Broken:
            def dashboard(self,q):raise DataError('DATA_UNAVAILABLE')
        with serving(Broken())as port:
            status,body,_=request(port);self.assertEqual(status,503);self.assertEqual(json.loads(body),{'error':'DATA_UNAVAILABLE'})

    def test_database_lock_and_missing_file_return_503(self):
        path,config,reader=self.demo()
        with closing(sqlite3.connect(path))as lock:
            lock.execute('BEGIN EXCLUSIVE')
            try:
                with serving(reader)as port:
                    status,body,_=request(port)
                    self.assertEqual(status,503);self.assertEqual(json.loads(body),{'error':'DATA_UNAVAILABLE'})
            finally:lock.rollback()
        missing=Reader(self.folder/'absent.sqlite3',config,mode='DEMO')
        with serving(missing)as port:self.assertEqual(request(port)[0],503)

    def test_corrupt_payload_returns_safe_error(self):
        path,config,reader=self.demo()
        with closing(sqlite3.connect(path))as db,db:
            p=db.execute('SELECT id,payload FROM predictions LIMIT 1').fetchone()
            body=json.loads(p[1]);body['p_up']='broken'
            db.execute('UPDATE predictions SET payload=? WHERE id=?',(json.dumps(body),p[0]))
        with self.assertRaises(DataError):reader.dashboard({})

    def test_parsing_cache_observes_changes_and_does_not_leak_mutation(self):
        path,config,reader=self.demo()
        original=reader.dashboard({})['records'][0]
        value=reader.dashboard({'prediction_id':[original['id']]})
        value['detail']['publication']['eligible']=False
        value['detail']['trace']['rule_state']['demo']=False
        value['market']['bars'][0]['close']=-1
        again=reader.dashboard({'prediction_id':[original['id']]})
        self.assertTrue(again['detail']['publication']['eligible'])
        self.assertTrue(again['detail']['trace']['rule_state']['demo'])
        self.assertGreater(again['market']['bars'][0]['close'],0)
        with closing(sqlite3.connect(path))as db,db:
            p=json.loads(db.execute('SELECT payload FROM predictions WHERE id=?',(original['id'],)).fetchone()[0])
            p['p_up']='invalid-after-cache'
            db.execute('UPDATE predictions SET payload=? WHERE id=?',(json.dumps(p),original['id']))
        with self.assertRaises(DataError):reader.dashboard({})

    def test_cancelled_client_does_not_log_server_traceback(self):
        started=threading.Event();release=threading.Event();finished=threading.Event()
        class Slow:
            def dashboard(self,q):
                started.set();release.wait(2);return {'fixture':'x'*1000000}
        class Handler(handler_for(Slow())):
            def finish(self):
                try:super().finish()
                finally:finished.set()
        server=LocalServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();errors=io.StringIO()
        try:
            with redirect_stderr(errors):
                client=http.client.HTTPConnection('127.0.0.1',server.server_port)
                client.request('GET','/api/dashboard');self.assertTrue(started.wait(2))
                client.close();release.set();self.assertTrue(finished.wait(2))
                server.shutdown();server.server_close();thread.join()
            self.assertNotIn('Traceback',errors.getvalue())
        finally:
            release.set();server.shutdown();server.server_close()

    def test_performance_10000_predictions_50_http_requests(self):
        _,_,reader=self.demo(count=10000)
        durations=[]
        with serving(reader)as port:
            for _ in range(50):
                start=time.perf_counter();status,body,_=request(port,'/api/dashboard?bars=600&limit=100')
                durations.append(time.perf_counter()-start)
                self.assertEqual(status,200)
            result=json.loads(body)
            self.assertEqual(result['statistics']['cumulative']['total'],10000)
            self.assertEqual(len(result['market']['bars']),600)
            self.assertEqual(len(result['records']),100)
            self.assertLessEqual(len(result['trend']),50)
        p95=sorted(durations)[math.ceil(.95*len(durations))-1]
        folder=ROOT/'docs/evidence/development';folder.mkdir(parents=True,exist_ok=True)
        path=folder/('performance-'+str(time.time_ns())+'.json')
        path.write_text(json.dumps(dict(mode='SYNTHETIC_QA',count=10000,requests=50,durations_seconds=durations,p95_seconds=p95),indent=2),encoding='utf-8')
        self.assertLessEqual(p95,2)


if __name__=='__main__':unittest.main(verbosity=2)
