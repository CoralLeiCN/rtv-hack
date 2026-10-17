"""Monitor only the confirmed CEDA batch; never upload or re-ingest anything."""
import argparse
argparse.ArgumentParser(description="CEDA batch monitor").parse_args()
from datetime import datetime, timezone
import fcntl, json, os
from pathlib import Path
import tempfile, time, urllib.error, urllib.parse, urllib.request

index_path = Path.home() / 'data/ceda/external-videos.json'
batch_id = 'ceda-soc250721-JC241_HDSCI_DIVE403_17-clips-v1'
lock = (index_path.parent / '.ceda-clip-ingest.lock').open('w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
index = json.loads(index_path.read_text())
batch = next(b for b in index['ingest_batches'] if b['id'] == batch_id)
by_id = {v['id']: v for v in index['videos']}
clips = [by_id[key] for key in batch['clip_ids']]
assert len(clips) == 54 and all(c['ingestion'].get('object_key') for c in clips)
assert len({c['ingestion']['object_key'] for c in clips}) == 54
base = os.environ['INGRESS_URL'].rstrip('/')
token = None

def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def save():
    index['updated_at_utc'] = now()
    fd, temporary = tempfile.mkstemp(prefix='.external-videos-', dir=index_path.parent)
    with os.fdopen(fd, 'w') as output:
        output.write(json.dumps(index, indent=2) + '\n')
    os.replace(temporary, index_path)

def login():
    global token
    data = json.dumps({'username': os.environ['USERNAME'], 'password': os.environ['PASSWORD']}).encode()
    req = urllib.request.Request(base + '/api/v1/auth/login', data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=40) as response:
        token = json.load(response)['access_token']

def get(path):
    global token
    if token is None:
        login()
    for attempt in range(2):
        try:
            req = urllib.request.Request(base + path, headers={'Authorization':'Bearer ' + token, 'Accept':'application/json'})
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 0:
                login()
                continue
            raise

def explore_all():
    rows, offset = [], 0
    while True:
        page = get(f'/api/v1/videos/explore?scope=mine&limit=100&offset={offset}')
        current = page.get('chunks', [])
        rows.extend(current)
        offset += len(current)
        if not current or offset >= int(page.get('total', offset)):
            return rows

def key_from_original(original):
    parsed = urllib.parse.urlsplit(original)
    return urllib.parse.unquote(parsed.path).lstrip('/') if parsed.scheme == 's3' else None

batch['monitor'] = {'pid': os.getpid(), 'status':'running', 'started_at_utc':now(), 'interval_seconds':60,
                    'script':str(Path(__file__).resolve()), 'log':'~/data/ceda/ceda-ingest-monitor.log'}
audit_path = index_path.parent / 'ceda-upload-verification.json'
if audit_path.exists():
    audit = json.loads(audit_path.read_text())
    if audit['checked_files'] == 54 and not audit['errors'] and all(v == 54 for v in audit['matching_files'].values()):
        batch['storage_verification'] = {'checked_at_utc':datetime.fromtimestamp(audit_path.stat().st_mtime, timezone.utc).isoformat(),
            'method':'S3 HEAD: file size and stored ingest metadata; custom prompt URL-decoded',
            'verified_clip_count':54, 'checks':list(audit['matching_files']), 'server_checksum_verified':False}
batch['status'] = 'indexing'
save()
last_complete = -1
highest_complete = -1
stop_reason = None
last_progress = time.monotonic()
consecutive_errors = 0
try:
    while True:
        try:
            rows = explore_all()
            consecutive_errors = 0
            batch.pop('last_check_error', None)
        except Exception as exc:
            consecutive_errors += 1
            batch['last_check_error'] = {'type':type(exc).__name__, 'at_utc':now(), 'consecutive_failures':consecutive_errors}
            save()
            print(now() + ' Index check unavailable: ' + type(exc).__name__, flush=True)
            if consecutive_errors >= 60:
                stop_reason = 'checks_unavailable'
                raise RuntimeError('Index checks unavailable for an hour')
            time.sleep(60)
            continue
        keyed = {key_from_original(r.get('original_video','')):r for r in rows}
        complete = 0
        for clip in clips:
            ingestion = clip['ingestion']
            row = keyed.get(ingestion['object_key'])
            if row is None:
                if ingestion.get('status') != 'indexed': ingestion['status'] = 'indexing'
                continue
            total = row.get('total_segments')
            timeline = row.get('timeline', [])
            numbers = {e.get('segment_number') for e in timeline if isinstance(e,dict) and isinstance(e.get('segment_number'),int)}
            if not isinstance(total,int) or total <= 0 or numbers != set(range(1,total + 1)):
                continue
            if row.get('is_public') is not False:
                ingestion['verification_error'] = 'Unexpected visibility in Explore'
                stop_reason = 'visibility_mismatch'
                raise RuntimeError('Unexpected indexed visibility')
            ingestion.update(status='indexed', indexed_at_utc=ingestion.get('indexed_at_utc') or now())
            ingestion['verification'] = {'method':'Exact object-key match in fully-indexed Explore parents',
                'original_video':row['original_video'], 'total_segments':total, 'timeline_entries':len(timeline),
                'is_public':False, 'verified_at_utc':now()}
            complete += 1
        batch['indexed_clip_count'] = complete
        batch['last_checked_at_utc'] = now()
        batch['monitor']['last_success_at_utc'] = now()
        save()
        if complete != last_complete:
            print(now() + f' Indexed and private: {complete}/54', flush=True)
            last_complete = complete
        if complete > highest_complete:
            highest_complete, last_progress = complete, time.monotonic()
        if complete == 54:
            batch.update(status='indexed', completed_at_utc=now())
            batch['monitor'].update(status='complete', stopped_at_utc=now())
            by_id[batch['source_video_id']]['derivatives']['status'] = 'indexed'
            save()
            print(now() + ' All 54 clips fully indexed and private.', flush=True)
            break
        if time.monotonic() - last_progress > 24 * 3600:
            stop_reason = 'indexing_stalled'
            raise RuntimeError('No indexing progress for 24 hours')
        time.sleep(60)
except BaseException as exc:
    batch['status'] = 'needs_attention'
    batch['monitor'].update(status='stopped', stopped_at_utc=now(), error_type=type(exc).__name__, stop_reason=stop_reason or 'unexpected_error')
    save()
    print(now() + ' Monitor stopped: ' + type(exc).__name__, flush=True)
    raise SystemExit(1)
