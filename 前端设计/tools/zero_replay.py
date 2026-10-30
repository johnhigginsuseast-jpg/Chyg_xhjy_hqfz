"""Read a real historical zero-prediction cutoff, explicitly labelled REPLAY."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from data import DATABASE, Reader, SYSTEM
from server import LocalServer, handler_for

config=json.loads((SYSTEM/'runtime/http-research/deployment.json').read_text(encoding='utf-8'))
with closing(sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True))as db:
    row=db.execute("SELECT id,at_ms,payload FROM events WHERE deployment=? AND kind='POLL' ORDER BY id LIMIT 1",(config['id'],)).fetchone()
assert row
reader=Reader(configuration=config,clock=lambda:row[1])
class Replay:
    mode='REPLAY'
    def dashboard(self,q):
        value=reader.dashboard(q)
        assert value['statistics']['cumulative']['total']==0
        value['identity']['mode']='REPLAY'
        return value
value=Replay().dashboard({})
assert value['statistics']['cumulative']['hit_rate']is None
output=ROOT/'docs/evidence/browser/real-zero-replay-api.json'
output.write_text(json.dumps(dict(historical_poll=dict(id=row[0],at_ms=row[1],payload=json.loads(row[2])),response=value),ensure_ascii=False,indent=2),encoding='utf-8')
server=LocalServer(('127.0.0.1',8769),handler_for(Replay()))
print('http://127.0.0.1:8769 | REAL HISTORICAL REPLAY / NOT CURRENT LIVE',flush=True)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close()
