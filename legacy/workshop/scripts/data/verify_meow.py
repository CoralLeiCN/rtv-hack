#!/usr/bin/env python3
"""Reconcile the upload journal with fully indexed VSS Explore records.

Run between upload batches; the shared lock prevents journal write races.
"""
import fcntl
import json
from ingest_meow import Backend, ROOT, atomic, now


def main():
    with (ROOT / '.ingest.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        journal_path = ROOT / 'ingestion.json'
        journal = json.loads(journal_path.read_text())
        all_uploads = {entry['object_key']: (path, entry)
                       for path, entry in journal['videos'].items() if entry.get('object_key')}
        targets = {entry['object_key']: entry for entry in journal['videos'].values()
                   if entry.get('object_key') and entry['status'] == 'uploaded'}
        links_path = ROOT / 'clip-links.json'
        links = json.loads(links_path.read_text()) if links_path.exists() else {
            'schema_version': 1, 'clips': {}}
        backend = Backend()
        offset = 0
        matched = 0
        while True:
            response = backend.call(f'/api/v1/videos/explore?scope=mine&limit=48&offset={offset}')
            rows = response['chunks']
            for row in rows:
                parent = row.get('original_video', '')
                # Object key is the URI path after s3://bucket/; never match basenames alone.
                key = parent.split('/', 3)[3] if parent.startswith('s3://') and parent.count('/') >= 3 else parent
                upload = all_uploads.get(key)
                if upload is None:
                    continue
                source_path, entry = upload
                if row.get('is_public') is not False:
                    raise ValueError('Indexed visibility differs from approved private setting')
                tags = row.get('tags') or []
                if isinstance(tags, str):
                    tags = [tag.strip() for tag in tags.split(',')]
                for segment in row.get('timeline') or []:
                    source = segment.get('source')
                    if not source:
                        continue
                    old = links['clips'].get(source)
                    if old and old['object_key'] != key:
                        raise ValueError('Clip source mapped to conflicting parent upload')
                    links['clips'][source] = {
                        'original_video_uri': parent, 'object_key': key,
                        'source_path': source_path, 'segment_number': segment.get('segment_number'),
                        'start_seconds': segment.get('segment_start_sec'),
                        'end_seconds': segment.get('segment_end_sec'),
                        'dataset_tag_present': 'meow-10k' in tags, 'observed_at_utc': now()}
                if key in targets:
                    entry.update(status='indexed', indexed_at_utc=now(),
                                 indexed_segments=row.get('total_segments'),
                                 indexing_evidence='VSS videos/explore fully-indexed parent')
                    del targets[key]
                    matched += 1
            offset += len(rows)
            if not rows or offset >= response['total']:
                break
        journal['updated_at_utc'] = now()
        atomic(journal_path, journal)
        links['updated_at_utc'] = now()
        atomic(links_path, links)
        print(json.dumps({'newly_verified_indexed': matched,
                          'total_indexed': sum(e['status'] == 'indexed' for e in journal['videos'].values()),
                          'uploaded_awaiting_index': len(targets),
                          'clips_linked_to_dataset': len(links['clips'])}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'http_status': getattr(error, 'code', None)}))
        raise SystemExit(1)
