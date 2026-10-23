"""Stage failures remain actionable without leaking private exception text."""
from contextlib import contextmanager
import json
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest

from video_archive import ingest
from video_archive.config import Settings
from video_archive.media import MediaStore
from video_archive.models import embedding_identity


@pytest.mark.parametrize('failure', ['configuration', 'media', 'captioning', 'embedding', 'indexing', 'database', None])
def test_worker_records_stage_ids_and_timings_without_private_diagnostics(tmp_path, monkeypatch, caplog, failure):
    settings = Settings(media_root=tmp_path)
    job = {'id': uuid4(), 'video_id': uuid4(), 'settings': {
        'embedding_identity': 'mismatch' if failure == 'configuration' else embedding_identity(settings),
        'cosmos_model': settings.cosmos_model, 'cosmos_revision': settings.cosmos_revision,
        'captions': None, 'duration': 1, 'segment_seconds': 1, 'dataset_id': 'fixture', 'tags': []}}
    finished, published = [], []
    private = 'private-password https://private.invalid/source /private/source.mp4'

    def operation(stage, result=None):
        def call(*args):
            if failure == stage:
                raise RuntimeError(private)
            return result
        return call

    class Repository:
        @contextmanager
        def worker_lock(self):
            yield self

        def next_job(self):
            return job

        def finish(self, identifier, error=None):
            finished.append((identifier, error))

        assert_worker = staticmethod(lambda: None)
        video = staticmethod(lambda identifier: {'storage_key': 'fixture.mp4'})
        segment = staticmethod(lambda identifier: None)
        save_segment = staticmethod(operation('database'))
        mark_indexed = staticmethod(lambda identifier: published.append(identifier))

    def transcode(args):
        if failure == 'media':
            raise RuntimeError(private)
        from pathlib import Path
        Path(args[-1]).write_bytes(b'fixture')

    monkeypatch.setattr(ingest, 'run_media', transcode)
    monkeypatch.setattr(ingest, 'validate_video', lambda path: None)
    index = SimpleNamespace(upsert=operation('indexing'))
    embedder = SimpleNamespace(encode=operation('embedding', [1.] + [0.] * 767))
    captioner = SimpleNamespace(caption=operation('captioning', 'A fixture cat walks.'))
    with caplog.at_level(logging.INFO, logger='video_archive.ingest'):
        assert ingest.work_once(Repository(), MediaStore(tmp_path), index, embedder, captioner, settings)
    assert finished == [(job['id'], failure + '_failed' if failure else None)]
    assert bool(published) == (failure is None)
    events = [json.loads(record.message) for record in caplog.records]
    assert events and all(event['job_id'] == str(job['id']) for event in events)
    assert all(isinstance(event['elapsed_ms'], int) and event['elapsed_ms'] >= 0 for event in events)
    if failure:
        failed = [event for event in events if event['status'] == 'failed']
        assert len(failed) == 1 and failed[0]['stage'] == failure
        assert failed[0]['error_code'] == failure + '_failed'
        assert bool(failed[0]['segment_id']) == (failure != 'configuration')
    assert private not in caplog.text and 'Traceback' not in caplog.text
    assert 'fixture.mp4' not in caplog.text and 'fixture cat' not in caplog.text


def test_nested_database_failure_keeps_the_innermost_stage(caplog):
    progress = ingest.IngestionProgress(uuid4())
    with pytest.raises(RuntimeError):
        with progress.stage('media', uuid4()):
            with progress.stage('database'):
                raise RuntimeError('private-connection-string')
    assert progress.error_code == 'database_failed'
    assert 'private-connection-string' not in caplog.text
