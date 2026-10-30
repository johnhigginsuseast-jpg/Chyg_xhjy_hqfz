"""Compare the actual local API with the original ledger on an isolated copy."""
from contextlib import closing
from datetime import datetime
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'系统设计'))
from data import DATABASE, SHANGHAI, SYSTEM
from realtime.ledger import Ledger


def get(query):
    conn=http.client.HTTPConnection('127.0.0.1',8765,timeout=5)
    try:
        conn.request('GET','/api/dashboard?bars=600&limit=100'+query)
        response=conn.getresponse();body=response.read();assert response.status==200
        return json.loads(body)
    finally:conn.close()


def main():
    first=get('');selected=next((p['id']for p in first['records']if p['result']['status']in ('HIT','MISS')),None)
    data=get('&prediction_id='+selected)if selected else first
    output=ROOT/'docs/evidence'/('live-check-'+str(time.time_ns()));output.mkdir()
    (output/'api.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    copy=output/'ledger.sqlite3'
    with closing(sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True))as source,closing(sqlite3.connect(copy))as target:
        source.backup(target)
    config=json.loads((SYSTEM/'runtime/http-research/deployment.json').read_text(encoding='utf-8'))
    cutoff=data['snapshot']['data_as_of_ms'];now=data['snapshot']['observed_at_ms']
    midnight=int(datetime.fromtimestamp(now/1000,SHANGHAI).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000)
    issues=[]
    with Ledger(copy,config)as ledger:
        expected=ledger.summary(as_of=cutoff);today=ledger.summary(as_of=cutoff,since=midnight)
        if data['statistics']['cumulative']!=expected:issues.append('CUMULATIVE_DIFF')
        if data['statistics']['today']!=today:issues.append('TODAY_DIFF')
        for point in data['trend']:
            actual=ledger.summary(as_of=point['as_of_ms'])
            if (point['hit_rate'],point['scored'])!=(actual['hit_rate'],actual['scored']):issues.append('TREND_DIFF')
        if selected:
            original=next(p for p in ledger.forecasts()if p['id']==selected)
            if any(data['detail'][k]!=v for k,v in original.items()):issues.append('PREDICTION_DIFF')
            if data['detail']['publication']!=ledger._receipt(selected):issues.append('PUBLICATION_DIFF')
            result=ledger.db.execute('SELECT payload FROM settlements WHERE prediction=? AND at_ms<=? ORDER BY revision DESC LIMIT 1',(selected,cutoff)).fetchone()
            if not result or data['detail']['result']!=json.loads(result[0]):issues.append('SETTLEMENT_DIFF')
        for bar in data['market']['bars']:
            row=ledger.db.execute('SELECT payload FROM bars WHERE deployment=? AND ts=? AND received_ms<=? ORDER BY revision DESC LIMIT 1',(config['id'],bar['ts'],cutoff)).fetchone()
            if not row or any(bar[k]!=v for k,v in json.loads(row[0]).items()):issues.append('BAR_DIFF')
        integrity=ledger.db.execute('PRAGMA integrity_check').fetchone()[0]
    inspected=json.loads((ROOT/'docs/evidence/readonly-inspection-20261029.json').read_text(encoding='utf-8'))
    hashes=inspected['source_protection']['inspected_files']
    changes=[p for p,h in hashes.items()if hashlib.sha256((SYSTEM/p).read_bytes()).hexdigest()!=h]
    document_changes=[p for p in changes if Path(p).suffix=='.md']
    protected_changes=[p for p in changes if Path(p).suffix!='.md']
    protected=json.loads((SYSTEM/'docs/evidence/20261028-preflight/model-baseline-sha256.json').read_text(encoding='utf-8'))
    model_changes=[p for p,h in protected.items()if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
    report=dict(mode='LIVE',snapshot=data['snapshot'],deployment=config['id'],integrity=integrity,
                original_summary=expected,original_today=today,trend_points_checked=len(data['trend']),bars_checked=len(data['market']['bars']),
                real_scored_prediction_checked=selected,issues=issues,existing_inspected_files_changed=changes,
                observed_existing_document_changes=document_changes,protected_source_changes=protected_changes,original_model_changes=model_changes,
                note='Original Ledger instantiated only on the frontend evidence copy; source connected mode=ro, no collector started')
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(output),**report),ensure_ascii=False))
    return 0 if not issues and not protected_changes and not model_changes and integrity=='ok' and selected else 1


if __name__=='__main__':sys.exit(main())
