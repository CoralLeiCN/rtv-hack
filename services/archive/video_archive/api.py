from contextlib import asynccontextmanager
import hmac
import logging
import threading

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import Settings
from .index import VectorIndex
from .media import MediaStore, media_id
from .models import Embedder, embedding_identity
from .repository import Repository

for name in ('httpx', 'httpcore'):
    logging.getLogger(name).setLevel(logging.WARNING)


class Search(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=32)
    top_k: int = Field(default=15, ge=1, le=100)

    @field_validator('query')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Blank query')
        return value.strip()

    @field_validator('tags')
    @classmethod
    def valid_tags(cls, value):
        if any(not v.strip() or len(v) > 100 for v in value):
            raise ValueError('Invalid tag')
        return value


def create_app(settings=None, repo=None, index=None, embedder=None, store=None):
    settings = settings or Settings.from_env()
    repo = repo or Repository(settings)
    # Lazy creation lets unconfigured liveness run without a DB or models.
    state = {'index': index, 'embedder': embedder}
    store = store or MediaStore(settings.media_root)
    service_lock = threading.Lock()

    def services():
        settings.validate()
        with service_lock:
            if state['index'] is None:
                state['index'] = VectorIndex(settings)
            if state['embedder'] is None:
                state['embedder'] = Embedder(settings)
            return state['index'], state['embedder']

    @asynccontextmanager
    async def lifespan(app):
        yield
        if state['index'] is not None:
            state['index'].close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    def authorize(request: Request):
        if not settings.api_key:
            raise HTTPException(503, 'Archive is not configured')
        expected = ('Bearer ' + settings.api_key).encode()
        if not hmac.compare_digest(request.headers.get('authorization', '').encode(), expected):
            raise HTTPException(401, 'Archive authentication required')

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({'detail': 'Invalid request'}, status_code=422)

    @app.exception_handler(Exception)
    async def unavailable(request, exc):
        return JSONResponse({'detail': 'Archive service is unavailable'}, status_code=503)

    @app.middleware('http')
    async def private(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/ready', dependencies=[Depends(authorize)])
    def ready():
        vector_index, _ = services()
        repo.ready()
        vector_index.ready()
        store.ready()
        return {'status': 'ready', 'model_loaded': state['embedder']._model is not None if isinstance(state['embedder'], Embedder) else True}

    @app.post('/api/v1/search', dependencies=[Depends(authorize)])
    def search(body: Search):
        vector_index, embedding = services()
        vector = embedding.encode(body.query, query=True)
        identity = embedding_identity(settings)
        results = []
        # Page past stale/unpublished index entries while bounding total work.
        for offset in range(0, 1000, 100):
            hits = vector_index.search(vector, body.tags, 100, identity, offset)
            records = repo.indexed([p.id for p in hits], body.tags, identity)
            for point in hits:
                row = records.get(str(point.id))
                if row is None:
                    continue
                results.append({'source': f"media://{row['id']}", 'original_video': f"media://{row['video_id']}",
                    'reasoning_content': row['caption'], 'segment_start_sec': row['start_sec'],
                    'segment_end_sec': row['end_sec'], 'similarity_score': point.score,
                    'dataset': row['dataset_id'], 'dataset_id': row['dataset_id']})
                if len(results) == body.top_k:
                    return {'results': results}
            if len(hits) < 100:
                break
        return {'results': results}

    @app.get('/api/v1/metadata', dependencies=[Depends(authorize)])
    def metadata():
        return repo.metadata()

    @app.api_route('/api/v1/videos/stream', methods=['GET', 'HEAD'], dependencies=[Depends(authorize)])
    def video(request: Request, source: str):
        try:
            identifier = media_id(source)
        except ValueError:
            raise HTTPException(404, 'Unknown media') from None
        row = repo.segment(identifier)
        if not row or not row['indexed']:
            raise HTTPException(404, 'Unknown media')
        return store.response(row['storage_key'], request.method, request.headers.get('range'), request.headers.get('if-range'))

    return app


app = create_app()
