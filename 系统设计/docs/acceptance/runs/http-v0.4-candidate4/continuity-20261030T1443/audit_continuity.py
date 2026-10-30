"""Read-only continuity evidence for the frozen HTTP candidate; no release approval."""
import argparse
from bisect import bisect_left
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_forward import digest

ZONE = timezone(timedelta(hours=8))


def sequences(items):
    runs, current = [], []
    for item in items:
        if not item['accepted']:
            continue
        if item['published']:
            current.append(item['anchor_ms'])
        else:
            if current:
                runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def calendar():
    path = ROOT/'docs/evidence/20261028-calendar/calendar-binding.json'
    binding = json.loads(path.read_text(encoding='utf-8'))
    image = (ROOT/binding['source_image']).resolve()
    if not image.is_relative_to(ROOT) or hashlib.sha256(image.read_bytes()).hexdigest() != binding['source_sha256']:
        raise ValueError('Calendar source image changed')
    intervals = {key: [(int(a[:2])*60+int(a[3:]), int(b[:2])*60+int(b[3:]))
                       for a, b in value] for key, value in binding['regular_sessions'].items()}

    def regular_close(ts):
        wall = datetime.fromtimestamp(ts/1000, ZONE)
        day = 'sun' if wall.weekday() == 6 else 'sat' if wall.weekday() == 5 else 'mon_fri'
        return any(a < wall.hour*60+wall.minute <= b for a, b in intervals[day])

    return regular_close, hashlib.sha256(path.read_bytes()).hexdigest()


def self_check():
    item = lambda t, accepted, published: dict(anchor_ms=t, accepted=accepted, published=published)
    assert sequences([item(1, True, True), item(2, False, False), item(3, True, True)]) == [[1, 3]]
    assert sequences([item(1, True, True), item(2, True, False), item(3, True, True)]) == [[1], [3]]
    # A recorded late attempt stays in the sequence; the separate latency audit must retain it.
    assert sequences([dict(item(1, True, True), eligible=False)]) == [[1]]
    regular, _ = calendar()
    stamp = lambda value: int(datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()*1000)
    assert not regular(stamp('2026-10-29T09:30:00')) and regular(stamp('2026-10-29T09:31:00'))
    assert regular(stamp('2026-10-29T11:30:00')) and not regular(stamp('2026-10-29T11:31:00'))
    assert not regular(stamp('2026-10-31T19:01:00')) and not regular(stamp('2026-11-01T09:31:00'))
    print('PASS: skip preserves sequence; missing accepted root breaks it; late attempts retained; user calendar boundaries')


