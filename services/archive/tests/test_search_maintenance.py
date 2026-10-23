"""Search sizing and maintenance checks without external services or models."""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from qdrant_client import QdrantClient, models

from video_archive.api import MAX_SEARCH_REQUESTS, create_app
from video_archive.config import Settings
from video_archive.index import VectorIndex
from video_archive import ingest
from video_archive.maintenance import cleanup_vectors
from video_archive.media import MediaStore
from video_archive.models import embedding_identity


VECTOR = [1.0] + [0.0] * 767
AUTH = {'Authorization': 'Bearer fixture-key'}


class FixtureEmbedding:
    def encode(self, text, query=False):
        assert query
        return VECTOR


class SearchIndex:
    def __init__(self, ids):
        self.hits = [SimpleNamespace(id=value, score=1 - i / 2000) for i, value in enumerate(ids)]
        self.calls = []

    def search(self, vector, tags, limit, identity, offset=0):
        self.calls.append((limit, offset, tags, identity))
        return self.hits[offset:offset + limit]

    def close(self):
        pass


class SearchRepository:
    def __init__(self, ids):
        self.ids = set(ids)
        self.calls = []

    def indexed(self, ids, tags, identity):
        self.calls.append((ids, tags, identity))
        return {value: {'id': value, 'video_id': str(UUID(int=10000)),
                       'caption': 'Fixture caption ' + value, 'start_sec': 0,
                       'end_sec': 1, 'dataset_id': 'fixture'}
                for value in ids if value in self.ids}


def search_client(tmp_path, ids, accepted):
    settings = Settings(database_url='postgresql://unused', api_key='fixture-key', media_root=tmp_path)
    index, repo = SearchIndex(ids), SearchRepository(accepted)
    client = TestClient(create_app(settings, repo, index, FixtureEmbedding()))
    return client, index, repo, settings


@pytest.mark.parametrize('top_k', [1, 15, 100])
def test_clean_search_requests_only_top_k_once(tmp_path, top_k):
    ids = [str(UUID(int=i + 1)) for i in range(200)]
    client, index, repo, settings = search_client(tmp_path, ids, ids)
    with client:
        response = client.post('/api/v1/search', json={'query': 'deer', 'tags': ['wildlife'], 'top_k': top_k}, headers=AUTH)
    assert response.status_code == 200
    assert [row['source'] for row in response.json()['results']] == ['media://' + value for value in ids[:top_k]]
    assert index.calls == [(top_k, 0, ['wildlife'], embedding_identity(settings))]
    assert repo.calls == [(ids[:top_k], ['wildlife'], embedding_identity(settings))]


def test_search_refills_only_shortfall_and_preserves_rank(tmp_path):
    ids = [str(UUID(int=i + 1)) for i in range(6)]
    accepted = [ids[1], ids[4], ids[5]]
    client, index, repo, settings = search_client(tmp_path, ids, accepted)
    with client:
        response = client.post('/api/v1/search', json={'query': 'deer', 'top_k': 3}, headers=AUTH)
    assert response.status_code == 200
    rows = response.json()['results']
    assert [row['source'] for row in rows] == ['media://' + value for value in accepted]
    assert [row['similarity_score'] for row in rows] == [index.hits[i].score for i in (1, 4, 5)]
    assert [(limit, offset) for limit, offset, *_ in index.calls] == [(3, 0), (2, 3), (1, 5)]
    assert len(repo.calls) == 3


def test_short_page_returns_actual_partial_results(tmp_path):
    ids = [str(uuid4()) for _ in range(4)]
    client, index, _, _ = search_client(tmp_path, ids, ids[:1])
    with client:
        response = client.post('/api/v1/search', json={'query': 'deer', 'top_k': 3}, headers=AUTH)
    assert response.status_code == 200
    assert len(response.json()['results']) == 1
    assert [(limit, offset) for limit, offset, *_ in index.calls] == [(3, 0), (2, 3)]


def test_empty_index_is_a_successful_no_match(tmp_path):
    client, index, _, _ = search_client(tmp_path, [], [])
    with client:
        response = client.post('/api/v1/search', json={'query': 'deer'}, headers=AUTH)
    assert response.status_code == 200 and response.json() == {'results': []}
    assert len(index.calls) == 1


