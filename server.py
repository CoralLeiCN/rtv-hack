"""Simple search UI backed by the independent video archive."""
from collections import OrderedDict
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ranger_duck.archive import ArchiveClient
from ranger_duck.config import Settings
from ranger_duck.errors import DemoError
from ranger_duck.stream import close_stream

WEB_ROOT = Path(__file__).resolve().parent / 'web'
REQUEST_TIMEOUT_SECONDS = 55.0
MAX_PLAYBACK_SOURCES = 1024
MAX_SOURCE_LENGTH = 4096


class VideoStreamResponse(StreamingResponse):
    def __init__(self, upstream, headers):
        self.upstream = upstream
        super().__init__(self.chunks(), status_code=upstream.status_code, headers=headers)

    async def chunks(self):
        try:
            async for chunk in self.upstream.aiter_raw():
                yield chunk
        except httpx.HTTPError:
            raise RuntimeError('The video stream was interrupted.') from None

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await close_stream(self.upstream)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=2000)

    @field_validator('query')
    @classmethod
    def nonblank_query(cls, value):
        if not value.strip():
            raise ValueError('Query must not be blank')
        return value.strip()


def create_app(backend_url=None, transport=None, api_key=None):
    configured = Settings.from_env()
    settings = Settings(archive_url=backend_url if backend_url is not None else configured.archive_url,
                        api_key=api_key if api_key is not None else configured.api_key,
                        search_timeout_sec=REQUEST_TIMEOUT_SECONDS)
    client = ArchiveClient(settings, transport)

    @asynccontextmanager
    async def lifespan(app):
        app.state.playback_sources = OrderedDict()
        try:
            yield
        finally:
            await client.close()
            app.state.playback_sources.clear()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse({'detail': 'Invalid request.'}, status_code=422)

    @app.exception_handler(DemoError)
    async def failed_archive(request, error):
        return JSONResponse({'detail': error.message}, status_code=error.status)

    @app.post('/api/v1/search')
    async def search(body: SearchRequest, request: Request):
        data = await client.search(body.query, tags=[])
        sources = request.app.state.playback_sources
        for result in data['results']:
            source = result.get('source') if isinstance(result, dict) else None
            if isinstance(source, str) and source.strip() and len(source) <= MAX_SOURCE_LENGTH:
                sources[source] = None
                sources.move_to_end(source)
                while len(sources) > MAX_PLAYBACK_SOURCES:
                    sources.popitem(last=False)
        return {'results': data['results']}

    @app.api_route('/api/v1/videos/stream', methods=['GET', 'HEAD'])
    async def video(request: Request, source: str = Query(min_length=1, max_length=MAX_SOURCE_LENGTH)):
        if source not in request.app.state.playback_sources:
            raise HTTPException(403, 'Search again to load this video.')
        byte_range = request.headers.get('range')
        if byte_range and (len(byte_range) > 100 or not re.fullmatch(r'bytes=(?:\d+-\d*|-\d+)', byte_range)):
            raise HTTPException(416, 'Use a single byte range.')
        upstream = await client.video(source, request.method, byte_range, request.headers.get('if-range'))
        headers = {key: upstream.headers[key] for key in ('content-type', 'content-length', 'content-range', 'accept-ranges', 'etag') if key in upstream.headers}
        mime = headers.get('content-type', '').split(';')[0].lower()
        if upstream.status_code != 416 and not mime.startswith('video/'):
            await close_stream(upstream)
            raise HTTPException(502, 'The video service returned an invalid response.')
        if upstream.headers.get('content-encoding', 'identity') != 'identity':
            await close_stream(upstream)
            raise HTTPException(502, 'The video service returned an invalid response.')
        if request.method == 'HEAD' or upstream.status_code == 416:
            await close_stream(upstream)
            if upstream.status_code == 416:
                headers['content-length'] = '0'
            return Response(status_code=upstream.status_code, headers=headers)
        return VideoStreamResponse(upstream, headers)

    @app.get('/config.js')
    async def config():
        # Keep the established browser configuration name for the static UI.
        public = {'apiBaseUrl': '', 'resultTiming': {'startField': 'segment_start_sec', 'endField': 'segment_end_sec', 'unit': 'seconds'}}
        return Response('window.VSS_CONFIG = ' + json.dumps(public) + ';\n', media_type='text/javascript')

    app.mount('/', StaticFiles(directory=WEB_ROOT, html=True), name='frontend')
    return app


app = create_app()