def audit(output):
    runtime = ROOT/'runtime/http-research'
    config = json.loads((runtime/'deployment.json').read_text(encoding='utf-8'))
    candidate = config.get('candidate_id')
    if candidate not in ('http-v0.4-candidate3','http-v0.4-candidate4'):
        raise ValueError('No frozen continuity manifest for this candidate')
    manifest = json.loads((ROOT/'docs/candidates'/f'{candidate}.json').read_text(encoding='utf-8'))
    if config != manifest['deployment']:
        raise ValueError('Not the frozen candidate deployment')
    for name, expected in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen candidate changed: '+name)
    if hashlib.sha256((runtime/'bootstrap.json').read_bytes()).hexdigest() != config['bootstrap_sha256']:
        raise ValueError('Frozen bootstrap changed')
    regular, calendar_hash = calendar()
    output.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).read_bytes()
    (output/'audit_continuity.py').write_bytes(script)
    snapshot = output/'ledger.sqlite3'
    with closing(sqlite3.connect((runtime/'forward.sqlite3').as_uri()+'?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(snapshot)) as destination:
            source.backup(destination)
    with closing(sqlite3.connect(snapshot.as_uri()+'?mode=ro', uri=True)) as db:
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise ValueError('Snapshot integrity failed')
        events = [(k, t, json.loads(p)) for k, t, p in db.execute(
            'SELECT kind,at_ms,payload FROM events WHERE deployment=? ORDER BY id', (config['id'],))]
        cutoff = max(t for k, t, _ in events if k == 'POLL')
        events = [(k, t, p) for k, t, p in events if t <= cutoff]
        boot_index = max(i for i, (k, _, _) in enumerate(events) if k == 'BOOTSTRAP')
        _, boot_at, boot = events[boot_index]
        cursors = [(boot['cursor'], boot_at)] + [(p['anchor'], t) for k, t, p in events[boot_index+1:] if k == 'CURSOR']
        anchors = [t for t, _ in cursors]
        if any(b <= a for a, b in zip(anchors, anchors[1:])):
            raise ValueError('Non-monotonic cursor in the latest collector segment')
        versions = defaultdict(list)
        for t, at, p in db.execute('SELECT ts,received_ms,payload FROM bars WHERE deployment=? AND received_ms<=? ORDER BY received_ms,revision', (config['id'], cutoff)):
            if t <= anchors[-1]:
                versions[t].append((at, json.loads(p)))
        rows = {t: values[-1][1] for t, values in versions.items() if not values[-1][1].get('quarantine_reason')}
        revisions = []
        for t, row in rows.items():
            completed_at = cursors[bisect_left(anchors, t)][1]
            before = [value for at, value in versions[t] if at <= completed_at]
            if not before or any(value['close'] != before[-1]['close'] for at, value in versions[t] if at > completed_at):
                revisions.append(t)
        from realtime.model import StudyPredictor
        kept = StudyPredictor().prepare([rows[t] for t in sorted(rows)])['kept']
        accepted = set(int(t) for t in kept.ts)
        receipts = {p['prediction']: p for k, _, p in events if k == 'PUBLISHED'}
        publications = {json.loads(p)['anchor_ms']: receipts[i] for i, p in db.execute(
            'SELECT id,payload FROM predictions WHERE deployment=?', (config['id'],)) if i in receipts}
        annotations = defaultdict(list)
        for kind, _, payload in events:
            if kind in ('RULE_SKIP', 'BACKFILL_ONLY'):
                annotations[payload['anchor']].append(kind)
        items, issues = [], []
        cursor_set = set(anchors[1:])
        for t in range(anchors[0]+60000, anchors[-1]+1, 60000):
            if not regular(t):
                continue
            if t not in rows:
                issues.append([t, 'SOURCE_OR_CALENDAR_GAP'])
            allowed = t in accepted or t not in rows
            receipt = publications.get(t)
            published = receipt is not None and t in cursor_set
            if receipt and (t not in accepted or t not in cursor_set):
                issues.append([t, 'PUBLICATION_ON_SKIPPED_OR_UNPROCESSED_ROOT'])
            items.append(dict(anchor_ms=t,accepted=allowed,published=published,
                              eligible=receipt['eligible'] if receipt else None,
                              actual_events=annotations[t]))
        runs = sequences(items)
        longest = max(runs, key=len, default=[])
        report = dict(observed_at=datetime.now(ZONE).isoformat(),evidence_cutoff_ms=cutoff,
                      candidate=manifest['candidate'],deployment=config['id'],integrity=integrity,
                      collector_bootstrap_at_ms=boot_at,collector_bootstrap_cursor_ms=boot['cursor'],
                      snapshot=str(snapshot.relative_to(ROOT)),tool_sha256=hashlib.sha256(script).hexdigest(),
                      calendar_binding_sha256=calendar_hash,completed_close_context_changed=revisions,
                      processed_raw_roots=len(cursor_set),sequence_lengths=[len(run) for run in runs],
                      longest_sequence=longest,latest_sequence=runs[-1] if runs else [],
                      missing_accepted_anchors=[p['anchor_ms'] for p in items if p['accepted'] and not p['published']],
                      backfill_on_rule_skip=[p['anchor_ms'] for p in items if not p['accepted'] and 'BACKFILL_ONLY' in p['actual_events']],
                      timeline=items,issues=issues,
                      sixty_contiguous_model_attempts_proven=len(longest)>=60 and not revisions and not issues,
                      qualification='Latest collector segment; regular weekly calendar only. Skips do not count as predictions. Recorded late attempts stay included. Changed completed close context requires per-anchor replay. Use the full-candidate latency/outcome audit separately.',
                      release_gate='NOT_ACCEPTED')
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('timeline','longest_sequence','latest_sequence')},ensure_ascii=False))
    return not issues and not revisions


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
        destination = (ROOT/args.output).resolve()
        if not destination.is_relative_to(ROOT):
            parser.error('Output must stay inside 系统设计')
        sys.exit(0 if audit(destination) else 1)
