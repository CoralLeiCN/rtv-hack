from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import psycopg
import pytest
from qdrant_client import QdrantClient

from video_archive.api import create_app
from video_archive.config import Settings
from video_archive.index import VectorIndex, validate_vector
from video_archive.ingest import duration, enqueue, work_once, validate_video
from video_archive.media import MediaStore, media_id
from video_archive.maintenance import cleanup_vectors
from video_archive.models import Captioner, embedding_identity
from video_archive.repository import Repository


class FixtureEmbedding:
    def encode(self, text, query=False):
        vector = [0.0] * 768
        vector[0 if 'deer' in text.lower() else 1] = 1.0
        return vector


class NoCaptioner:
    def caption(self, path):
        pytest.fail('Imported captions must avoid a model call')


@pytest.fixture
def archive(tmp_path):
    dsn = os.environ.get('TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Run services/archive/Dockerfile.test for disposable Postgres + FFmpeg integration')
    settings = Settings(database_url=dsn, api_key='fixture-key', media_root=tmp_path, collection='test_' + uuid4().hex)
    repo = Repository(settings)
    repo.initialize()
    with repo.connect() as conn:
        conn.execute('TRUNCATE archive_segments, archive_jobs, archive_videos CASCADE')
    index = VectorIndex(settings, QdrantClient(':memory:'))
    index.initialize()
    store = MediaStore(tmp_path)
    yield settings, repo, index, store
    index.close()