@pytest.mark.parametrize('accepted_count', [0, 1])
def test_search_limit_never_masquerades_as_complete_results(tmp_path, accepted_count):
    ids = [str(uuid4()) for _ in range(1001)]
    client, index, _, _ = search_client(tmp_path, ids, ids[:accepted_count] + ids[-1:])
    with client:
        response = client.post('/api/v1/search', json={'query': 'deer'}, headers=AUTH)
    assert response.status_code == 503
    assert response.json() == {'detail': 'search_limit_reached'}
    assert len(index.calls) == MAX_SEARCH_REQUESTS
    assert index.calls[0][0] == 15
    assert all(call[0] == 15 - accepted_count for call in index.calls[1:])


def test_last_permitted_page_can_satisfy_the_search(tmp_path):
    ids = [str(uuid4()) for _ in range(MAX_SEARCH_REQUESTS)]
    client, index, _, _ = search_client(tmp_path, ids, ids[-1:])
    with client:
        response = client.post('/api/v1/search', json={'query': 'deer', 'top_k': 1}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()['results'][0]['source'] == 'media://' + ids[-1]
    assert len(index.calls) == MAX_SEARCH_REQUESTS


def test_duplicate_hits_during_index_changes_do_not_duplicate_results(tmp_path):
    first, second = str(uuid4()), str(uuid4())
    client, index, _, _ = search_client(tmp_path, [first, first, second], [first, second])
    with client:
        response = client.post('/api/v1/search', json={'query': 'deer', 'top_k': 2}, headers=AUTH)
    assert [row['source'] for row in response.json()['results']] == ['media://' + first, 'media://' + second]
    assert len(index.calls) == 2


class MaintenanceRepository:
    def __init__(self, referenced):
        self.referenced = set(referenced)
        self.locked = False
        self.connection_alive = True
        self.lookups = []

    @contextmanager
    def worker_lock(self):
        if self.locked:
            raise ValueError('Another archive worker is active')
        self.locked = True
        try:
            yield self
        finally:
            self.locked = False

    def assert_worker(self):
        assert self.locked
        if not self.connection_alive:
            raise RuntimeError('Worker connection lost')

    def referenced_index_ids(self, ids):
        self.assert_worker()
        self.lookups.append(list(ids))
        return self.referenced.intersection(ids)


def test_cleanup_dry_run_apply_pagination_and_idempotence(tmp_path):
    settings = Settings(media_root=tmp_path)
    index = VectorIndex(settings, QdrantClient(':memory:'))
    index.initialize()
    ids = [str(UUID(int=i + 1)) for i in range(205)]
    index.client.upsert(settings.collection, points=[models.PointStruct(id=value, vector=VECTOR) for value in ids], wait=True)
    repo = MaintenanceRepository([ids[0], ids[100], ids[-1]])
    try:
        assert cleanup_vectors(repo, index) == {'scanned': 205, 'orphaned': 202, 'deleted': 0}
        assert index.client.count(settings.collection).count == 205
        assert [len(page) for page in repo.lookups] == [100, 100, 5]
        assert cleanup_vectors(repo, index, apply=True) == {'scanned': 205, 'orphaned': 202, 'deleted': 202}
        assert set(index.point_ids()[0]) == repo.referenced
        assert cleanup_vectors(repo, index, apply=True) == {'scanned': 3, 'orphaned': 0, 'deleted': 0}
    finally:
        index.close()


def test_cleanup_restores_search_past_stale_qdrant_matches(tmp_path):
    settings = Settings(database_url='postgresql://unused', api_key='fixture-key', media_root=tmp_path)
    index = VectorIndex(settings, QdrantClient(':memory:'))
    index.initialize()
    stale = [str(uuid4()) for _ in range(12)]
    active = str(uuid4())
    payload = {'embedding_identity': embedding_identity(settings)}
    points = [models.PointStruct(id=value, vector=VECTOR, payload=payload) for value in stale]
    points.append(models.PointStruct(id=active, vector=[0.9, 0.1] + [0.0] * 766, payload=payload))
    index.client.upsert(settings.collection, points=points, wait=True)
    class Repository(MaintenanceRepository, SearchRepository):
        def __init__(self):
            MaintenanceRepository.__init__(self, [active])
            SearchRepository.__init__(self, [active])
    repo = Repository()
    with TestClient(create_app(settings, repo, index, FixtureEmbedding())) as client:
        request = {'json': {'query': 'deer', 'top_k': 1}, 'headers': AUTH}
        assert client.post('/api/v1/search', **request).status_code == 503
        assert cleanup_vectors(repo, index, apply=True)['deleted'] == len(stale)
        response = client.post('/api/v1/search', **request)
        assert response.status_code == 200
        assert response.json()['results'][0]['source'] == 'media://' + active


def test_cleanup_stops_before_deletion_if_lock_session_is_lost():
    repo = MaintenanceRepository([])
    class Index:
        def point_ids(self, offset):
            return [str(uuid4())], None

        def delete(self, ids):
            pytest.fail('Deletion after lock loss')
    def lose_session(ids):
        repo.connection_alive = False
        return set()
    repo.referenced_index_ids = lose_session
    with pytest.raises(RuntimeError, match='connection lost'):
        cleanup_vectors(repo, Index(), apply=True)


def test_cleanup_requires_exclusive_worker_lock():
    repo = MaintenanceRepository([])
    with repo.worker_lock(), pytest.raises(ValueError, match='Another archive worker'):
        cleanup_vectors(repo, object(), apply=True)


def test_cleanup_does_not_delete_when_reference_lookup_fails():
    repo = MaintenanceRepository([])
    class Index:
        def point_ids(self, offset):
            return [str(uuid4())], None

        def delete(self, ids):
            pytest.fail('Deletion without authoritative references')
    def unavailable(ids):
        raise RuntimeError('Database unavailable')
    repo.referenced_index_ids = unavailable
    with pytest.raises(RuntimeError, match='Database unavailable'):
        cleanup_vectors(repo, Index(), apply=True)


@pytest.mark.parametrize('failure', [None, 'upsert', 'publication', 'cleanup'])
def test_replacement_cleanup_never_precedes_publication(tmp_path, monkeypatch, caplog, failure):
    # Reuse a fixture media path. Decoding is covered by the FFmpeg integration
    # suite; this test exercises publication/cleanup failure ordering only.
    path = tmp_path / 'fixture.mp4'
    path.write_bytes(b'fixture')
    monkeypatch.setattr(ingest, 'validate_video', lambda target: None)
    settings = Settings(media_root=tmp_path)
    old_id = uuid4()
    events = []
    class Repository:
        def assert_worker(self):
            pass

        def video(self, identifier):
            return {'storage_key': path.name}

        def segment(self, identifier):
            return {'storage_key': path.name, 'caption': 'Existing exact caption', 'index_id': old_id}

        def save_segment(self, row):
            assert row['index_id'] != old_id
            assert row['caption'] == 'Existing exact caption'
            events.append('saved')

        def mark_indexed(self, identifier):
            if failure == 'publication':
                raise RuntimeError('publication')
            events.append('published')

    class Index:
        def upsert(self, row, vector):
            if failure == 'upsert':
                raise RuntimeError('upsert')
            events.append('upserted')

        def delete(self, ids):
            assert ids == [old_id]
            assert events[-1] == 'published'
            if failure == 'cleanup':
                raise RuntimeError('private-cleanup-key')
            events.append('deleted')

    job = {'id': uuid4(), 'video_id': uuid4(), 'settings': {
        'embedding_identity': embedding_identity(settings), 'captions': ['Unused imported caption'],
        'duration': 1, 'segment_seconds': 1, 'dataset_id': 'fixture', 'tags': []}}
    embedder = SimpleNamespace(encode=lambda caption: VECTOR)
    if failure in {'upsert', 'publication'}:
        with pytest.raises(RuntimeError, match=failure):
            ingest.process_job(job, Repository(), MediaStore(tmp_path), Index(), embedder, None, settings)
        assert 'deleted' not in events
    else:
        ingest.process_job(job, Repository(), MediaStore(tmp_path), Index(), embedder, None, settings)
        assert events[:3] == ['saved', 'upserted', 'published']
        assert ('deleted' in events) == (failure is None)
    if failure == 'cleanup':
        assert 'cleanup deferred' in caplog.text
        assert 'private-cleanup-key' not in caplog.text
