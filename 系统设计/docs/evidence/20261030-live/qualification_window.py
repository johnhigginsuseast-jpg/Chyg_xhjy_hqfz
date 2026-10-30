"""Read-only final-window check; frozen auditors still verify the original model."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.audit_continuity import sequences
from tools.audit_forward import recompute


def select_window(timeline, settled_anchors):
    run = next((r for r in sequences(timeline) if len(r) >= 60), [])
    anchors = run[:60]
    return dict(anchors=anchors, run=run,
                waiting=[a for a in anchors if a not in settled_anchors])


def logical_digest(path):
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        rows = {t: sorted(db.execute('SELECT * FROM '+t)) for t in
                ('deployments','predictions','events','settlements','bars')}
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,
                                    separators=(',',':')).encode()).hexdigest()


def evaluate(model_dir, continuity_dir):
    model = json.loads((model_dir/'report.json').read_text(encoding='utf-8'))
    continuity = json.loads((continuity_dir/'report.json').read_text(encoding='utf-8'))
    assert model['deployment'] == continuity['deployment']
    assert model['evidence_cutoff_ms'] == continuity['evidence_cutoff_ms'], 'Different evidence cutoffs'
    assert logical_digest(model_dir/'ledger.sqlite3') == logical_digest(continuity_dir/'ledger.sqlite3'), 'Different audit input rows'
    cutoff, deployment = model['evidence_cutoff_ms'], model['deployment']
    with closing(sqlite3.connect((continuity_dir/'ledger.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
        receipts = {json.loads(p)['prediction']: json.loads(p) for p, in db.execute(
            "SELECT payload FROM events WHERE deployment=? AND kind='PUBLISHED' AND at_ms<=? ORDER BY id",(deployment,cutoff))}
        predictions = [dict(json.loads(p),id=i) for i,p in db.execute(
            'SELECT id,payload FROM predictions WHERE deployment=?',(deployment,))]
        predictions = [p for p in predictions if p['computed_at_ms']<=cutoff and p['id'] in receipts]
        ids = {p['id'] for p in predictions}
        results = {i:json.loads(p) for i,_,p in db.execute(
            'SELECT prediction,revision,payload FROM settlements WHERE at_ms<=? ORDER BY revision',(cutoff,)) if i in ids}
    by_anchor = {p['anchor_ms']:p for p in predictions}
    assert len(by_anchor)==len(predictions)
    settled = {p['anchor_ms'] for p in predictions if p['id'] in results}
    window = select_window(continuity['timeline'],settled)
    selected = [by_anchor[a] for a in window['anchors']]
    run = [by_anchor[a] for a in window['run']]
    stats, issues, latency = recompute(selected,receipts,results)
    _, run_issues, run_latency = recompute(run,receipts,results)
    checks = dict(sixty_in_one_run=len(selected)==60,
                  all_first_sixty_settled=bool(selected) and not window['waiting'],
                  all_published_model_recomputed=model['model_recomputed']==len(predictions),
                  model_and_input_issues_empty=not model['issues'],
                  continuity_issues_empty=not continuity['issues'] and not continuity['completed_close_context_changed'],
                  independent_window_issues_empty=not issues and not run_issues,
                  window_p95=bool(selected) and latency['p95_nearest_rank_seconds']<=20,
                  full_run_p95=bool(run) and run_latency['p95_nearest_rank_seconds']<=20,
                  full_candidate_p95=bool(predictions) and model['latency']['p95_nearest_rank_seconds']<=20)
    return dict(deployment=deployment,evidence_cutoff_ms=cutoff,checks=checks,
                policy='EARLIEST_CONTIGUOUS_RUN_FIRST_60_NO_OUTCOME_OR_LATENCY_SELECTION',
                anchors=window['anchors'],prediction_ids=[p['id'] for p in selected],waiting=window['waiting'],
                window_statistics=stats,window_latency=latency,full_run_latency=run_latency,
                full_candidate_latency=model['latency'],model_recomputed=model['model_recomputed'],
                result='PASS_WINDOW_GATES' if all(checks.values()) else 'NOT_ACCEPTED')


if __name__=='__main__':
    assert len(sys.argv)==4, 'model evidence directory, continuity directory, new output JSON required'
    paths=[(ROOT/v).resolve() for v in sys.argv[1:]]
    assert all(p.is_relative_to(ROOT) for p in paths)
    result=evaluate(paths[0],paths[1])
    with paths[2].open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))
    sys.exit(0 if result['result']=='PASS_WINDOW_GATES' else 2)
