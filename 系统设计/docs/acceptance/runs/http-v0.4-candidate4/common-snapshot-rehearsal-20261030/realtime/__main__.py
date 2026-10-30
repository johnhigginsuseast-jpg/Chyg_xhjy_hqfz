import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "4"

from .engine import Engine
from .ledger import Ledger, canonical
from .native import HISTORY_HASH, SHANGHAI, read_history, read_snapshot, local_time
from .http_feed import HttpFeed, FeedError, SOURCE, SYMBOL, NAME, TIME_POLICY, BOUNDARY_POLICY

ROOT = Path(__file__).resolve().parents[1]
CLIENT = Path(r"D:\Download\行情分析端\DATA\DriverRTA\MIN.DY2")


def workspace_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("All output paths must stay in 系统设计")
    return path


def code_hash():
    return hashlib.sha256(canonical({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted((ROOT/'realtime').glob('*.py'))}).encode()).hexdigest()


@contextmanager
def worker_lock(runtime):
    import msvcrt
    with (runtime/'worker.lock').open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:
            handle.write(b'0');handle.flush()
        handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise ValueError('This source already has a running collector')from None
        try:yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def http_bootstrap(runtime,predictor,feed):
    confirmation_path=ROOT/'docs/baselines/v0.4/confirmation.json'
    approval=json.loads(confirmation_path.read_text(encoding='utf-8'))
    approved_change=ROOT/'docs/baselines/v0.4/source-v0.4-draft.md'
    if (approval.get('status')!='USER_CONFIRMED' or approval.get('source')!=SOURCE
            or approval.get('domain_shift_acknowledged')is not True or approval.get('research_only')is not True
            or hashlib.sha256(approved_change.read_bytes()).hexdigest()!=approval.get('change_sha256')):
        raise ValueError('HTTP_CROSS_SOURCE_APPROVAL_MISSING')
    rows,metadata=feed.fetch(bootstrap=True)
    watermark=min(metadata['received_ms']-2000,rows[-1]['ts']-1)
    history=[r for r in rows if r['ts']<=watermark and not r.get('quarantine_reason')]
    prepared=predictor.prepare(history)
    if len(prepared['kept'])<=64:raise ValueError('HTTP_BOOTSTRAP_WARMUP_INSUFFICIENT')
    snapshot=dict(rows=history,metadata=metadata,bootstrap_end_rule_state=prepared['state'],
                  quarantined_rows=[r for r in rows if r.get('quarantine_reason')],
                  initial_status=prepared['status'],first_close_ms=history[0]['ts'],last_close_ms=history[-1]['ts'],
                  origin_policy='HTTP_ONLY_FROZEN_WINDOW_ZERO_INITIAL_RULE_STATE')
    body=canonical(snapshot)
    (runtime/'bootstrap.json').write_text(body,encoding='utf-8')
    from .model import MODEL_HASH
    return dict(id='http-research-'+datetime.now(SHANGHAI).strftime('%Y%m%dT%H%M%S'),mode='LIVE',
                source=SOURCE,symbol=SYMBOL,name=NAME,model_sha256=MODEL_HASH,
                bootstrap_sha256=hashlib.sha256(body.encode()).hexdigest(),
                approval_sha256=hashlib.sha256(confirmation_path.read_bytes()).hexdigest(),
                code_sha256=code_hash(),time_policy=TIME_POLICY,policy='realtime-v0.4-http-research-v1',
                boundary_policy=BOUNDARY_POLICY,
                enabled_at_ms=int(time.time()*1000),research_only=True,domain_shift_acknowledged=True,
                training_source='supplied-20261028-native-csv',units=metadata['actual_units'],
                initial_rule_origin=history[0]['ts'],poll_seconds=3,cpu_threads=4)


def main():
    parser = argparse.ArgumentParser(description="印江花果红茶二期：冻结模型、独立来源前向账本；研究用途")
    parser.add_argument('--source',choices=('native','http-research'),default='native')
    parser.add_argument("--once", action="store_true", help="Read once and report/bootstrap; never backfill forecasts")
    parser.add_argument("--status", action="store_true", help="Show stored statistics without reading client")
    parser.add_argument("--backup", help="New SQLite backup file inside this workspace")
    args = parser.parse_args()
    runtime = workspace_path('runtime/http-research' if args.source=='http-research' else 'runtime')
    runtime.mkdir(parents=True,exist_ok=True)
    config_path = runtime / "deployment.json"
    if (args.status or args.backup) and not config_path.exists():
        print('尚无该来源的部署和账本。')
        return
    if args.status or args.backup:
        run(args,runtime,config_path,None,None)
        return
    with worker_lock(runtime):
        print('WARMUP | 正在校验冻结模型和来源；尚未发布预测',flush=True)
        from .model import StudyPredictor
        predictor=StudyPredictor()
        feed=HttpFeed() if args.source=='http-research' else None
        try:run(args,runtime,config_path,predictor,feed)
        finally:
            if feed:feed.close()