@pytest.fixture
def video(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg/FFprobe required; use the integration test container')
    path = tmp_path / 'input.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=64x64:r=10',
                    '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)
    return path


def submit(archive, video):
    settings, repo, index, store = archive
    job_id = enqueue(repo, store, settings, video, 'animal-fixture', ['wildlife'], 1,
                     ['A deer walks forward.', 'A cat sits down.'])
    return job_id


def test_real_ingest_search_metadata_and_local_playback(archive, video):
    settings, repo, index, store = archive
    job_id = submit(archive, video)
    assert submit(archive, video) == job_id
    assert len(repo.jobs()) == 1
    assert work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.jobs()[0]['status'] == 'complete'
    assert not work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    app = create_app(settings, repo, index, FixtureEmbedding(), store)
    with TestClient(app) as client:
        auth = {'Authorization': 'Bearer fixture-key'}
        assert client.get('/health').status_code == 200
        assert client.get('/ready', headers=auth).status_code == 200
        assert client.post('/api/v1/search', json={'query': 'deer'}).status_code == 401
        response = client.post('/api/v1/search', headers=auth, json={'query': 'deer', 'tags': ['wildlife']})
        rows = response.json()['results']
        assert len(rows) == 2 and rows[0]['reasoning_content'] == 'A deer walks forward.'
        assert rows[0]['segment_start_sec'] == 0 and rows[1]['segment_start_sec'] == 1
        assert rows[0]['original_video'] == rows[1]['original_video']
        assert str(settings.media_root) not in response.text
        assert client.get('/api/v1/metadata', headers=auth).json() == {'tags': ['wildlife'], 'datasets': ['animal-fixture']}
        assert client.post('/api/v1/search', headers=auth, json={'query': 'deer', 'tags': ['missing']}).json()['results'] == []
        full = client.get('/api/v1/videos/stream', headers=auth, params={'source': rows[0]['source']})
        assert full.status_code == 200 and b'ftyp' in full.content[:32]
        partial = client.get('/api/v1/videos/stream', headers={**auth, 'Range': 'bytes=3-12'}, params={'source': rows[0]['source']})
        assert partial.status_code == 206 and partial.content == full.content[3:13]
        head = client.head('/api/v1/videos/stream', headers=auth, params={'source': rows[0]['source']})
        assert head.content == b'' and int(head.headers['content-length']) == len(full.content)
        assert client.get('/api/v1/videos/stream', headers=auth, params={'source': 'file:///etc/passwd'}).status_code == 404


def test_failed_upsert_is_hidden_and_retry_preserves_evidence(archive, video):
    settings, repo, index, store = archive
    job_id = submit(archive, video)
    class BrokenIndex:
        def upsert(self, row, vector):
            raise RuntimeError('private-password')
    assert work_once(repo, store, BrokenIndex(), FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.jobs()[0]['status'] == 'pending'
    assert repo.jobs()[0]['error_code'] == 'ingestion_failed'
    with repo.connect() as conn:
        first = conn.execute('SELECT * FROM archive_segments').fetchone()
    assert not first['indexed']
    repo.retry(job_id)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.segment(first['id'])['caption'] == first['caption']
    assert repo.segment(first['id'])['indexed']
    assert repo.jobs()[0]['status'] == 'complete'
    # A deleted vector collection can be rebuilt from the same stable IDs.
    index.client.delete_collection(settings.collection)
    index.initialize()
    repo.retry(job_id)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    assert index.client.count(settings.collection).count == 2


def test_retry_limit_and_crashed_job_recovery(archive, video):
    settings, repo, index, store = archive
    submit(archive, video)
    job = repo.next_job()  # Simulate a crash after claiming, before any output.
    assert job['status'] == 'running'
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.jobs()[0]['status'] == 'complete'
    assert repo.jobs()[0]['attempts'] == 2
    repo.retry(job['id'])
    class BrokenEmbedding:
        def encode(self, *args, **kwargs):
            raise ValueError('private-key')
    for _ in range(3):
        work_once(repo, store, index, BrokenEmbedding(), NoCaptioner(), settings)
        with repo.connect() as conn:
            conn.execute('UPDATE archive_jobs SET available_at=now()')
    assert repo.jobs()[0]['status'] == 'failed'
    assert repo.jobs()[0]['attempts'] == 3
    assert not work_once(repo, store, index, BrokenEmbedding(), NoCaptioner(), settings)


def test_worker_excludes_concurrent_worker(archive):
    _, repo, _, _ = archive
    with repo.worker_lock():
        with pytest.raises(ValueError, match='Another archive worker'):
            with repo.worker_lock():
                pass


def test_successful_retries_remove_previous_points_after_publication(archive, video):
    settings, repo, index, store = archive
    job_id = submit(archive, video)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    with repo.connect() as conn:
        original = conn.execute('SELECT * FROM archive_segments ORDER BY start_sec').fetchall()
    for _ in range(2):
        repo.retry(job_id)
        work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
        assert repo.jobs()[0]['status'] == 'complete'
        assert index.client.count(settings.collection).count == 2
    assert index.client.retrieve(settings.collection, [str(row['index_id']) for row in original]) == []
    for row in original:
        current = repo.segment(row['id'])
        assert current['indexed'] and current['caption'] == row['caption']
        assert current['index_id'] != row['index_id']


def test_cleanup_failure_does_not_retry_a_published_job(archive, video, monkeypatch, caplog):
    settings, repo, index, store = archive
    job_id = submit(archive, video)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    def unavailable(ids):
        raise RuntimeError('private-cleanup-key')
    monkeypatch.setattr(index, 'delete', unavailable)
    repo.retry(job_id)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.jobs()[0]['status'] == 'complete'
    assert repo.jobs()[0]['error_code'] is None
    assert 'cleanup deferred' in caplog.text
    assert 'private-cleanup-key' not in caplog.text
    assert index.client.count(settings.collection).count == 4


def test_orphan_cleanup_retains_unpublished_and_other_model_references(archive, video):
    settings, repo, index, store = archive
    submit(archive, video)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    with repo.connect() as conn:
        conn.execute("UPDATE archive_segments SET indexed=false, embedding_identity='other-model', tags=ARRAY['other'] WHERE start_sec=0")
        row = conn.execute('SELECT * FROM archive_segments LIMIT 1').fetchone()
    orphan = {**row, 'index_id': uuid4()}
    index.upsert(orphan, FixtureEmbedding().encode('deer'))
    assert cleanup_vectors(repo, index) == {'scanned': 3, 'orphaned': 1, 'deleted': 0}
    assert cleanup_vectors(repo, index, apply=True) == {'scanned': 3, 'orphaned': 1, 'deleted': 1}
    assert index.client.count(settings.collection).count == 2
    with repo.worker_lock(), pytest.raises(ValueError, match='Another archive worker'):
        cleanup_vectors(repo, index, apply=True)


def test_lost_worker_cannot_publish_or_overwrite_successor_vectors(archive, video):
    settings, repo, index, store = archive
    submit(archive, video)
    stale = []

    class DelayedIndex:
        def upsert(self, row, vector):
            stale.append(row)
            # Simulate disconnect after a remote upsert was sent but before it
            # completed. The replacement worker finishes before that old write.
            with repo.connect() as conn:
                pid = conn.execute("SELECT pid FROM pg_locks WHERE locktype='advisory' AND objid=847203315").fetchone()['pid']
                conn.execute('SELECT pg_terminate_backend(%s)', (pid,))
            assert work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
            index.upsert(row, [0.0, 1.0] + [0.0] * 766)

    with pytest.raises(psycopg.Error):
        work_once(repo, store, DelayedIndex(), FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.jobs()[0]['status'] == 'complete'
    assert repo.jobs()[0]['attempts'] == 2
    assert len(stale) == 1
    current = repo.segment(stale[0]['id'])
    assert current['indexed'] and current['index_id'] != stale[0]['index_id']
    assert repo.indexed([stale[0]['index_id']], [], embedding_identity(settings)) == {}
    points = index.client.retrieve(settings.collection, [str(current['index_id'])], with_vectors=True)
    assert points[0].vector == FixtureEmbedding().encode(current['caption'])
    with TestClient(create_app(settings, repo, index, FixtureEmbedding(), store)) as client:
        results = client.post('/api/v1/search', json={'query': 'deer'}, headers={'Authorization': 'Bearer fixture-key'}).json()['results']
        assert len(results) == 2
        assert results[0]['reasoning_content'] == 'A deer walks forward.'


def test_lost_worker_cannot_finish_job_via_a_new_connection(archive, video):
    settings, repo, index, store = archive
    submit(archive, video)
    with pytest.raises(psycopg.Error):
        with repo.worker_lock() as worker:
            job = worker.next_job()
            with repo.connect() as conn:
                pid = conn.execute("SELECT pid FROM pg_locks WHERE locktype='advisory' AND objid=847203315").fetchone()['pid']
                conn.execute('SELECT pg_terminate_backend(%s)', (pid,))
            assert work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
            with pytest.raises(psycopg.Error):
                worker.finish(job['id'], 'ingestion_failed')
    assert repo.jobs()[0]['status'] == 'complete'


def test_audio_tail_does_not_create_extra_video_segments(archive, tmp_path):
    settings, repo, index, store = archive
    source = tmp_path / 'audio-tail.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=64x64:r=10:d=2',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', '-c:v', 'libx264',
                    '-c:a', 'aac', str(source)], check=True)
    enqueue(repo, store, settings, source, 'fixture', [], 1, ['First video second', 'Second video second'])
    assert work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.jobs()[0]['status'] == 'complete'
    with repo.connect() as conn:
        rows = conn.execute('SELECT * FROM archive_segments ORDER BY start_sec').fetchall()
    assert [(row['start_sec'], row['end_sec']) for row in rows] == [(0, 1), (1, 2)]
    assert all(row['indexed'] for row in rows)
    for row in rows:
        validate_video(store.path(row['storage_key']))


def test_audio_only_output_is_not_published(archive, video, monkeypatch, tmp_path):
    import video_archive.ingest as ingestion
    settings, repo, index, store = archive
    submit(archive, video)
    audio = tmp_path / 'audio-only.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1',
                    '-c:a', 'aac', str(audio)], check=True)
    real_run = ingestion.run_media

    def faulty_transcode(args):
        if '-c:v' in args:
            shutil.copyfile(audio, args[-1])
            return b''
        return real_run(args)

    monkeypatch.setattr(ingestion, 'run_media', faulty_transcode)
    assert work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.jobs()[0]['error_code'] == 'ingestion_failed'
    assert index.client.count(settings.collection).count == 0
    with repo.connect() as conn:
        assert conn.execute('SELECT count(*) AS n FROM archive_segments').fetchone()['n'] == 0
    assert not list(store.root.glob('segments/**/*.mp4'))


