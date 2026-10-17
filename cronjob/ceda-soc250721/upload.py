"""Run on the workshop VM after the user confirms this prepared batch."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--confirmed', action='store_true', required=True)
parser.parse_args()
index_path = Path.home() / 'data/ceda/external-videos.json'
batch_id = 'ceda-soc250721-JC241_HDSCI_DIVE403_17-clips-v1'
lock = (index_path.parent / '.ceda-clip-ingest.lock').open('w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
index = json.loads(index_path.read_text())
batch = next(b for b in index['ingest_batches'] if b['id'] == batch_id)
by_id = {v['id']: v for v in index['videos']}
clips = [by_id[clip_id] for clip_id in batch['clip_ids']]
settings = batch['settings']
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
    body = json.dumps({'username': os.environ['USERNAME'], 'password': os.environ['PASSWORD']}).encode()
    req = urllib.request.Request(base + '/api/v1/auth/login', data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=40) as response:
        token = json.load(response)['access_token']


def request(path, body=None, content_type=None, timeout=40):
    for attempt in range(2):
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}
        if content_type:
            headers['Content-Type'] = content_type
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path, data=body, headers=headers), timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 0:
                login()
                continue
            raise


def upload(path):
    boundary = '----ceda-' + uuid.uuid4().hex
    fields = {'is_public': 'true' if settings['is_public'] else 'false'}
    for key in ('custom_prompt', 'scenario', 'capture_type', 'location', 'camera_id'):
        if settings.get(key):
            fields[key] = settings[key]
    for key in ('tags', 'allowed_users'):
        if settings.get(key):
            fields[key] = ','.join(settings[key])
    chunks = []
    for name, value in fields.items():
        chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode())
    chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\nContent-Type: video/mp4\r\n\r\n').encode())
    chunks.append(path.read_bytes())
    chunks.append((f'\r\n--{boundary}--\r\n').encode())
    body = b''.join(chunks)
    del chunks
    return request('/api/v1/videos/upload', body, 'multipart/form-data; boundary=' + boundary, timeout=240)


def key_from_original(original):
    parsed = urllib.parse.urlsplit(original)
    return urllib.parse.unquote(parsed.path).lstrip('/') if parsed.scheme == 's3' else None


def explore_all():
    offset = 0
    chunks = []
    while True:
        page = request(f'/api/v1/videos/explore?scope=mine&limit=100&offset={offset}', timeout=60)
        current = page.get('chunks', [])
        chunks.extend(current)
        offset += len(current)
        if not current or offset >= int(page.get('total', offset)):
            return chunks


try:
    login()
    request('/api/v1/auth/me')
    config = request('/api/v1/config').get('app', {})
    limit = min(100000000, int(float(config['max_upload_size_mb']) * 1000000))
    for clip in clips:
        path = Path(clip['storage']['path']).expanduser()
        if path.stat().st_size != clip['size_bytes'] or not 0 < clip['size_bytes'] < limit:
            raise RuntimeError('Prepared file size changed or exceeds current limit')
        if path.suffix.lower() not in config['allowed_video_extensions']:
            raise RuntimeError('File extension is not allowed')
        if clip['ingestion']['status'] in ('uploading', 'upload_status_unknown'):
            raise RuntimeError('An earlier upload needs reconciliation before retrying')
    batch['confirmed_at_utc'] = batch.get('confirmed_at_utc') or now()
    batch['status'] = 'uploading'
    save()
    for number, clip in enumerate(clips, 1):
        ingestion = clip['ingestion']
        if ingestion.get('object_key'):
            continue
        ingestion.update(status='uploading', upload_started_at_utc=now())
        save()
        try:
            response = upload(Path(clip['storage']['path']).expanduser())
            if response.get('success') is not True or not response.get('object_key'):
                raise RuntimeError('Upload response did not confirm acceptance')
        except Exception as exc:
            status = 'upload_rejected' if isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 else 'upload_status_unknown'
            ingestion.update(status=status, error_type=type(exc).__name__)
            if isinstance(exc, urllib.error.HTTPError):
                ingestion['http_status'] = exc.code
            batch['status'] = 'needs_attention'
            save()
            raise
        ingestion.update(status='uploaded', object_key=response['object_key'], uploaded_at_utc=now())
        save()
        print(f'Uploaded {number}/{len(clips)}: {clip["filename"]}', flush=True)
    batch['status'] = 'indexing'
    batch['uploads_completed_at_utc'] = now()
    save()
    print(f'All {len(clips)} uploads accepted. Verifying fully indexed parents in Explore.', flush=True)
    started = time.monotonic()
    failures = 0
    while True:
        try:
            chunks = explore_all()
            failures = 0
        except Exception as exc:
            failures += 1
            print(f'Index check unavailable ({type(exc).__name__}); retaining pending state.', flush=True)
            if failures >= 3:
                batch['last_check_error'] = type(exc).__name__
                save()
                sys.exit(2)
            time.sleep(30)
            continue
        keyed = {key_from_original(chunk.get('original_video', '')): chunk for chunk in chunks}
        for clip in clips:
            ingestion = clip['ingestion']
            chunk = keyed.get(ingestion['object_key'])
            if not chunk:
                if ingestion['status'] != 'indexed':
                    ingestion['status'] = 'indexing'
                continue
            total = chunk.get('total_segments')
            if not isinstance(total, int) or total <= 0:
                continue
            timeline = chunk.get('timeline', [])
            numbers = {entry.get('segment_number') for entry in timeline if isinstance(entry, dict) and isinstance(entry.get('segment_number'), int)}
            if numbers != set(range(1, total + 1)):
                continue
            if chunk.get('is_public') is not False:
                batch['status'] = 'needs_attention'
                ingestion['verification_error'] = 'Unexpected visibility in Explore'
                save()
                raise RuntimeError('Indexed visibility differs from the confirmed private setting')
            ingestion.update(status='indexed', indexed_at_utc=ingestion.get('indexed_at_utc') or now())
            ingestion['verification'] = {
                'method': 'Exact object-key match in fully-indexed Explore parents',
                'original_video': chunk['original_video'],
                'total_segments': total,
                'timeline_entries': len(timeline),
                'is_public': chunk['is_public'],
                'verified_at_utc': now(),
            }
        complete = sum(clip['ingestion']['status'] == 'indexed' for clip in clips)
        batch['indexed_clip_count'] = complete
        batch['last_checked_at_utc'] = now()
        save()
        print(f'Indexed and verified: {complete}/{len(clips)} uploaded files.', flush=True)
        if complete == len(clips):
            batch['status'] = 'indexed'
            batch['completed_at_utc'] = now()
            by_id[batch['source_video_id']]['derivatives']['status'] = 'indexed'
            save()
            print(json.dumps({'status': 'complete', 'uploaded_files': len(clips), 'indexed_files': complete, 'private': True}), flush=True)
            break
        if time.monotonic() - started > 3600:
            print('Indexing is still pending after one hour; progress is saved.', flush=True)
            sys.exit(2)
        time.sleep(30)
except Exception as exc:
    print('Batch stopped: ' + type(exc).__name__, flush=True)
    if isinstance(exc, urllib.error.HTTPError):
        print('HTTP status: ' + str(exc.code), flush=True)
    sys.exit(1)
