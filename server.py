"""Serve video search using the configured workshop account."""

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


WEB_ROOT = Path(__file__).resolve().parent / "web"
REQUEST_TIMEOUT_SECONDS = 55.0
MAX_PLAYBACK_SOURCES = 1024
MAX_SOURCE_LENGTH = 4096


async def close_stream(response):
    # Disconnects cancel the response task; closing the upstream must still run.
    with anyio.CancelScope(shield=True):
        try:
            await response.aclose()
        except httpx.HTTPError:
            pass


class VideoStreamResponse(StreamingResponse):
    def __init__(self, upstream, headers):
        self.upstream = upstream
        super().__init__(self.chunks(), status_code=upstream.status_code, headers=headers)

    async def chunks(self):
        try:
            async for chunk in self.upstream.aiter_raw():
                yield chunk
        except httpx.HTTPError:
            # HTTPX errors may contain the authenticated upstream URL.
            raise RuntimeError("The video stream was interrupted.") from None

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await close_stream(self.upstream)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Query must not be blank")
        return value


def create_app(backend_url=None, transport=None, username=None, password=None):
    base = (backend_url if backend_url is not None else os.environ.get("INGRESS_URL", "")).strip().rstrip("/")
    account = username if username is not None else os.environ.get("USERNAME", "")
    secret = password if password is not None else os.environ.get("PASSWORD", "")
    if base:
        parsed = urlsplit(base)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("INGRESS_URL must be an HTTP(S) base address without credentials, query, or fragment.")

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(55.0, connect=10.0),
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 VSS-Search-Frontend/1.0", "Accept": "application/json"},
            transport=transport,
        ) as client:
            app.state.upstream = client
            app.state.token = ""
            app.state.token_lock = asyncio.Lock()
            app.state.playback_sources = OrderedDict()
            try:
                yield
            finally:
                app.state.token = ""
                app.state.playback_sources.clear()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        # Never echo request input or upstream diagnostics in validation errors.
        return JSONResponse({"detail": "Invalid request."}, status_code=422)

    async def forward(request, path, payload, authorization=None):
        if not base:
            raise HTTPException(503, "The VSS backend is not configured.")
        headers = {"Authorization": authorization} if authorization else {}
        try:
            upstream_request = request.app.state.upstream.build_request(
                "POST",
                f"{base}/api/v1/{path}", json=payload, headers=headers,
            )
            # The VSS API uses per-request JWTs. Never forward pooled cookies.
            upstream_request.headers.pop("cookie", None)
            response = await request.app.state.upstream.send(upstream_request)
        except httpx.TimeoutException:
            raise HTTPException(504, "The VSS backend timed out.") from None
        except httpx.RequestError:
            raise HTTPException(502, "The VSS backend is unavailable.") from None
        if not response.is_success:
            status = response.status_code if response.status_code in (400, 401, 403, 422, 429) else 502
            raise HTTPException(status, "The VSS request failed.")
        try:
            return response.json()
        except ValueError:
            raise HTTPException(502, "The VSS backend returned an invalid response.") from None

    async def session_token(request, rejected_token=None):
        if not account or not secret:
            raise HTTPException(503, "The workshop account is not configured.")
        state = request.app.state
        async with state.token_lock:
            # Concurrent searches share a login; only refresh the rejected token.
            if state.token and state.token != rejected_token:
                return state.token
            state.token = ""
            try:
                data = await forward(request, "auth/login", {"username": account, "password": secret})
            except HTTPException as error:
                if error.status_code in (400, 401, 403, 422):
                    raise HTTPException(503, "The workshop account could not connect to VSS.") from None
                raise
            if not isinstance(data, dict) or not isinstance(data.get("access_token"), str) or not data["access_token"].strip():
                raise HTTPException(502, "The VSS backend returned an invalid session.")
            state.token = data["access_token"]
            return state.token

    async def search_results(body, request):
        token = await session_token(request)
        for attempt in range(2):
            try:
                data = await forward(request, "search", body.model_dump(), f"Bearer {token}")
                break
            except HTTPException as error:
                if error.status_code != 401:
                    raise
                if attempt:
                    if request.app.state.token == token:
                        request.app.state.token = ""
                    raise HTTPException(503, "The workshop account could not connect to VSS.") from None
                token = await session_token(request, rejected_token=token)
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise HTTPException(502, "The VSS backend returned invalid search results.")
        # The upstream stream endpoint accepts a source URI. Only allow sources
        # that this workshop account actually received from authenticated search.
        sources = request.app.state.playback_sources
        for result in data["results"]:
            source = result.get("source") if isinstance(result, dict) else None
            if isinstance(source, str) and source.strip() and len(source) <= MAX_SOURCE_LENGTH:
                sources[source] = None
                sources.move_to_end(source)
                while len(sources) > MAX_PLAYBACK_SOURCES:
                    sources.popitem(last=False)
        # Only segment results are needed by this UI; retain their order and fields.
        return {"results": data["results"]}

    @app.post("/api/v1/search")
    async def search(body: SearchRequest, request: Request):
        try:
            # Include authentication and one refresh in the browser's 60s budget.
            return await asyncio.wait_for(search_results(body, request), REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise HTTPException(504, "The VSS backend timed out.") from None

    async def open_video(request, source):
        token = await session_token(request)
        for attempt in range(2):
            headers = {"Accept": "video/*, application/octet-stream", "Accept-Encoding": "identity"}
            if "range" in request.headers:
                headers["Range"] = request.headers["range"]
            upstream_request = request.app.state.upstream.build_request(
                "GET", f"{base}/api/v1/videos/stream",
                params={"source": source, "token": token}, headers=headers,
            )
            upstream_request.headers.pop("cookie", None)
            try:
                upstream = await request.app.state.upstream.send(upstream_request, stream=True)
            except httpx.TimeoutException:
                raise HTTPException(504, "The video service timed out.") from None
            except httpx.RequestError:
                raise HTTPException(502, "The video service is unavailable.") from None

            handed_off = False
            try:
                if upstream.status_code == 401:
                    if attempt:
                        if request.app.state.token == token:
                            request.app.state.token = ""
                        raise HTTPException(503, "The workshop account could not connect to VSS.")
                elif upstream.status_code == 416:
                    return Response(status_code=416, headers={
                        key: upstream.headers[key] for key in ("content-range", "accept-ranges") if key in upstream.headers
                    })
                elif upstream.status_code not in (200, 206):
                    status = upstream.status_code if upstream.status_code in (400, 403, 404, 429) else 502
                    raise HTTPException(status, "The video could not be loaded.")
                else:
                    content_type = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    binary = content_type in ("application/octet-stream", "binary/octet-stream")
                    if not content_type.startswith("video/") and not binary:
                        raise HTTPException(502, "The video service returned an invalid response.")
                    media_headers = {
                        key: upstream.headers[key]
                        for key in ("content-type", "content-length", "content-range", "accept-ranges")
                        if key in upstream.headers
                    }
                    # VSS storage sometimes labels MP4 clips as generic binary.
                    if binary and urlsplit(source).path.lower().endswith(".mp4"):
                        media_headers["content-type"] = "video/mp4"
                    response = VideoStreamResponse(upstream, media_headers)
                    handed_off = True
                    return response
            finally:
                if not handed_off:
                    await close_stream(upstream)
            token = await session_token(request, rejected_token=token)

    @app.get("/api/v1/videos/stream")
    async def video(request: Request, source: str = Query(min_length=1, max_length=MAX_SOURCE_LENGTH)):
        if not source.strip():
            raise HTTPException(422, "Invalid request.")
        if source not in request.app.state.playback_sources:
            raise HTTPException(403, "Search again to load this video.")
        try:
            # Bound authentication and response headers, not the clip's duration.
            return await asyncio.wait_for(open_video(request, source), REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise HTTPException(504, "The video service timed out.") from None

    @app.get("/config.js")
    async def config():
        public = {
            "apiBaseUrl": "",
            "resultTiming": {
                "startField": os.environ.get("VSS_RESULT_START_FIELD", "segment_start_sec"),
                "endField": os.environ.get("VSS_RESULT_END_FIELD", "segment_end_sec"),
                "unit": os.environ.get("VSS_RESULT_TIME_UNIT", "seconds"),
            },
        }
        return Response("window.VSS_CONFIG = " + json.dumps(public) + ";\n", media_type="text/javascript")

    app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="frontend")
    return app


app = create_app()