@pytest.mark.parametrize('frame_count,filter_expression', [
    (1, 'null'),
    (20, 'null'),
    (20, 'setpts=PTS+5/TB'),
    (20, "select='not(eq(n,1)+eq(n,4)+eq(n,8))'"),
])
def test_decoded_video_duration_includes_final_frame(tmp_path, frame_count, filter_expression):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg/FFprobe required; use the integration test container')
    source = tmp_path / 'video.webm'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    f'color=c=green:s=64x64:r=10:d={frame_count / 10}',
                    '-vf', filter_expression, '-fps_mode', 'vfr', '-c:v', 'libvpx-vp9', str(source)], check=True)
    assert duration(source) == pytest.approx(frame_count / 10)


def test_missing_stream_duration_uses_video_timeline(archive, tmp_path):
    settings, repo, index, store = archive
    source = tmp_path / 'audio-tail.webm'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=64x64:r=10:d=2',
                    '-f', 'lavfi', '-i', 'sine=duration=3', '-c:v', 'libvpx-vp9',
                    '-c:a', 'libopus', str(source)], check=True)
    assert duration(source) == pytest.approx(2.0)
    enqueue(repo, store, settings, source, 'fixture', [], 1, ['First second', 'Second second'])
    assert work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    assert repo.jobs()[0]['status'] == 'complete'
    assert index.client.count(settings.collection).count == 2
    with repo.connect() as conn:
        rows = conn.execute('SELECT * FROM archive_segments ORDER BY start_sec').fetchall()
    assert [(row['start_sec'], row['end_sec']) for row in rows] == [(0, 1), (1, 2)]
    # Correct metadata must also preserve the final decoded frame after cutting.
    frame_counts = []
    for row in rows:
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-count_frames', '-show_entries', 'stream=nb_read_frames', '-of', 'json',
            str(store.path(row['storage_key']))], check=True, capture_output=True)
        frame_counts.append(int(json.loads(result.stdout)['streams'][0]['nb_read_frames']))
    assert frame_counts == [10, 10]


