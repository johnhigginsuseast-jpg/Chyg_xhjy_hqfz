"""Read a real historical one-point trend cutoff, explicitly labelled REPLAY."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from data import DATABASE, Reader, SYSTEM
from server import LocalServer, handler_for

config=json.loads((SYSTEM/'runtime/http-research/deployment.json').read_text(encoding='utf-8'))
with closing(sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True))as db:
    first=db.execute("SELECT MIN(s.at_ms) FROM settlements s JOIN predictions p ON p.id=s.prediction WHERE p.deployment=? AND json_extract(s.payload,'$.status') IN ('HIT','MISS')",(config['id'],)).fetchone()[0]
    row=db.execute("SELECT id,at_ms,payload FROM events WHERE deployment=? AND kind='POLL' AND at_ms>=? ORDER BY id LIMIT 1",(config['id'],first)).fetchone()
assert row
reader=Reader(configuration=config,clock=lambda:row[1])
class Replay:
    mode='REPLAY'
    def dashboard(self,q):
        value=reader.dashboard(q)
        assert len(value['trend'])==1
        value['identity']['mode']='REPLAY'
        return value
value=Replay().dashboard({})
assert value['statistics']['cumulative']['scored']==1
output=ROOT/'docs/evidence/browser/real-one-point-replay-api.json'
output.write_text(json.dumps(dict(historical_poll=dict(id=row[0],at_ms=row[1],payload=json.loads(row[2])),response=value),ensure_ascii=False,indent=2),encoding='utf-8')
server=LocalServer(('127.0.0.1',8769),handler_for(Replay()))
print('http://127.0.0.1:8769 | REAL HISTORICAL REPLAY / NOT CURRENT LIVE',flush=True)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close()
