"""Audit one immutable raw copy with the unchanged frozen auditors."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
# shortcut: requires the existing trusted model project; make portable only for requested cross-machine review.
import realtime.model
from tools import audit_forward, audit_continuity

spec=importlib.util.spec_from_file_location('qualification_window',Path(__file__).with_name('qualification_window.py'))
window=importlib.util.module_from_spec(spec);spec.loader.exec_module(window)


def run(output):
    assert output.is_relative_to(ROOT) and not output.exists()
    runtime=ROOT/'runtime/http-research'
    config=json.loads((runtime/'deployment.json').read_text(encoding='utf-8'))
    manifest_path=ROOT/'docs/candidates/http-v0.4-candidate4.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    assert config==manifest['deployment']
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items())
    extras=['docs/candidates/http-v0.4-candidate4.json',
            'docs/evidence/20261028-preflight/model-baseline-sha256.json',
            'docs/evidence/20261028-calendar/calendar-binding.json',
            'docs/baselines/v0.4/confirmation.json',
            'runtime/http-research/deployment.json','runtime/http-research/bootstrap.json']
    binding=json.loads((ROOT/extras[2]).read_text(encoding='utf-8'))
    image=(ROOT/binding['source_image']).resolve()
    assert image.is_relative_to(ROOT)
    files=list(manifest['files'])+extras+[str(image.relative_to(ROOT))]
    for name in files:
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    raw=output/'runtime/http-research/forward.sqlite3'
    with closing(sqlite3.connect((runtime/'forward.sqlite3').as_uri()+'?mode=ro',uri=True)) as live:
        with closing(sqlite3.connect(raw)) as frozen:live.backup(frozen)
    provenance=dict(frozen_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                    source_workspace=str(ROOT),review_root=str(output.relative_to(ROOT)),
                    source_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                    raw_snapshot_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                    model_dependency='Existing trusted original market-direction-ml; no copied model loaded',
                    method='Only independent audit ROOT paths redirected; original code/model/data unchanged')
    (output/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    saved_forward,saved_continuity=audit_forward.ROOT,audit_continuity.ROOT
    try:
        audit_forward.ROOT=output;audit_continuity.ROOT=output
        assert audit_continuity.audit(output/'evidence/continuity'), 'Continuity price/context issue'
        report=json.loads((output/'evidence/continuity/report.json').read_text(encoding='utf-8'))
        with closing(sqlite3.connect(raw.as_uri()+'?mode=ro',uri=True)) as db:
            settled={json.loads(p)['anchor_ms'] for i,p in db.execute(
                'SELECT id,payload FROM predictions WHERE deployment=?',(config['id'],))
                if db.execute('SELECT 1 FROM settlements WHERE prediction=? AND at_ms<=? LIMIT 1',
                              (i,report['evidence_cutoff_ms'])).fetchone()}
        selected=window.select_window(report['timeline'],settled)
        if len(selected['anchors'])<60 or selected['waiting']:
            result=dict(result='NOT_READY',max_contiguous=max(report['sequence_lengths'],default=0),
                        selected_anchors=selected['anchors'],waiting=selected['waiting'],
                        evidence_cutoff_ms=report['evidence_cutoff_ms'])
        else:
            assert audit_forward.audit(output/'evidence/model'), 'Independent model/input issue'
            model=json.loads((output/'evidence/model/report.json').read_text(encoding='utf-8'))
            assert model['integrity']=='ok' and report['integrity']=='ok'
            result=window.evaluate(output/'evidence/model',output/'evidence/continuity')
    finally:
        audit_forward.ROOT=saved_forward;audit_continuity.ROOT=saved_continuity
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items())
    (output/'qualification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result['result']=='PASS_WINDOW_GATES'


if __name__=='__main__':
    assert len(sys.argv)==2,'New review directory inside 系统设计 required'
    target=(ROOT/sys.argv[1]).resolve()
    sys.exit(0 if run(target) else 2)
