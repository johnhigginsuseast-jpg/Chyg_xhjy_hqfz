"""Read-only projections of the frozen forward ledger; no producer imports."""
import base64
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import sqlite3
import time

ROOT = Path(__file__).resolve().parent
SYSTEM = ROOT.parent / '系统设计'
DATABASE = SYSTEM / 'runtime/http-research/forward.sqlite3'
SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')
STATES = ('HIT', 'MISS', 'FLAT', 'PENDING', 'UNSCORABLE')
MODEL_HASH = 'd79afdbc7936dbd8692f903c37c0948de3c06c9579f671ed8bbb6f1f884b1ba7'


class DataError(Exception):
    def __init__(self, code, status=503):
        self.code, self.status = code, status


@lru_cache(maxsize=50000)
def decoded(payload):
    # The complete stored text is the key; revisions cannot reuse a previous value.
    return json.loads(payload)


@lru_cache(maxsize=20000)
def validated_prediction(payload):
    p=decoded(payload)
    if (any(isinstance(p[k],bool) or not isinstance(p[k],(int,float)) or not math.isfinite(p[k])
            for k in ('anchor_ms','computed_at_ms','base_close','p_up','p_down','confidence'))
            or not 0<=p['p_up']<=1 or p['base_close']<=0 or p['horizon']!=1
            or p['predicted_direction'] not in ('up','down') or p['signal'] not in (p['predicted_direction'],'wait')):
        raise DataError('INVALID_PREDICTION_DATA')
    return p


def options(query):
    allowed = {'from', 'to', 'status', 'before', 'limit', 'bars', 'prediction_id'}
    if set(query) - allowed or any(len(v) != 1 or len(v[0]) > 160 for v in query.values()):
        raise DataError('INVALID_PARAMETERS', 400)
    out = {k: v[0] for k, v in query.items()}
    try:
        for key, default, maximum in (('limit', 50, 100), ('bars', 240, 600)):
            out[key] = int(out.get(key, default))
            if not 1 <= out[key] <= maximum:
                raise ValueError()
        out['status'] = out.get('status', '')
        if out['status'] and out['status'] not in STATES:
            raise ValueError()
        for key in ('from', 'to'):
            value = out.get(key, '')
            out[key] = value
            if value and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError()
            out[key + '_ms'] = int(datetime.fromisoformat(value).replace(tzinfo=SHANGHAI).timestamp()*1000) if value else None
        if out['from'] and out['to'] and out['from'] > out['to']:
            raise ValueError()
        if out['to_ms'] is not None:
            out['to_ms'] += 86400000
        out['before_key'] = None
        if out.get('before'):
            key = json.loads(base64.urlsafe_b64decode(out['before']).decode())
            if len(key) != 2 or type(key[0]) is not int or not re.fullmatch(r'[0-9a-f]{64}', key[1]):
                raise ValueError()
            out['before_key'] = tuple(key)
        if out.get('prediction_id') and not re.fullmatch(r'[0-9a-f]{64}', out['prediction_id']):
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise DataError('INVALID_PARAMETERS', 400) from None
    return out


def wilson(hits, n):
    if not n:
        return None
    z = 1.959963984540054
    p, d = hits/n, 1+z*z/n
    center = (p+z*z/(2*n))/d
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0, center-radius), min(1, center+radius)]


def result_for(p, receipts, results):
    receipt = receipts.get(p['id'])
    result = dict(results.get(p['id'], {'status': 'PENDING'}))
    if not receipt or not receipt['eligible']:
        result['status'] = 'UNSCORABLE'
        result.setdefault('reason', 'UNPUBLISHED_OR_LATE')
    return result