def test_schema_upgrade_preserves_existing_vector_ids(archive, video):
    settings, repo, index, store = archive
    submit(archive, video)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    # Represent the previous schema, where vector IDs were the segment IDs.
    with repo.connect() as conn:
        conn.execute('ALTER TABLE archive_segments DROP COLUMN index_id')
    repo.initialize()
    repo.initialize()  # Upgrade is repeatable.
    with repo.connect() as conn:
        rows = conn.execute('SELECT id,index_id FROM archive_segments').fetchall()
    assert all(row['id'] == row['index_id'] for row in rows)
    assert len(repo.indexed([row['id'] for row in rows], [], embedding_identity(settings))) == 2


def test_stale_vector_payload_cannot_bypass_postgres_filter_or_publication(archive, video):
    settings, repo, index, store = archive
    submit(archive, video)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    with repo.connect() as conn:
        conn.execute("UPDATE archive_segments SET tags=ARRAY['private'] WHERE start_sec=0")
        conn.execute('UPDATE archive_segments SET indexed=false WHERE start_sec=1')
    with TestClient(create_app(settings, repo, index, FixtureEmbedding(), store)) as client:
        response = client.post('/api/v1/search', json={'query': 'deer', 'tags': ['wildlife']}, headers={'Authorization': 'Bearer fixture-key'})
        assert response.json()['results'] == []


def test_mismatched_caption_count_never_queues(archive, video):
    settings, repo, _, store = archive
    with pytest.raises(ValueError, match='Caption count'):
        enqueue(repo, store, settings, video, 'fixture', [], 1, ['Only one caption'])
    assert repo.jobs() == []


def test_changed_model_identity_cannot_process_old_job(archive, video):
    settings, repo, index, store = archive
    submit(archive, video)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), replace(settings, embedding_revision='new-revision'))
    assert repo.jobs()[0]['error_code'] == 'ingestion_failed'
    assert index.client.count(settings.collection).count == 0


def test_filesystem_ranges_containment_and_if_range(tmp_path):
    store = MediaStore(tmp_path / 'media')
    store.ready()
    store.path('clip.mp4').write_bytes(b'0123456789')
    outside = tmp_path / 'private'
    outside.write_text('secret')
    (store.root / 'escape').symlink_to(outside)
    for key in ('../private', '/etc/passwd', 'escape', 'a/../../private', 'a\\..\\private'):
        with pytest.raises(ValueError):
            store.path(key)
    app = FastAPI()
    @app.get('/video')
    def video_route(range: str = '', if_range: str = ''):
        return store.response('clip.mp4', 'GET', range, if_range)
    with TestClient(app) as client:
        full = client.get('/video')
        for value, content in [('bytes=2-4', b'234'), ('bytes=-3', b'789'), ('bytes=8-', b'89')]:
            result = client.get('/video', params={'range': value})
            assert result.status_code == 206 and result.content == content
        for value in ('bytes=99-', 'bytes=-0', 'bytes=5-3', 'bytes=0-1,3-4', 'bytes=-'):
            assert client.get('/video', params={'range': value}).status_code == 416
        assert client.get('/video', params={'range': 'bytes=2-4', 'if_range': '"old"'}).content == full.content
        assert client.get('/video', params={'range': 'bytes=2-4', 'if_range': full.headers['etag']}).content == b'234'


def test_cosmos_request_uses_configured_model_video_and_private_header(tmp_path):
    path = tmp_path / 'clip.mp4'
    path.write_bytes(b'fixture-video')
    def handler(request):
        assert request.headers['authorization'] == 'Bearer private-model-key'
        assert request.url.path == '/v1/chat/completions'
        body = json.loads(request.content)
        assert body['model'] == 'nvidia/Cosmos3-Nano'
        assert body['messages'][0]['content'][0]['video_url']['url'].startswith('data:video/mp4;base64,')
        assert str(path) not in request.content.decode()
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '<think>internal</think>A deer walks.'}}]})
    captioner = Captioner(Settings(cosmos_api_key='private-model-key'), httpx.MockTransport(handler))
    assert captioner.caption(path) == 'A deer walks.'
    bad = Captioner(Settings(), httpx.MockTransport(lambda r: httpx.Response(200, json={
        'choices': [{'finish_reason': 'length', 'message': {'content': 'A deer'}}]})))
    with pytest.raises(ValueError, match='Incomplete'):
        bad.caption(path)


