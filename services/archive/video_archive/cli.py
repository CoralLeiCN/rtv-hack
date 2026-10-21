import argparse
import json
import logging
import time
from pathlib import Path
from uuid import UUID

from .config import Settings
from .index import VectorIndex
from .ingest import enqueue, work_once
from .media import MediaStore
from .maintenance import cleanup_vectors
from .models import Captioner, Embedder
from .repository import Repository


def main():
    parser = argparse.ArgumentParser(description='Manage the independent MicroDuck archive')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init', help='Create archive tables and Qdrant collection')
    ingest = commands.add_parser('ingest', help='Copy a local video and queue ingestion')
    ingest.add_argument('video', type=Path)
    ingest.add_argument('--dataset', required=True)
    ingest.add_argument('--tag', action='append', default=[])
    ingest.add_argument('--segment-seconds', type=int, default=10)
    ingest.add_argument('--captions', type=Path, help='JSON list of one exact caption per segment')
    worker = commands.add_parser('worker', help='Process durable jobs')
    worker.add_argument('--once', action='store_true')
    retry = commands.add_parser('retry', help='Requeue a failed/completed job, preserving IDs and captions')
    retry.add_argument('job_id', type=UUID)
    commands.add_parser('status')
    cleanup = commands.add_parser('cleanup-vectors', help='Inspect unreferenced vector points while holding the worker lock')
    cleanup.add_argument('--apply', action='store_true', help='Delete unreferenced points; default is a dry run')
    serve = commands.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=18001)
    args = parser.parse_args()
    for name in ('httpx', 'httpcore'):
        logging.getLogger(name).setLevel(logging.WARNING)
    index = None
    try:
        settings = Settings.from_env()
        settings.validate()
        repo, store = Repository(settings), MediaStore(settings.media_root)
        if args.command == 'serve':
            import uvicorn
            # Suppress framework traceback logging that could include private URLs.
            uvicorn.run('video_archive.api:app', host=args.host, port=args.port, access_log=False, log_level='critical')
        elif args.command == 'init':
            index = VectorIndex(settings)
            repo.initialize()
            index.initialize()
            store.ready()
            print('Archive initialized')
        elif args.command == 'ingest':
            captions = json.loads(args.captions.read_text()) if args.captions else None
            print(enqueue(repo, store, settings, args.video, args.dataset, args.tag, args.segment_seconds, captions))
        elif args.command == 'status':
            print(json.dumps(repo.jobs(), default=str))
        elif args.command == 'retry':
            repo.retry(args.job_id)
            print('Job queued')
        elif args.command == 'cleanup-vectors':
            index = VectorIndex(settings)
            index.ready()
            print(json.dumps(cleanup_vectors(repo, index, apply=args.apply)))
        elif args.command == 'worker':
            index = VectorIndex(settings)
            index.ready()
            embedder, captioner = Embedder(settings), Captioner(settings)
            while True:
                worked = work_once(repo, store, index, embedder, captioner, settings)
                if args.once:
                    break
                if not worked:
                    time.sleep(5)
    except KeyboardInterrupt:
        pass
    except Exception:
        parser.exit(1, 'Archive operation failed. Check configuration, service readiness and input files. Private diagnostics were suppressed.\n')
    finally:
        if index:
            index.close()


if __name__ == '__main__':
    main()
