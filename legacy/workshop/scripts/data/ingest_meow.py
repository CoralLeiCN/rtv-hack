#!/usr/bin/env python3
"""Sequential VSS uploads using approved settings and a durable per-file journal.

Run on the workshop VM after loading its /config team environment. Credentials
and tokens remain in memory. Ambiguous requests are never automatically retried.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path.home() / 'data/meow-10k'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    os.replace(temporary, path)


class Backend:
    def __init__(self):
        self.base = os.environ['INGRESS_URL'].rstrip('/')
        self.token = None
        self.login()

    def login(self):
        body = json.dumps({'username': os.environ['USERNAME'],
                           'password': os.environ['PASSWORD']}).encode()
        result = self.call('/api/v1/auth/login', body, 'application/json', retry=False)
        self.token = result['access_token']
        self.call('/api/v1/auth/me')

    def call(self, path, body=None, content_type=None, retry=True):
        headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
        if content_type:
            headers['Content-Type'] = content_type
        req = urllib.request.Request(self.base + path, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 401 and retry:
                self.login()
                return self.call(path, body, content_type, retry=False)
            raise


def multipart(path, record, settings):
    boundary = 'meow-' + uuid.uuid4().hex
    chunks = []
    fields = {'is_public': str(settings['is_public']).lower(),
              'custom_prompt': settings['custom_prompt'],
              'capture_type': settings['capture_type'],
              'tags': ','.join(settings['tags'])}
    for key, value in fields.items():
        chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
                       f'\r\n\r\n{value}\r\n').encode())
    # Stable prefix distinguishes equal basenames from different source folders.
    prefix = hashlib.sha256(record['path'].encode()).hexdigest()[:12]
    filename = 'meow10k_' + prefix + '_' + path.name
    if any(c in filename for c in '\r\n"'):
        raise ValueError('Unsafe multipart filename')
    payload = path.read_bytes()
    if len(payload) != record['expected_size_bytes'] or hashlib.sha256(payload).hexdigest() != record['sha256']:
        raise ValueError('Downloaded file changed after verification')
    chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                   f'filename="{filename}"\r\nContent-Type: video/mp4\r\n\r\n').encode())
    chunks.extend([payload, f'\r\n--{boundary}--\r\n'.encode()])
    return b''.join(chunks), 'multipart/form-data; boundary=' + boundary, filename


def run(limit):
    settings_bytes = (ROOT / 'meow-ingestion-v1.json').read_bytes()
    settings = json.loads(settings_bytes)
    if not settings.get('approved_by_user'):
        raise ValueError('Settings need user approval')
    settings_hash = hashlib.sha256(settings_bytes).hexdigest()
    journal_path = ROOT / 'ingestion.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {
        'schema_version': 1, 'settings_version': settings['settings_version'],
        'settings_sha256': settings_hash, 'settings_path': 'meow-ingestion-v1.json',
        'created_at_utc': now(), 'videos': {}}
    if journal['settings_sha256'] != settings_hash:
        raise ValueError('Settings changed: create a new version and use the re-ingest workflow')
    if any(v['status'] == 'submitting' for v in journal['videos'].values()):
        raise ValueError('Uncertain previous upload needs reconciliation before restarting')
    backend = Backend()
    config = backend.call('/api/v1/config')['app']
    ingest = backend.call('/api/v1/metadata/ingest-config')
    if '.mp4' not in config['allowed_video_extensions']:
        raise ValueError('MP4 not allowed by live backend')
    if len(settings['custom_prompt']) > ingest['custom_prompt_max_length']:
        raise ValueError('Prompt exceeds live limit')
    if settings['capture_type'] not in [v['value'] for v in ingest['capture_types']]:
        raise ValueError('Capture type is unavailable')
    submitted = 0
    journal['worker_status'] = 'running'

    def save():
        journal['updated_at_utc'] = now()
        atomic(journal_path, journal)

    save()
    while True:
        manifest = json.loads((ROOT / 'manifest.json').read_text())
        if manifest['revision'] != settings['revision']:
            raise ValueError('Unexpected dataset revision')
        videos = [r for r in manifest['files'] if r['path'].lower().endswith('.mp4')]
        pending = [r for r in videos if r['path'] not in journal['videos']]
        ready = [r for r in pending if r['download_status'] == 'verified']
        for record in ready:
            relative = Path(record['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe manifest path')
            if record['actual_size_bytes'] > config['max_upload_size_mb'] * 1024 * 1024:
                raise ValueError('File exceeds live upload size limit')
            body, content_type, filename = multipart(ROOT / relative, record, settings)
            entry = {'status': 'submitting', 'source_path': record['path'],
                     'source_sha256': record['sha256'], 'upload_filename': filename,
                     'settings_version': settings['settings_version'],
                     'settings_sha256': settings_hash, 'submitted_at_utc': now()}
            journal['videos'][record['path']] = entry
            save()  # Persist intent before network call: crash recovery must not duplicate uploads.
            try:
                result = backend.call('/api/v1/videos/upload', body, content_type)
                if result.get('success') is not True or not result.get('object_key'):
                    raise ValueError('Upload outcome unconfirmed')
                entry.update(status='uploaded', object_key=result['object_key'], uploaded_at_utc=now())
                submitted += 1
                save()
                print(json.dumps({'uploaded_this_run': submitted, 'recorded_total': len(journal['videos']),
                                  'dataset_videos': len(videos), 'path': record['path']}), flush=True)
            except Exception as error:
                # Even an error can occur after storage accepted the object. Stop and reconcile.
                entry.update(error_type=type(error).__name__, http_status=getattr(error, 'code', None))
                journal['worker_status'] = 'needs_reconciliation'
                save()
                print(json.dumps({'status': 'needs_reconciliation', 'error_type': type(error).__name__,
                                  'http_status': getattr(error, 'code', None)}), flush=True)
                return 2
            if limit and submitted >= limit:
                journal['worker_status'] = 'batch_complete'
                save()
                return 0
            time.sleep(0.5)
        if not pending:
            complete = (all(record['path'] in journal['videos'] for record in videos)
                        and all(entry['status'] in ('uploaded', 'indexed')
                                for entry in journal['videos'].values()))
            journal['worker_status'] = 'all_uploaded' if complete else 'needs_reconciliation'
            save()
            return 0 if complete else 2
        if manifest['download_status'] in ('verified', 'partial_failure') and not ready:
            journal['worker_status'] = 'waiting_for_failed_downloads'
            save()
            return 1
        time.sleep(15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0, help='Upload at most this many new files; zero means all')
    args = parser.parse_args()
    try:
        with (ROOT / '.ingest.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raise SystemExit(run(args.limit))
    except Exception as error:
        # Never log response bodies, URLs, environment values, or credentials.
        print(json.dumps({'error_type': type(error).__name__, 'http_status': getattr(error, 'code', None)}), flush=True)
        raise SystemExit(1)