def test_invalid_vectors_and_media_ids_are_rejected():
    for vector in ([0.0]*768, [1.0]*256, [float('nan')]*768, [float('inf')]*768):
        with pytest.raises(ValueError):
            validate_vector(vector)
    for source in ('media://../foo', 'file:///etc/passwd', 'media://' + str(uuid4()) + '?x=y'):
        with pytest.raises(ValueError):
            media_id(source)


def test_archive_errors_redact_configuration(tmp_path):
    class FailingRepository:
        def metadata(self):
            raise RuntimeError('postgres://private-password@private-host')
    settings = Settings(api_key='test-secret', media_root=tmp_path)
    with TestClient(create_app(settings, repo=FailingRepository()), raise_server_exceptions=False) as client:
        response = client.get('/api/v1/metadata', headers={'Authorization': 'Bearer test-secret'})
        assert response.status_code == 503 and 'private' not in response.text
        response = client.post('/api/v1/search', headers={'Authorization': 'Bearer test-secret'}, json={'query': ' ', 'secret': 'private'})
        assert response.status_code == 422 and 'private' not in response.text


def test_both_applications_use_new_archive_and_session_scoped_media(archive, video):
    from ranger_duck.app import create_app as ranger_app
    from ranger_duck.config import Settings as AppSettings
    from ranger_duck.encounter_agent import EncounterQueryDecision, EncounterActionsDecision
    from server import create_app as search_app

    class Agent:
        available = True
        async def decide(self, context, schema):
            if schema is EncounterQueryDecision:
                return EncounterQueryDecision(query='Deer walking together', individual_query='A deer walks alone', reason='Find visible walking.')
            # Explicit decisions for the two synthetic captions supplied by
            # submit(); production context lists capabilities, not a selection.
            fixture_actions = {'A deer walks forward.': 'short_walk', 'A cat sits down.': None}
            actions = []
            for candidate in context['candidates']:
                primitive = fixture_actions[candidate['caption']]
                assert 'preferred_action' not in candidate
                assert primitive is None or primitive in candidate['allowed_actions']
                actions.append({'candidate_id': candidate['candidate_id'],
                    'decision': 'imitate' if primitive else 'skip', 'primitive': primitive,
                    'evidence_excerpt': candidate['caption'] if primitive else '',
                    'reason': 'Use the observed deer walk.' if primitive else 'The cat is not the selected species.'})
            return EncounterActionsDecision(summary='Imitate supported walking.', actions=actions)

    settings, repo, index, store = archive
    submit(archive, video)
    work_once(repo, store, index, FixtureEmbedding(), NoCaptioner(), settings)
    upstream = create_app(settings, repo, index, FixtureEmbedding(), store)
    transport = httpx.ASGITransport(app=upstream)
    with TestClient(search_app('http://archive.test', transport, settings.api_key)) as client:
        rows = client.post('/api/v1/search', json={'query': 'deer'}).json()['results']
        assert rows[0]['reasoning_content'] == 'A deer walks forward.'
        assert client.get('/api/v1/videos/stream', params={'source': rows[0]['source']}, headers={'Range': 'bytes=0-15'}).status_code == 206
    app = ranger_app(AppSettings(archive_url='http://archive.test', api_key=settings.api_key),
                     httpx.ASGITransport(app=upstream), loop_agent=Agent())
    with TestClient(app) as client:
        result = client.post('/demo-api/search', json={'encounter_id': 'local-test', 'scenario_id': 'deer-walking'})
        assert result.status_code == 200
        candidate = result.json()['candidates'][0]
        assert candidate['action']['primitive'] == 'short_walk'
        assert 'media://' not in result.text and str(store.root) not in result.text
        clip = client.get(candidate['video_url'], headers={'Range': 'bytes=0-15'})
        assert clip.status_code == 206 and b'ftyp' in clip.content
        client.cookies.clear()
        assert client.get(candidate['video_url']).status_code == 404


def test_neon_pooler_cannot_be_used_for_worker_session_lock():
    repo = Repository(Settings(database_url='postgresql://user:password@project-pooler.neon.tech/db'))
    with pytest.raises(ValueError, match='direct Postgres URL'):
        repo.connect(worker=True)
