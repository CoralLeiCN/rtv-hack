#!/usr/bin/env python3
"""Download the pinned public Meow-10k snapshot with a verified file manifest."""
import concurrent.futures
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

REPO = 'smgjch/meow-10k'
REVISION = '41e4014ef226bd822dec22be61cf5eee7f12088a'
ROOT = Path.home() / 'data/meow-10k'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temp, path)


def request(url):
    for attempt in range(8):
        try:
            return urllib.request.urlopen(urllib.request.Request(
                url, headers={'User-Agent': 'MeowDatasetDownloader/1.0'}), timeout=90)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 7:
                raise
            retry = error.headers.get('Retry-After', '')
            time.sleep(min(300, int(retry) if retry.isdigit() else 2 ** attempt + 5))
        except (OSError, TimeoutError):
            if attempt == 7:
                raise
            time.sleep(2 ** attempt)


def inventory():
    url = f'https://huggingface.co/api/datasets/{REPO}/tree/{REVISION}?recursive=true&limit=1000'
    files = {}
    while url:
        with request(url) as response:
            page = json.load(response)
            links = response.headers.get('Link', '')
        for item in page:
            if item['type'] != 'file':
                continue
            path = item['path']
            if Path(path).is_absolute() or '..' in Path(path).parts:
                raise ValueError('Unsafe repository path')
            lfs = item.get('lfs')
            files[path] = {
                'path': path, 'expected_size_bytes': item['size'],
                'source_url': f'https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/' + urllib.parse.quote(path),
                'expected_checksum': {'algorithm': 'sha256' if lfs else 'git-blob-sha1',
                                      'value': lfs['oid'] if lfs else item['oid']},
                'download_status': 'pending', 'ingestion_status': 'not_ingested',
            }
        url = None
        for link in links.split(','):
            if 'rel="next"' in link:
                url = link.split('<', 1)[1].split('>', 1)[0]
                if not url.startswith('https://huggingface.co/api/datasets/'):
                    raise ValueError('Unexpected pagination destination')
    return [files[key] for key in sorted(files)]


def checksum(path, record):
    if path.stat().st_size != record['expected_size_bytes']:
        return None
    sha = hashlib.sha256()
    git = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
            git.update(block)
    expected = record['expected_checksum']
    actual = sha.hexdigest() if expected['algorithm'] == 'sha256' else git.hexdigest()
    return sha.hexdigest() if actual == expected['value'] else None


def download(record):
    path = ROOT / record['path']
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try:
            actual = checksum(path, record) if path.exists() else None
            if not actual:
                partial = path.with_name(path.name + '.part')
                with request(record['source_url']) as response, partial.open('wb') as stream:
                    for block in iter(lambda: response.read(1024 * 1024), b''):
                        stream.write(block)
                actual = checksum(partial, record)
                if not actual:
                    raise ValueError('Checksum mismatch')
                os.replace(partial, path)
            return {'download_status': 'verified', 'sha256': actual,
                    'actual_size_bytes': path.stat().st_size, 'verified_at_utc': now()}
        except Exception as error:
            if attempt == 3:
                return {'download_status': 'failed', 'error_type': type(error).__name__,
                        'http_status': getattr(error, 'code', None)}
            time.sleep(2 ** attempt + 1)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / '.download.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest_path = ROOT / 'manifest.json'
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest['revision'] != REVISION:
                raise ValueError('Existing manifest uses a different revision')
        else:
            manifest = {'schema_version': 1, 'dataset': REPO, 'revision': REVISION,
                        'created_at_utc': now(), 'files': inventory()}
        files = manifest['files']
        manifest['download_status'] = 'in_progress'
        atomic(manifest_path, manifest)
        done = failed = size = 0
        last_save = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            # Make video data available early so ingestion can overlap download.
            ordered = sorted(files, key=lambda r: (not r['path'].endswith('.mp4'), r['path']))
            jobs = {executor.submit(download, record): record for record in ordered}
            for future in concurrent.futures.as_completed(jobs):
                record = jobs[future]
                result = future.result()
                if result['download_status'] == 'failed':
                    for key in ('sha256', 'actual_size_bytes', 'verified_at_utc'):
                        record.pop(key, None)
                record.update(result)
                done += 1
                failed += record['download_status'] == 'failed'
                size += record.get('actual_size_bytes', 0)
                if time.monotonic() - last_save > 15 or done == len(files):
                    manifest.update(updated_at_utc=now(), completed_files=done,
                                    failed_files=failed, verified_bytes=size)
                    atomic(manifest_path, manifest)
                    print(json.dumps({'completed': done, 'total': len(files),
                                      'failed': failed, 'verified_bytes': size}), flush=True)
                    last_save = time.monotonic()
        manifest['download_status'] = 'verified' if failed == 0 else 'partial_failure'
        manifest['completed_at_utc'] = now()
        atomic(manifest_path, manifest)
        raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
