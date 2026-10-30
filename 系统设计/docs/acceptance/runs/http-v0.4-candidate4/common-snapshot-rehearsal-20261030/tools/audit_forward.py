"""Independent forward evidence audit; writes only a new evidence directory."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '4'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def recompute(predictions, receipts, results):
    counts = dict.fromkeys(('HIT', 'MISS', 'FLAT', 'PENDING', 'UNSCORABLE'), 0)
    issues, delays = [], []
    signal_n = signal_hits = signal_total = late = revisions = 0
    for p in predictions:
        identity = p['id']
        receipt, result = receipts.get(identity), results.get(identity)
        published = receipt['published_at_ms'] if receipt else None
        timely = published is not None and p['anchor_ms'] <= p['computed_at_ms'] <= published <= p['anchor_ms']+20000
        if receipt:
            delays.append((published-p['anchor_ms'])/1000)
            if receipt['eligible'] != timely:
                issues.append([identity, 'INCORRECT_PUBLICATION_ELIGIBILITY'])
        late += not timely
        if not timely:
            status = 'UNSCORABLE'
        elif result is None:
            status = 'PENDING'
        elif result['reason'] or (result['target_ms'] is not None and published >= result['target_ms']):
            status = 'UNSCORABLE'
        else:
            if result['target_ms'] is None or result['target_ms'] <= p['anchor_ms'] or result['at_ms'] < result['target_ms']:
                issues.append([identity, 'INVALID_FUTURE_TARGET_TIME'])
                status = 'UNSCORABLE'
            elif result['target_close'] == p['base_close']:
                status = 'FLAT'
            else:
                up = result['target_close'] > p['base_close']
                status = 'HIT' if up == (p['predicted_direction'] == 'up') else 'MISS'
        if p['predicted_direction'] != ('up' if p['p_up'] >= .5 else 'down') or p['signal'] not in (p['predicted_direction'], 'wait'):
            issues.append([identity, 'DIRECTION_OR_SIGNAL_CHANGED'])
        if result:
            allowed_reasons = (None, 'UNPUBLISHED_OR_LATE', 'RESULT_KNOWN_AT_PUBLICATION',
                               'ANCHOR_REVISED', 'EFFECTIVE_TARGET_REVISED', 'ANCHOR_NO_LONGER_EFFECTIVE',
                               'TWO_OBSERVED_TRADING_DAYS_MISSING_SEQUENCE')
            if result['reason'] not in allowed_reasons:
                issues.append([identity, 'UNEXPLAINED_SCORING_EXCLUSION'])
            revisions += result['revision']-1
            if result['status'] != status:
                issues.append([identity, 'INCORRECT_SETTLEMENT_STATUS'])
        counts[status] += 1
        signal_total += p['signal'] != 'wait'
        if status in ('HIT', 'MISS') and p['signal'] != 'wait':
            signal_n += 1
            signal_hits += status == 'HIT'
    n, total = counts['HIT']+counts['MISS'], len(predictions)
    interval = None
    if n:
        # Solve the Wilson score inequality as a quadratic, independently of the product formula.
        z2 = 1.959963984540054**2
        a, b, c = n+z2, -(2*counts['HIT']+z2), counts['HIT']**2/n
        delta = max(0, b*b-4*a*c)
        interval = [(-b-math.sqrt(delta))/(2*a), (-b+math.sqrt(delta))/(2*a)]
    summary = dict(counts, total=total, scored=n, hit_rate=counts['HIT']/n if n else None,
                   wilson95=interval, late=late, revisions=revisions, signal_scored=signal_n,
                   signal_hit_rate=signal_hits/signal_n if signal_n else None,
                   signal_coverage=signal_n/n if n else None, signal_total=signal_total,
                   signal_coverage_all_predictions=signal_total/total if total else None)
    ordered = sorted(delays)
    return summary, issues, dict(publication_count=len(ordered), latencies_seconds=ordered,
                                 p95_nearest_rank_seconds=ordered[math.ceil(.95*len(ordered))-1] if ordered else None)


def self_check():
    predictions, receipts, results = [], {}, {}
    for i in range(13):
        anchor = 100000+i*60000
        p = dict(id=str(i), anchor_ms=anchor, computed_at_ms=anchor+500, p_up=.5,
                 predicted_direction='up', base_close=100, signal='up' if i < 3 else 'wait')
        predictions.append(p)
        receipts[str(i)] = dict(published_at_ms=anchor+(21000 if i == 12 else 1000), eligible=i != 12)
        if i != 11:
            results[str(i)] = dict(target_ms=anchor+60000, target_close=101 if i < 6 else 99,
                                   at_ms=anchor+61000, reason=None, revision=1,
                                   status='HIT' if i < 6 else 'MISS')
    results['10'].update(target_close=100, status='FLAT')
    results['12'].update(status='UNSCORABLE', reason='UNPUBLISHED_OR_LATE')
    summary, issues, latency = recompute(predictions, receipts, results)
    assert not issues and summary['total'] == 13 and summary['scored'] == 10
    assert summary['hit_rate'] == .6 and [summary[k] for k in ('FLAT', 'PENDING', 'UNSCORABLE')] == [1, 1, 1]
    assert summary['signal_hit_rate'] == 1 and summary['signal_coverage'] == .3
    assert abs(summary['wilson95'][0]-.3126737697) < 1e-9
    assert abs(summary['wilson95'][1]-.8318196703) < 1e-9
    assert latency['p95_nearest_rank_seconds'] == 21
    results['9']['status'] = 'HIT'
    assert any(x[1] == 'INCORRECT_SETTLEMENT_STATUS' for x in recompute(predictions, receipts, results)[1])
    receipts['12']['eligible'] = True
    assert any(x[1] == 'INCORRECT_PUBLICATION_ELIGIBILITY' for x in recompute(predictions, receipts, results)[1])
    assert recompute([], {}, {})[0]['hit_rate'] is None
    print('PASS: hand-counted 6/10, wait, tie, flat, pending, late, Wilson and corrupt evidence rejection')


def audit(output):
    runtime = ROOT/'runtime/http-research'
    config = json.loads((runtime/'deployment.json').read_text(encoding='utf-8'))
    candidate = config.get('candidate_id','http-v0.4-candidate1')
    if candidate not in ('http-v0.4-candidate1','http-v0.4-candidate2','http-v0.4-candidate3','http-v0.4-candidate4'):
        raise ValueError('No frozen manifest for this candidate')
    manifest = json.loads((ROOT/'docs/candidates'/f'{candidate}.json').read_text(encoding='utf-8'))
    issues = []
    for name, expected in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            issues.append([name, 'CANDIDATE_CHANGED'])
    if config != manifest['deployment']:
        issues.append(['deployment', 'CANDIDATE_DEPLOYMENT_CHANGED'])
    body = (runtime/'bootstrap.json').read_bytes()
    if hashlib.sha256(body).hexdigest() != config['bootstrap_sha256']:
        issues.append(['bootstrap', 'BOOTSTRAP_CHANGED'])
    protected = json.loads((ROOT/'docs/evidence/20261028-preflight/model-baseline-sha256.json').read_text(encoding='utf-8'))
    for name, expected in protected.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            issues.append([name, 'ORIGINAL_MODEL_OR_CODE_CHANGED'])
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output/'ledger.sqlite3'
    with closing(sqlite3.connect((runtime/'forward.sqlite3').as_uri()+'?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(snapshot)) as destination:
            source.backup(destination)
    snapshot_ms = int(time.time()*1000)
    from realtime.ledger import Ledger
    with Ledger(snapshot, config) as ledger:
        db = ledger.db
        events = [(kind, when, json.loads(p)) for kind, when, p in db.execute('SELECT kind,at_ms,payload FROM events WHERE deployment=? ORDER BY id', (config['id'],))]
        at_ms = max((when for kind, when, _ in events if kind == 'POLL'),default=snapshot_ms)
        all_receipts = {p['prediction']:p for kind, _, p in events if kind == 'PUBLISHED'}
        predictions = [dict(json.loads(p), id=i) for i, p in db.execute('SELECT id,payload FROM predictions WHERE deployment=?', (config['id'],))]
        predictions = [p for p in predictions if p['computed_at_ms']<=at_ms and all_receipts.get(p['id'],{}).get('published_at_ms',0)<=at_ms]
        events = [(kind, when, p)for kind, when, p in events if when<=at_ms]
        receipts = {p['prediction']: p for kind, _, p in events if kind == 'PUBLISHED'}
        results = {}
        for identity, revision, when, payload in db.execute('SELECT s.* FROM settlements s JOIN predictions p ON p.id=s.prediction WHERE p.deployment=? AND s.at_ms<=? ORDER BY s.revision', (config['id'],at_ms)):
            results[identity] = dict(json.loads(payload), at_ms=when, revision=revision)
        independent, arithmetic_issues, latency = recompute(predictions, receipts, results)
        issues += arithmetic_issues
        actual = ledger.summary(as_of=at_ms)
        for key, expected in independent.items():
            value = actual[key]
            equal = (all(abs(x-y) < 1e-12 for x, y in zip(expected, value)) if key == 'wilson95' and expected is not None else value == expected)
            if not equal:
                issues.append([key, 'SUMMARY_DIFFERS_FROM_INDEPENDENT_ARITHMETIC'])
        bar_versions = [(ts, when, json.loads(p)) for ts, _, when, p in db.execute('SELECT ts,revision,received_ms,payload FROM bars WHERE deployment=? ORDER BY received_ms,revision', (config['id'],))]
        def rows_at(when, cutoff):
            latest = {}
            for ts, received, row in bar_versions:
                if received <= when and ts <= cutoff:
                    latest[ts] = row
            return [latest[t] for t in sorted(latest) if not latest[t].get('quarantine_reason')]
        model_inputs = {p['prediction']: p for kind, _, p in events if kind == 'MODEL_INPUT'}
        checked = []
        if predictions:
            from realtime.model import StudyPredictor
            predictor = StudyPredictor()
            for p in predictions:
                prefix = rows_at(p['computed_at_ms'], p['anchor_ms'])
                successor = any(ts>p['anchor_ms'] and when<=p['computed_at_ms'] for ts,when,_ in bar_versions)
                if not successor or p['computed_at_ms']<p['anchor_ms']+2000:
                    issues.append([p['id'], 'MINUTE_COMPLETION_NOT_PROVEN'])
                if digest(prefix) != p['input_sha256']:
                    issues.append([p['id'], 'INPUT_DIGEST_DIFFERS'])
                prepared = predictor.prepare(prefix)
                if prepared['status'] == 'rule_skip':
                    issues.append([p['id'], 'PREDICTION_ON_RULE_SKIP'])
                    continue
                expected = predictor.predict(prepared)
                trace = model_inputs.get(p['id'], {})
                if abs(expected['p_up']-p['p_up']) > 1e-12 or expected['base_close'] != p['base_close'] or expected['signal'] != p['signal']:
                    issues.append([p['id'], 'FROZEN_MODEL_RECOMPUTE_DIFFERS'])
                if trace.get('feature_sha256') != expected['feature_sha256'] or trace.get('actual_source') != config['source']:
                    issues.append([p['id'], 'MODEL_INPUT_TRACE_DIFFERS'])
                checked.append(p['id'])
            cursors = [p.get('anchor', p.get('cursor', 0)) for kind, _, p in events if kind in ('CURSOR', 'BOOTSTRAP')]
            prepared = predictor.prepare(rows_at(at_ms, max(cursors)))
            kept = list(prepared['kept'][['ts', 'close']].itertuples(index=False, name=None))
            targets = {int(a[0]): (int(b[0]), float(b[1])) for a, b in zip(kept, kept[1:])}
            for p in predictions:
                result, target = results.get(p['id']), targets.get(p['anchor_ms'])
                if result and result['status'] in ('HIT', 'MISS', 'FLAT') and target != (result['target_ms'], result['target_close']):
                    issues.append([p['id'], 'TARGET_IS_NOT_NEXT_EFFECTIVE_BAR'])
                raw_times = {r['ts']for r in rows_at(at_ms,target[0])} if target else set()
                def nominal(t):
                    wall=datetime.fromtimestamp(t/1000,timezone(timedelta(hours=8)))
                    minute=wall.hour*60+wall.minute
                    return wall.weekday()!=6 and (571<=minute<=690 or 811<=minute<=960 or (wall.weekday()<5 and 1141<=minute<=1260))
                complete_sequence = bool(target) and all(t in raw_times for t in range(p['anchor_ms']+60000,target[0]+1,60000) if nominal(t))
                if complete_sequence and result is None:
                    issues.append([p['id'], 'COMPLETED_TARGET_NOT_SETTLED'])
        polls = [p for kind, _, p in events if kind == 'POLL']
        report = dict(observed_at=datetime.fromtimestamp(snapshot_ms/1000, timezone(timedelta(hours=8))).isoformat(),
                      evidence_cutoff_ms=at_ms,cutoff_policy='LAST_COMPLETED_POLL_EXCLUDES_INFLIGHT_WRITES',
                      candidate=manifest['candidate'], deployment=config['id'], source=config['source'],
                      snapshot=str(snapshot.relative_to(ROOT)), integrity=db.execute('PRAGMA integrity_check').fetchone()[0],
                      independent_statistics=independent, product_statistics=actual, latency=latency,
                      poll_count=len(polls), poll_failures=sum(not p['success'] for p in polls),
                      poll_statuses=dict(Counter(p['status'] for p in polls)),
                      raw_versions=len(bar_versions), model_recomputed=len(checked), issues=issues,
                      real_forward_evidence='NOT_TESTED' if not predictions else 'INSPECT_PER_PREDICTION_ISSUES',
                      minimum_60_predictions_available=len(predictions) >= 60,
                      process_liveness='NOT_CHECKED_BY_AUDITOR', release_gate='NOT_ACCEPTED')
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return not issues


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--output', help='New evidence directory inside 系统设计')
    args = parser.parse_args()
    if args.self_check:
        self_check()
    else:
        if not args.output:
            parser.error('--output is required')
        output = (ROOT/args.output).resolve()
        if not output.is_relative_to(ROOT):
            parser.error('Output must stay inside 系统设计')
        sys.exit(0 if audit(output) else 1)
