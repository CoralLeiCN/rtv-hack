#!/usr/bin/env python3
"""Run bounded upload batches and reconcile indexing without changing VSS services."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time
from ingest_meow import ROOT, atomic, now


def run_script(name, *args):
    result = subprocess.run([sys.executable, str(ROOT / name), *args],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def status(phase, **extra):
    value = {'phase': phase, 'updated_at_utc': now(), **extra}
    atomic(ROOT / 'pipeline-status.json', value)
    print(json.dumps(value), flush=True)


def main(max_pending=100):
    with (ROOT / '.pipeline.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        last_indexed = -1
        last_progress = time.monotonic()
        while True:
            if not run_script('verify_meow.py'):
                status('verification_failed', detail='Inspect VSS access before resuming; no new batch submitted')
                return 1
            if not run_script('summarize_meow.py'):
                status('provenance_update_failed')
                return 1
            manifest = json.loads((ROOT / 'manifest.json').read_text())
            journal = json.loads((ROOT / 'ingestion.json').read_text())
            indexed = sum(v['status'] == 'indexed' for v in journal['videos'].values())
            awaiting = sum(v['status'] == 'uploaded' for v in journal['videos'].values())
            videos = sum(r['path'].lower().endswith('.mp4') for r in manifest['files'])
            if indexed > last_indexed:
                last_indexed, last_progress = indexed, time.monotonic()
            if any(v['status'] not in ('uploaded', 'indexed') for v in journal['videos'].values()):
                status('needs_reconciliation', indexed=indexed, awaiting_index=awaiting)
                return 1
            if indexed == videos:
                if manifest['download_status'] == 'verified':
                    status('complete', indexed=indexed, source_files=len(manifest['files']))
                    return 0
                if manifest['download_status'] == 'partial_failure':
                    status('companion_downloads_incomplete', indexed=indexed)
                    return 1
                status('waiting_for_companion_downloads', indexed=indexed)
                time.sleep(45)
                continue
            # Confirm the first batch works, then limit acknowledged uploads
            # waiting for the shared pipeline.
            if (indexed == 0 and awaiting) or awaiting >= max_pending or indexed + awaiting == videos:
                status('waiting_for_indexing', indexed=indexed, awaiting_index=awaiting,
                       remaining_to_upload=videos-indexed-awaiting, max_pending=max_pending)
                if time.monotonic() - last_progress > 1800:
                    status('indexing_stalled', indexed=indexed, awaiting_index=awaiting,
                           detail='No indexing progress for 30 minutes; uploads stopped')
                    return 1
                time.sleep(45)
                continue
            status('uploading_batch', indexed=indexed, awaiting_index=awaiting,
                   remaining_to_upload=videos-indexed-awaiting, max_pending=max_pending)
            if not run_script('ingest_meow.py', '--limit', str(min(25, max_pending - awaiting))):
                run_script('summarize_meow.py')
                status('upload_worker_stopped', detail='Inspect ingestion journal before resuming')
                return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-pending', type=int, default=100,
                        help='Maximum acknowledged uploads awaiting indexing')
    args = parser.parse_args()
    if args.max_pending < 1:
        parser.error('--max-pending must be positive')
    try:
        raise SystemExit(main(args.max_pending))
    except Exception as error:
        status('error', error_type=type(error).__name__)
        raise SystemExit(1)
