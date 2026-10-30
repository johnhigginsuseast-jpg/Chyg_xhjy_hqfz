"""Browser QA only: explicit DEMO scenarios and controlled transport failures."""
import json
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from data import DataError, Reader
from demo import seed
from server import LocalServer, handler_for

CONTROL=ROOT/'runtime/ui-control.json'


def main():
    now=int(time.time()*1000);folder=ROOT/'runtime'/('ui-qa-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    readers={}
    for scenario in ('normal','zero','rest','stale','warmup','error','skip','benchmark'):
        path=folder/(scenario+'.sqlite3');config=seed(path,count=10000 if scenario=='benchmark'else 120,scenario='normal'if scenario=='benchmark'else scenario,now=now)
        readers[scenario]=Reader(path,config,mode='DEMO',clock=lambda:now)
    CONTROL.write_text(json.dumps(dict(scenario='normal',reply='normal',delay=0)),encoding='utf-8')
    class Fixture:
        mode='DEMO'
        def dashboard(self,q):
            control=json.loads(CONTROL.read_text(encoding='utf-8'))
            time.sleep(min(6,max(0,control.get('delay',0))))
            if control.get('reply')=='bad_request':raise DataError('INVALID_PARAMETERS',400)
            if control.get('reply')=='error':raise DataError('QA_INTERFACE_ERROR')
            if control.get('reply')=='missing':return {'mode':'DEMO'}
            return readers[control['scenario']].dashboard(q)
    class Handler(handler_for(Fixture())):
        def do_GET(self):
            control=json.loads(CONTROL.read_text(encoding='utf-8'))
            if self.path.startswith('/api/dashboard')and control.get('reply')=='malformed':
                self.send_body(200,b'{');return
            super().do_GET()
    server=LocalServer(('127.0.0.1',8767),Handler)
    print('http://127.0.0.1:8767 | QA ONLY / DEMO / frozen clock',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
