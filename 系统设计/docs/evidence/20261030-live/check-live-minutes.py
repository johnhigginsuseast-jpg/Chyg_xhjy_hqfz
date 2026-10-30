"""Independent, read-only proof of three actual forming-to-complete source minutes."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
ZONE = timezone(timedelta(hours=8))
config = json.loads((ROOT/'runtime/http-research/deployment.json').read_text(encoding='utf-8'))
snapshot = OUTPUT/'source-observation.sqlite3'
assert not snapshot.exists()
with closing(sqlite3.connect((ROOT/'runtime/http-research/forward.sqlite3').as_uri()+'?mode=ro', uri=True)) as live:
    with closing(sqlite3.connect(snapshot)) as dest:
        live.backup(dest)
with closing(sqlite3.connect(snapshot.as_uri()+'?mode=ro', uri=True)) as db:
    integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    assert integrity == 'ok'
    events = [(k,t,json.loads(p)) for k,t,p in db.execute(
        'SELECT kind,at_ms,payload FROM events WHERE deployment=? ORDER BY id', (config['id'],))]
    cursors = {p['anchor']: t for k,t,p in events if k == 'CURSOR'}
    sources = {p['received_ms']: p['metadata'] for k,_,p in events if k == 'SOURCE_SNAPSHOT'}
    base = int(datetime(2026,10,30,10,20,tzinfo=ZONE).timestamp()*1000)
    proofs, clocks = [], []
    for ts in range(base,base+3*60000,60000):
        versions = [dict(revision=v,received_ms=at,row=json.loads(p)) for v,at,p in db.execute(
            'SELECT revision,received_ms,payload FROM bars WHERE deployment=? AND ts=? ORDER BY revision', (config['id'],ts))]
        forming = [v for v in versions if ts-60000 <= v['received_ms'] < ts]
        assert len(forming) >= 2
        assert len({(v['row']['close'],v['row']['volume'],v['row']['turnover']) for v in forming}) >= 2
        completed = cursors[ts]
        assert completed >= ts+2000
        successor = db.execute('SELECT ts,received_ms,payload FROM bars WHERE deployment=? AND ts>? AND received_ms<=? ORDER BY received_ms,ts LIMIT 1',
                               (config['id'],ts,completed)).fetchone()
        assert successor is not None
        final = [v for v in versions if v['received_ms'] <= completed][-1]
        assert all(v['row']['raw_ts'] == ts-60000 for v in versions)
        for at in (forming[0]['received_ms'],final['received_ms']):
            metadata = sources[at]
            assert metadata['source_id'] == config['source'] and metadata['symbol'] == '531'
            assert metadata['name'] == '印江花果红茶二期' and metadata['period'] == 1
            assert 'period=0' in metadata['request_path'] and ('contractId=531' in metadata['request_path'] or 'symbol=531' in metadata['request_path'])
            server_ms = int(parsedate_to_datetime(metadata['server_date']).timestamp()*1000)
            clocks.append(dict(received_ms=at,server_date=metadata['server_date'],receive_minus_server_seconds=(at-server_ms)/1000,metadata=metadata))
        proofs.append(dict(close_ms=ts,raw_open_ms=ts-60000,forming_revision_count=len(forming),first_forming=forming[0],last_forming=forming[-1],
                           completed_cursor_at_ms=completed,final_at_completion=final,
                           successor=dict(ts=successor[0],received_ms=successor[1],row=json.loads(successor[2]))))
    assert [p['close_ms'] for p in proofs] == [base,base+60000,base+120000]
report = dict(observed_at=datetime.now(ZONE).isoformat(),candidate=config['candidate_id'],deployment=config['id'],source=config['source'],
              mode='ACTUAL_LIVE_SOURCE_NOT_REPLAY',snapshot=str(snapshot.relative_to(ROOT)),snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
              integrity=integrity,live_minute_proofs=proofs,source_clock_checks=clocks,
              max_absolute_receive_server_seconds=max(abs(c['receive_minus_server_seconds']) for c in clocks),
              input_finality_audit='observation-20261030T1025/report.json independently checks every published input digest and successor/grace',
              result='PASS_THREE_CONSECUTIVE_SOURCE_MINUTES',release_gate='NOT_ACCEPTED')
(OUTPUT/'live-minute-proof.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(result=report['result'],minutes=len(proofs),clock_delta_max_seconds=report['max_absolute_receive_server_seconds'],snapshot=report['snapshot']),ensure_ascii=False))
