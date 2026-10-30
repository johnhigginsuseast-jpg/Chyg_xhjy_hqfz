"""Append one synthetic update to the active DEMO browser fixture, never LIVE."""
from contextlib import closing
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    conn=http.client.HTTPConnection('127.0.0.1',8767,timeout=5)
    try:
        conn.request('GET','/api/dashboard');response=conn.getresponse();assert response.status==200
        current=json.loads(response.read())
    finally:conn.close()
    assert current['identity']['mode']=='DEMO'
    now=current['snapshot']['data_as_of_ms'];candidates=[]
    for p in (ROOT/'runtime').glob('ui-qa-*/normal.sqlite3'):
        with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True))as db:
            when=db.execute("SELECT MAX(at_ms) FROM events WHERE kind='POLL'").fetchone()[0]
            if when==now:candidates.append(p.resolve())
    assert len(candidates)==1
    path=candidates[0];assert path.is_relative_to(ROOT/'runtime')
    with closing(sqlite3.connect(path))as db,db:
        config=json.loads(db.execute('SELECT payload FROM deployments').fetchone()[0]);assert config['source']=='DEMO_ONLY'
        dep=config['id'];before=db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]
        bar=json.loads(db.execute('SELECT payload FROM bars ORDER BY ts DESC LIMIT 1').fetchone()[0])
        anchor=bar['ts'];assert anchor<=now
        identity=hashlib.sha256(str(anchor).encode()).hexdigest()
        p=dict(anchor_ms=anchor,base_close=bar['close'],p_up=.6,p_down=.4,confidence=.6,predicted_direction='up',signal='up',horizon=1,computed_at_ms=now,input_sha256='a'*64)
        db.execute('INSERT INTO predictions VALUES(?,?,?,?)',(identity,dep,anchor,json.dumps(p)))
        def event(kind,value):db.execute('INSERT INTO events(deployment,kind,at_ms,payload) VALUES(?,?,?,?)',(dep,kind,now,json.dumps(value)))
        eligible=now-anchor<=20000
        event('PUBLISHED',dict(prediction=identity,published_at_ms=now,eligible=eligible,reason=None if eligible else 'LATE_OR_CLOCK_ERROR'))
        forming=dict(bar,ts=anchor+60000,raw_ts=anchor,volume=bar['volume']+1)
        db.execute('INSERT INTO bars VALUES(?,?,?,?,?)',(dep,forming['ts'],1,now,json.dumps(forming)))
        event('CURSOR',dict(anchor=anchor,previous=anchor-60000))
        event('SOURCE_STATE',dict(status='PREDICTED'if eligible else 'LATE',detail={'demo':True}))
        event('POLL',dict(success=True,status='PREDICTED'if eligible else 'LATE',received_ms=now))
        after=db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0];assert after==before+1
    print(json.dumps(dict(mode='DEMO',path=str(path),before=before,after=after,prediction=identity,forming_ts=forming['ts'])))


if __name__=='__main__':main()
