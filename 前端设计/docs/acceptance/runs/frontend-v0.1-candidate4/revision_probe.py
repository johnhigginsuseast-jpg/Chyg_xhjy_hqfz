from contextlib import closing
import json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'系统设计'))
from tests.test_dashboard import NOW
from data import Reader
from realtime.ledger import Ledger
candidates=[]
for p in (ROOT/'runtime').glob('qa-*/case.sqlite3'):
    with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True))as db:
        row=db.execute('SELECT payload FROM deployments').fetchone()
        if row and json.loads(row[0]).get('source')=='SYNTHETIC_QA' and db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]==13:candidates.append(p)
assert len(candidates)==1
path=candidates[0].resolve();assert path.is_relative_to(ROOT/'runtime')
with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True))as db,closing(sqlite3.connect(Path(__file__).with_name('hand-revision-before.sqlite3')))as copy:
    config=json.loads(db.execute('SELECT payload FROM deployments').fetchone()[0]);db.backup(copy)
reader=Reader(path,config,mode='DEMO',clock=lambda:NOW);before=reader.dashboard({})
selected=json.loads((ROOT/'docs/evidence/browser/revision-before-dom.json').read_text(encoding='utf-8'))['id']
p=next(p for p in before['records']if p['id']==selected);assert p['result']['status']=='MISS'
with Ledger(path,config,clock=lambda:NOW)as ledger:
    value=ledger.settle(selected,p['result']['target_ms'],102,NOW)
    ledger.event('POLL',dict(success=True,status='NOMINAL_REST',received_ms=NOW))
    expected=ledger.summary(as_of=NOW)
after=reader.dashboard({'prediction_id':[selected]})
assert before['statistics']['cumulative']['hit_rate']==.6
assert after['statistics']['cumulative']==expected and expected['hit_rate']==.7
assert after['trend'][:-1]==before['trend']
output=dict(mode='DEMO',selected=selected,before=before,after=after,original_summary=expected)
Path(__file__).with_name('revision-check.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(before=.6,after=.7,revision=value['revision'],past_trend_unchanged=True),indent=2))
