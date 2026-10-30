"""Explicit synthetic demo data, confined to the frontend workspace."""
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

ROOT = Path(__file__).resolve().parent


def seed(path, count=120, scenario='normal', now=None):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT) or path.exists():
        raise ValueError('Demo requires a new database inside 前端设计')
    path.parent.mkdir(parents=True, exist_ok=True)
    now = now or int(time.time()*1000)
    start = now//60000*60000-max(count,120)*60000
    config = dict(id='demo-v0.1', mode='REPLAY', source='DEMO_ONLY', symbol='531',
                  name='印江花果红茶二期（演示）', model_sha256='0'*64, research_only=True,
                  domain_shift_acknowledged=True, units='演示数值，无真实交易单位')
    pack = lambda v: json.dumps(v, ensure_ascii=False)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
            CREATE TABLE deployments(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE predictions(id TEXT PRIMARY KEY,deployment TEXT,anchor_ms INTEGER,payload TEXT);
            CREATE TABLE events(id INTEGER PRIMARY KEY,deployment TEXT,kind TEXT,at_ms INTEGER,payload TEXT);
            CREATE TABLE settlements(prediction TEXT,revision INTEGER,at_ms INTEGER,payload TEXT,PRIMARY KEY(prediction,revision));
            CREATE TABLE bars(deployment TEXT,ts INTEGER,revision INTEGER,received_ms INTEGER,payload TEXT,PRIMARY KEY(deployment,ts,revision));
            CREATE INDEX event_deployment ON events(deployment,kind,at_ms);
        ''')
        db.execute('INSERT INTO deployments VALUES(?,?)',(config['id'],pack(config)))
        def event(kind,value,at=now):
            db.execute('INSERT INTO events(deployment,kind,at_ms,payload) VALUES(?,?,?,?)',(config['id'],kind,at,pack(value)))
        for i in range(max(count,120)+1):
            t = start+i*60000
            close = round(1440+12*math.sin(i/6)+i*.03,2)
            bar = dict(ts=t,raw_ts=t-60000,open=round(close-2*math.sin(i),2),high=close+3,
                       low=close-3,close=close,volume=600+(i*197)%1800,turnover=close*(600+(i*197)%1800))
            db.execute('INSERT INTO bars VALUES(?,?,?,?,?)',(config['id'],t,1,min(t+2500,now),pack(bar)))
        cursor = start+(max(count,120)-1)*60000
        event('BOOTSTRAP',dict(cursor=cursor,history_only=True),now-100)
        if scenario!='zero':
            for i in range(count):
                anchor = start+i*60000
                identity = hashlib.sha256(str(anchor).encode()).hexdigest()
                p_up = .37 if i%3==0 else .52 if i%4==0 else .64
                direction = 'up' if p_up>=.5 else 'down'
                base = round(1440+12*math.sin(i/6)+i*.03,2)
                p = dict(anchor_ms=anchor,base_close=base,p_up=p_up,p_down=1-p_up,confidence=max(p_up,1-p_up),
                         predicted_direction=direction,signal='wait' if i%4==0 else direction,horizon=1,
                         computed_at_ms=anchor+3000,input_sha256='d'*64)
                db.execute('INSERT INTO predictions VALUES(?,?,?,?)',(identity,config['id'],anchor,pack(p)))
                eligible = i==count-1 or i%17!=0
                event('PUBLISHED',dict(prediction=identity,published_at_ms=anchor+3500,eligible=eligible,reason=None if eligible else 'LATE_OR_CLOCK_ERROR'),anchor+3500)
                event('MODEL_INPUT',dict(prediction=identity,model_version='DEMO-MODEL',feature_sha256='e'*64,
                                        snapshot_sha256='f'*64,actual_source='DEMO_ONLY',rule_state={'demo':True}),anchor+3600)
                if i<count-1:
                    status = 'UNSCORABLE' if not eligible else 'FLAT' if i%13==0 else 'MISS' if i%3==0 else 'HIT'
                    actual = 0 if status=='FLAT' else (1 if direction=='up' else -1)*(1 if status=='HIT' else -1)
                    result = dict(status=status,target_ms=anchor+60000,target_close=round(base+actual*2,2),
                                  target_open_ms=anchor,reason='DEMO_LATE' if not eligible else None,
                                  target_started_at_publication=True,revision=1)
                    db.execute('INSERT INTO settlements VALUES(?,?,?,?)',(identity,1,anchor+62000,pack(result)))
        codes={'normal':'PREDICTED','zero':'WAITING_NEW_COMPLETE_BAR','rest':'NOMINAL_REST',
               'stale':'STALE_SOURCE','warmup':'WARMUP','error':'HTTP_TRANSPORT_ERROR','skip':'RULE_SKIP'}
        if scenario=='skip':
            event('RULE_SKIP',dict(anchor=cursor,rule_state={'demo':True}))
        code=codes[scenario]
        event('SOURCE_STATE',dict(status=code,detail={'demo':True,'nominal_calendar_only':True}))
        event('POLL',dict(success=scenario!='error',status=code,received_ms=now if scenario!='error' else None,started_at_ms=now-500,elapsed_seconds=.5))
    return config
