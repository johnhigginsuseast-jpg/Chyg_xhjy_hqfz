"""Acceptance-only DEMO server using the same independent 13-record fixture."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests.test_dashboard import DashboardTests, NOW
from data import Reader
from server import LocalServer, handler_for

case=DashboardTests();case.setUp()
try:
    path,config,_=case.fixture()
    reader=Reader(path,config,mode='DEMO',clock=lambda:NOW)
    stats=reader.dashboard({})['statistics']['cumulative']
    assert [stats[k]for k in ('HIT','MISS','FLAT','PENDING','UNSCORABLE','scored')]==[6,4,1,1,1,10]
    server=LocalServer(('127.0.0.1',8768),handler_for(reader))
    print('http://127.0.0.1:8768 | QA ONLY / DEMO / 13 hand-counted records',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
finally:case.tearDown()