def run(args,runtime,config_path,predictor,feed):
    if config_path.exists():
        deployment = json.loads(config_path.read_text(encoding="utf-8"))
    elif feed:
        while True:
            try:
                deployment=http_bootstrap(runtime,predictor,feed)
                break
            except FeedError as exc:
                print(canonical(dict(status=exc.code,retry_after=exc.retry_after)),flush=True)
                if exc.code in ('HTTP_STATUS_401','HTTP_STATUS_403')or args.once:return
                time.sleep(exc.retry_after)
        config_path.write_text(json.dumps(deployment,ensure_ascii=False,indent=2),encoding='utf-8')
    else:
        from .model import MODEL_HASH
        deployment = dict(id="native-"+datetime.now(SHANGHAI).strftime("%Y%m%dT%H%M%S"), mode="LIVE",
                          source="NATIVE_MIN_DY2_EXPORTER_EQUIVALENT", symbol="印江花果红茶二期",
                          model_sha256=MODEL_HASH, history_sha256=HISTORY_HASH, policy="realtime-v0.2-native-v1",
                          enabled_at_ms=int(time.time()*1000), research_only=True)
        config_path.write_text(json.dumps(deployment,ensure_ascii=False,indent=2),encoding="utf-8")
    with Ledger(runtime / "forward.sqlite3", deployment) as ledger:
        if args.backup:
            backup = workspace_path(args.backup)
            backup.parent.mkdir(parents=True,exist_ok=True)
            ledger.backup(backup)
        if args.status or args.backup:
            print(json.dumps(dict(deployment=deployment['id'],source=deployment['source'],model_sha256=deployment['model_sha256'],
                                  statistics=ledger.summary(),recent=ledger.recent()),ensure_ascii=False,indent=2))
            return
        if feed:
            body=(runtime/'bootstrap.json').read_bytes()
            if (deployment.get('source')!=SOURCE or deployment.get('code_sha256')!=code_hash()
                    or deployment.get('bootstrap_sha256')!=hashlib.sha256(body).hexdigest()
                    or deployment.get('approval_sha256')!=hashlib.sha256((ROOT/'docs/baselines/v0.4/confirmation.json').read_bytes()).hexdigest()):
                raise ValueError('HTTP_DEPLOYMENT_CODE_BOOTSTRAP_OR_APPROVAL_DRIFT')
            history=json.loads(body)['rows']
            ledger.save_bars(json.loads(body)['quarantined_rows'],deployment['enabled_at_ms'])
        else:history=read_history(ROOT.parent/'2026-10-28/1分钟K线.csv')
        engine = Engine(ledger,history,predictor)
        print('研究模式 | '+deployment['source']+' | 印江花果红茶二期 | 1分钟 h=1 | 原三连跳两根',flush=True)
        if feed:print('HTTP跨源研究：价量域差异未解释，概率未在新域校准；边界事件单独保留。',flush=True)
        previous = None
        recover=False
        last_success=None
        try:
            while True:
                start = time.monotonic()
                started_ms=int(time.time()*1000)
                delay=3
                success=False
                received=None
                stop=False
                try:
                    rows,metadata = feed.fetch(bootstrap=recover) if feed else read_snapshot(CLIENT)
                    received=int(time.time()*1000)
                    state = engine.process(rows,metadata,int(time.time()*1000))
                    success=True
                    last_success=received
                    recover=state['status']=='MISSING_SEQUENCE'
                except FeedError as exc:
                    delay=exc.retry_after
                    state=engine.state(exc.code,dict(retry_after=delay))
                    ledger.event('HTTP_ERROR',dict(code=exc.code,retry_after=delay))
                    if exc.code in ('HTTP_STATUS_401','HTTP_STATUS_403'):
                        stop=True
                    if exc.code!='HTTP_TRANSPORT_ERROR':
                        delay+=time.monotonic()-start
                except (OSError,ValueError) as exc:
                    state = engine.state("SOURCE_OR_MODEL_BLOCKED",str(exc))
                ledger.event('POLL',dict(started_at_ms=started_ms,
                                        success=success,status=state['status'],
                                        elapsed_seconds=round(time.monotonic()-start,6),received_ms=received))
                summary = ledger.summary()
                midnight = datetime.now(SHANGHAI).replace(hour=0,minute=0,second=0,microsecond=0)
                today = ledger.summary(since=int(midnight.timestamp()*1000))
                display = dict(state=state, statistics=summary, today=today,
                               recent=ledger.recent(),
                               current_time=local_time(int(time.time()*1000)),deployment=deployment["id"],
                               model_version=predictor.bundle['model_version'],
                               source=deployment['source'],research_only=True,
                               domain_shift_acknowledged=deployment.get('domain_shift_acknowledged',False),
                               last_success_at=local_time(last_success) if last_success else None,
                               accuracy='暂无可计分样本' if summary['hit_rate'] is None else f"{summary['hit_rate']:.2%} ({summary['HIT']}/{summary['scored']})",
                               message="效果样本不足" if summary["effect_sample_insufficient"] else "前向实测，非盈利保证")
                key = canonical([state,summary,today])
                if key != previous or args.once:
                    print(json.dumps(display,ensure_ascii=False),flush=True)
                    previous = key
                if args.once or stop:
                    break
                time.sleep(max(0,delay-(time.monotonic()-start)))
        except KeyboardInterrupt:
            ledger.event("STOPPED",dict(reason="Ctrl+C"))
            print("已停止，账本已保存；重启不补发历史预测。",flush=True)
        except sqlite3.Error:
            print("数据库写入/读取失败，已停止正式发布；请检查账本及磁盘状态。",flush=True)
            raise


if __name__=="__main__":
    main()
