from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from data import DataError,Reader
from server import LocalServer,handler_for
reader=Reader();control=ROOT/'runtime/live-fault.json'
class Fault:
    mode='LIVE'
    def dashboard(self,q):
        if json.loads(control.read_text(encoding='utf-8'))['fail']:raise DataError('QA_FORCED_UNAVAILABLE')
        return reader.dashboard(q)
server=LocalServer(('127.0.0.1',8768),handler_for(Fault()))
print('http://127.0.0.1:8768 | QA ONLY / REAL READONLY DATA / CONTROLLED API FAILURE',flush=True)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close()