def summary(predictions, receipts, settlements, as_of, since=None, event_counts=None, mode='LIVE'):
    # Keep Ledger.summary semantics, including future receipts and publication-date cohorts.
    results = {}
    for identity, at_ms, value in settlements:
        if at_ms <= as_of:
            results[identity] = value
    counts = dict.fromkeys(STATES, 0)
    signal_hits = signal_n = signal_total = revisions = late = 0
    for p in predictions:
        receipt = receipts.get(p['id'])
        when = receipt['published_at_ms'] if receipt else p['computed_at_ms']
        if when > as_of or (since is not None and when < since):
            continue
        result = result_for(p, receipts, results)
        status = result['status']
        counts[status] += 1
        late += not receipt or not receipt['eligible']
        signal_total += p['signal'] != 'wait'
        revisions += max(0, result.get('revision', 1)-1)
        if status in ('HIT', 'MISS') and p['signal'] != 'wait':
            signal_n += 1
            signal_hits += status == 'HIT'
    n, total = counts['HIT']+counts['MISS'], sum(counts.values())
    events = event_counts or {}
    return dict(counts, total=total, scored=n, hit_rate=counts['HIT']/n if n else None,
                wilson95=wilson(counts['HIT'], n), signal_scored=signal_n,
                signal_hit_rate=signal_hits/signal_n if signal_n else None,
                signal_coverage=signal_n/n if n else None, revisions=revisions, late=late,
                signal_total=signal_total, signal_coverage_all_predictions=signal_total/total if total else None,
                rule_skip_events=events.get('RULE_SKIP', 0), backfill_events=events.get('BACKFILL_ONLY', 0),
                source_state_events=events.get('SOURCE_STATE', 0), effect_sample_insufficient=n < 500, mode=mode)


class Reader:
    def __init__(self, database=DATABASE, configuration=None, mode='LIVE', clock=None):
        self.database, self.configuration, self.mode = Path(database), configuration, mode
        self.clock = clock or (lambda: int(time.time()*1000))

    def dashboard(self, query):
        opts = options(query)
        try:
            config = self.configuration or json.loads((SYSTEM/'runtime/http-research/deployment.json').read_text(encoding='utf-8'))
            if self.mode == 'LIVE':
                metadata = json.loads((ROOT.parent/'market-direction-ml/models/study-20261028-v1/1min-h1-logistic.json').read_text(encoding='utf-8'))
                if (config['source'] != 'HTTP_CROSS_SOURCE_RESEARCH' or config['symbol'] != '531'
                        or config['model_sha256'] != MODEL_HASH or metadata['sha256'] != MODEL_HASH
                        or config['mode'] != 'LIVE' or config.get('research_only') is not True
                        or config.get('domain_shift_acknowledged') is not True):
                    raise DataError('BINDING_MISMATCH')
                version = metadata['model_version']
            else:
                version = 'DEMO-MODEL · 非真实预测'
            with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True, timeout=1)) as db:
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
                stored = db.execute('SELECT payload FROM deployments WHERE id=?', (config['id'],)).fetchone()
                if not stored or decoded(stored[0]) != config:
                    raise DataError('BINDING_MISMATCH')
                return self._read(db, config, version, opts)
        except DataError:
            raise
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
            raise DataError('DATA_UNAVAILABLE') from None

    def _read(self, db, config, version, opts):
        now, dep = self.clock(), config['id']

        def event(kind, cutoff=now):
            row = db.execute('SELECT id,at_ms,payload FROM events WHERE deployment=? AND kind=? AND at_ms<=? ORDER BY id DESC LIMIT 1',
                             (dep, kind, cutoff)).fetchone()
            return dict(id=row[0], at_ms=row[1], **deepcopy(decoded(row[2]))) if row else None

        poll = event('POLL')
        cutoff = poll['at_ms'] if poll else 0
        source = event('SOURCE_STATE', cutoff)
        last_success = db.execute("SELECT at_ms,payload FROM events WHERE deployment=? AND kind='POLL' AND at_ms<=? AND json_extract(payload,'$.success')=1 ORDER BY id DESC LIMIT 1", (dep, cutoff)).fetchone()
        stop = event('STOPPED')
        identity = dict(name=config.get('name', '印江花果红茶二期'), symbol=config['symbol'], source=config['source'],
                        mode=self.mode, deployment=dep, model_version=version, research_only=True,
                        domain_shift_acknowledged=config.get('domain_shift_acknowledged', False),
                        units=config.get('units', '源原始单位，物理单位未核实'))
        status = dict(process='UNKNOWN', process_note='没有可靠进程身份；账本活动不代表当前进程存活',
                      code=(poll or {}).get('status', 'UNKNOWN'), detail=(source or {}).get('detail'),
                      poll_recent=bool(poll and 0 <= now-poll['at_ms'] <= 15000), last_poll_ms=cutoff or None,
                      last_poll_success=poll.get('success') if poll else None,
                      last_success_ms=decoded(last_success[1]).get('received_ms') if last_success else None,
                      last_stop_event=stop)
        response = dict(snapshot=dict(id=f'{dep}:{(poll or {}).get("id",0)}', observed_at_ms=now,
                                      data_as_of_ms=cutoff or None, timezone='Asia/Shanghai', last_completed_poll_id=(poll or {}).get('id')),
                        identity=identity, status=status, market=None, current_prediction=None, last_prediction=None,
                        prediction_context=status['code'], statistics=None, trend=[], records=[], detail=None,
                        next_before=None, filters={k:opts[k] for k in ('from','to','status','limit','bars')})
        if not poll:
            return response
        predictions = [dict(validated_prediction(p), id=i) for i,p in db.execute('SELECT id,payload FROM predictions WHERE deployment=?', (dep,))]
        receipts = {r['prediction']:r for (body,) in db.execute("SELECT payload FROM events WHERE deployment=? AND kind='PUBLISHED' ORDER BY id", (dep,)) for r in [decoded(body)]}
        settlements = [(i,t,decoded(v)) for i,t,v in db.execute('SELECT s.prediction,s.at_ms,s.payload FROM settlements s JOIN predictions p ON p.id=s.prediction WHERE p.deployment=? AND s.at_ms<=? ORDER BY s.revision', (dep,cutoff))]
        results = {i:v for i,_,v in settlements}
        midnight = int(datetime.fromtimestamp(now/1000, SHANGHAI).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000)

        def stats(at_ms, since=None):
            counts = dict(db.execute('SELECT kind,COUNT(*) FROM events WHERE deployment=? AND at_ms<=? AND at_ms>=? GROUP BY kind', (dep,at_ms,since or 0)))
            return summary(predictions, receipts, settlements, at_ms, since, counts, config['mode'])

        response['statistics'] = dict(cumulative=stats(cutoff), today=stats(cutoff,midnight), today_date=datetime.fromtimestamp(now/1000,SHANGHAI).date().isoformat())
        points = sorted({t for _,t,v in settlements if v['status'] in ('HIT','MISS','FLAT','UNSCORABLE')})
        if len(points)>50:
            points = [points[round(i*(len(points)-1)/49)] for i in range(50)]
        response['trend'] = trend(predictions,receipts,settlements,points)

        def project(p):
            receipt = receipts.get(p['id'])
            result = result_for(p,receipts,results)
            target = result.get('target_close')
            direction = None if target is None else 'flat' if target==p['base_close'] else 'up' if target>p['base_close'] else 'down'
            return dict(p, publication=dict(receipt) if receipt else None, result=result, actual_direction=direction,
                        display_time_ms=receipt['published_at_ms'] if receipt else p['computed_at_ms'])

        visible = [project(p) for p in predictions if (receipts[p['id']]['published_at_ms'] if p['id'] in receipts else p['computed_at_ms'])<=cutoff]
        visible.sort(key=lambda p:(p['display_time_ms'],p['id']),reverse=True)
        response['last_prediction'] = visible[0] if visible else None
        cursor = max([(e or {}).get('anchor',(e or {}).get('cursor',0)) for e in (event('CURSOR',cutoff),event('BOOTSTRAP',cutoff))])
        latest = response['last_prediction']
        if (latest and latest['anchor_ms']==cursor and (latest['publication'] or {}).get('eligible')
                and latest['result']['status']=='PENDING' and status['poll_recent']
                and status['code'] in ('PREDICTED','WAITING_NEW_COMPLETE_BAR')):
            response['current_prediction'] = latest
        skip = event('RULE_SKIP',cutoff)
        if skip and skip.get('anchor')==cursor:
            response['prediction_context'] = 'RULE_SKIP'
        bars, observed, seen = [], None, set()
        for ts,rev,received,body in db.execute('SELECT ts,revision,received_ms,payload FROM bars WHERE deployment=? AND received_ms<=? ORDER BY ts DESC,revision DESC', (dep,cutoff)):
            if ts in seen:
                continue
            seen.add(ts)
            bar = dict(decoded(body), revision=rev, received_ms=received, complete=ts<=cursor)
            if bar.get('quarantine_reason'):
                continue
            if (any(isinstance(bar[k],bool) or not isinstance(bar[k],(int,float)) or not math.isfinite(bar[k])
                    for k in ('ts','raw_ts','open','high','low','close','volume','turnover'))
                    or bar['low']<=0 or bar['high']<max(bar['open'],bar['close'],bar['low'])
                    or bar['low']>min(bar['open'],bar['close']) or min(bar['volume'],bar['turnover'])<0):
                raise DataError('INVALID_MARKET_DATA')
            if observed is None:
                observed = bar
            if bar['complete'] and len(bars)<opts['bars']:
                bars.append(bar)
            if len(bars)==opts['bars']:
                break
        response['market'] = dict(latest_observed_bar=observed, last_complete_ms=cursor or None,
                                  bars=list(reversed(bars)), raw_units=identity['units'])
        filtered = [p for p in visible if (not opts['status'] or p['result']['status']==opts['status'])
                    and (opts['from_ms'] is None or p['display_time_ms']>=opts['from_ms'])
                    and (opts['to_ms'] is None or p['display_time_ms']<opts['to_ms'])
                    and (opts['before_key'] is None or (p['display_time_ms'],p['id'])<opts['before_key'])]
        response['records'] = filtered[:opts['limit']]
        if len(filtered)>opts['limit']:
            p = response['records'][-1]
            response['next_before'] = base64.urlsafe_b64encode(json.dumps([p['display_time_ms'],p['id']]).encode()).decode()
        selected = opts.get('prediction_id')
        if selected:
            response['detail'] = next((p.copy() for p in visible if p['id']==selected),None)
            if response['detail'] is None:
                raise DataError('PREDICTION_NOT_FOUND',404)
            for (body,) in db.execute("SELECT payload FROM events WHERE deployment=? AND kind='MODEL_INPUT' AND at_ms<=? ORDER BY id DESC", (dep,cutoff)):
                trace = deepcopy(decoded(body))
                if trace.get('prediction')==selected:
                    response['detail']['trace'] = trace
                    break
        return response


def trend(predictions,receipts,settlements,points):
    # Replay publication and result clocks once; later revisions never rewrite past points.
    eligible={p['id']for p in predictions if receipts.get(p['id'],{}).get('eligible') is True}
    actions=[(receipts[i]['published_at_ms'],0,0,i,None)for i in eligible]
    actions += [(t,1,v.get('revision',1),i,v['status'])for i,t,v in settlements if i in eligible]
    actions.sort()
    active=set();results={};counts={'HIT':0,'MISS':0};out=[];position=0
    for at in points:
        while position<len(actions) and actions[position][0]<=at:
            _,kind,_,identity,status=actions[position];position+=1
            previous=results.get(identity)
            if identity in active and previous in counts:counts[previous]-=1
            if kind:results[identity]=status
            else:active.add(identity)
            current=results.get(identity)
            if identity in active and current in counts:counts[current]+=1
        n=sum(counts.values())
        if n:out.append(dict(as_of_ms=at,hit_rate=counts['HIT']/n,scored=n))
    return out
