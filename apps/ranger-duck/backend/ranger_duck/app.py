"""Frontend-facing v1 API. VSS credentials and source URIs stay server-side."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import re
import secrets
import time
from urllib.parse import urlsplit
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .errors import DemoError, upstream_error
from .evidence import Manifest, caption_hash, normalize_segments, safe_text
from .session import COOKIE_NAME, ClipRegistry, SearchSnapshot
from .stream import close_stream
from .vss import VSSClient

SCENARIOS = {
    "deer-feeding": {"id": "deer-feeding", "label": "Feeding", "animal": "deer", "behavior_hint": "feeding",
        "description": "A deer lowers its head to feed in a clearing.", "input_mode": "scripted_scene",
        "query": "deer feeding with its head lowered"},
    "deer-walking": {"id": "deer-walking", "label": "Walking", "animal": "deer", "behavior_hint": "walking",
        "description": "A deer walks across a clearing.", "input_mode": "scripted_scene",
        "query": "deer walking across a clearing"},
    "deer-standing": {"id": "deer-standing", "label": "Standing", "animal": "deer", "behavior_hint": "standing",
        "description": "A deer stands still in a clearing.", "input_mode": "scripted_scene",
        "query": "deer standing still in a clearing"},
}


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    encounter_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    scenario_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    mode: Literal["live", "replay"] = "live"
    broaden: bool = False


class ProxyStreamingResponse(StreamingResponse):
    """Own the upstream connection even when sending fails before iteration."""
    def __init__(self, upstream: httpx.Response, content, **kwargs):
        super().__init__(content, **kwargs)
        self.upstream = upstream

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await close_stream(self.upstream)


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None,
               manifest: Manifest | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    manifest = manifest if manifest is not None else Manifest.load(settings.manifest_path)
    registry = ClipRegistry(settings.clip_ttl_sec, settings.max_sessions)
    client = VSSClient(settings, transport)
    opaque_key = secrets.token_bytes(32)

    def opaque_parent(source: str | None) -> str | None:
        return hmac.new(opaque_key, source.encode(), hashlib.sha256).hexdigest()[:32] if source else None

    def public_text(value: object, limit: int = 4000) -> str:
        result = safe_text(value, limit)
        for secret in (settings.ingress_url, settings.password, settings.username):
            if secret:
                result = result.replace(secret, "[redacted]")
        return result

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await client.close()

    app = FastAPI(title="Ranger Duck backend", version="1", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.registry = registry
    app.state.vss = client

    @app.exception_handler(DemoError)
    async def demo_error_handler(_: Request, error: DemoError):
        return JSONResponse(error.body(), status_code=error.status, headers={"Cache-Control": "no-store"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request_handler(_: Request, error: RequestValidationError):
        # Never echo request bodies or Pydantic inputs into public errors.
        return JSONResponse(DemoError("invalid_request", "Provide a valid encounter_id and scenario_id.", 422).body(), status_code=422)

    @app.middleware("http")
    async def private_api_responses(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/demo-api"):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def establish_cookie(response: Response, session_id: str) -> None:
        response.set_cookie(COOKIE_NAME, session_id, httponly=True, samesite="lax",
                            secure=settings.secure_cookie, max_age=settings.clip_ttl_sec, path="/demo-api")

    @app.get("/demo-api/health")
    async def health(request: Request):
        response = JSONResponse({"status": "ok", "api_version": "1", "live_configured": settings.configured,
                "reviewed_reference_count": len(manifest.entries)})
        establish_cookie(response, registry.session(request.cookies.get(COOKIE_NAME)))
        return response

    @app.get("/demo-api/encounters")
    async def encounters():
        return {"encounters": [{**scenario, "broader_query": scenario["query"].replace("deer", "hoofed animal", 1)}
                for scenario in SCENARIOS.values()]}

    @app.post("/demo-api/search")
    async def search(payload: SearchRequest, request: Request):
        scenario = SCENARIOS.get(payload.scenario_id)
        if scenario is None:
            raise DemoError("unknown_scenario", "Choose an encounter from the scenario catalog.", 404)
        started = time.monotonic()
        key = (payload.scenario_id, payload.broaden)
        query = scenario["query"].replace("deer", "hoofed animal", 1) if payload.broaden else scenario["query"]
        if payload.mode == "replay":
            snapshot = registry.replay(request.cookies.get(COOKIE_NAME), key)
        else:
            result = await client.search(query)
            snapshot = SearchSnapshot(query=query, segments=tuple(normalize_segments(result["results"])),
                elapsed_ms=round((time.monotonic() - started) * 1000),
                recorded_at=datetime.now(timezone.utc).isoformat(), started=started,
                expires=time.monotonic() + settings.clip_ttl_sec)
        session_id = registry.session(request.cookies.get(COOKIE_NAME))
        if payload.mode == "live":
            registry.remember(session_id, key, snapshot)
        candidates = []
        for index, segment in enumerate(snapshot.segments, start=1):
            annotation = manifest.annotate(segment, scenario["animal"])
            reference = annotation.pop("_reference", None)
            clip_id = registry.add(session_id, segment.source)
            source_label = (reference or {}).get("source_label") or f"Reference clip {index:02d}"
            dataset = (reference or {}).get("dataset") or segment.dataset
            candidates.append({"clip_id": clip_id, "video_url": f"/demo-api/clips/{clip_id}/video",
                "caption": public_text(segment.caption), "similarity": segment.similarity,
                "caption_hash": "sha256:" + caption_hash(segment.caption),
                "review_reason": public_text((reference or {}).get("review_note"), 1000) or None,
                **annotation,
                "provenance": {"dataset": public_text(dataset, 100) or None,
                    "source_label": public_text(source_label, 150), "parent_id": opaque_parent(segment.parent),
                    "segment_start_sec": segment.start, "segment_end_sec": segment.end}})
        response = JSONResponse({"encounter_id": payload.encounter_id,
            "search_id": secrets.token_urlsafe(24), "mode": payload.mode,
            "match_type": "broader_category" if payload.broaden else "species",
            "status": "ok" if any(c["action"] for c in candidates) else "no_supported_imitation" if candidates else "no_results",
            "query": snapshot.query, "elapsed_ms": round((time.monotonic() - started) * 1000),
            "original_elapsed_ms": snapshot.elapsed_ms, "recorded_at": snapshot.recorded_at,
            "candidates": candidates,
            "warnings": ([manifest.warning] if manifest.warning else []) +
                (["Replaying a previous live search. Video playback still requires VSS access."] if payload.mode == "replay" else [])})
        establish_cookie(response, session_id)
        return response

    @app.api_route("/demo-api/clips/{clip_id}/video", methods=["GET", "HEAD"])
    async def video(clip_id: str, request: Request):
        source = registry.resolve(request.cookies.get(COOKIE_NAME), clip_id)
        byte_range = request.headers.get("range")
        if byte_range and (len(byte_range) > 100 or not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", byte_range)):
            raise DemoError("invalid_range", "Use a single byte range for video playback.", 416)
        if_range = request.headers.get("if-range")
        if if_range and (len(if_range) > 512 or any(ord(c) < 32 for c in if_range)):
            raise DemoError("invalid_range", "The video range condition is invalid.", 416)
        upstream = await client.video(source, request.method, byte_range, if_range)
        headers = {}
        for name in ("Content-Length", "Content-Range", "Accept-Ranges"):
            value = upstream.headers.get(name)
            if value:
                patterns = {"Content-Length": r"\d+", "Content-Range": r"bytes (?:\d+-\d+/\d+|\*/\d+)", "Accept-Ranges": r"bytes|none"}
                if re.fullmatch(patterns[name], value):
                    headers[name] = value
        content_type = upstream.headers.get("content-type", "video/mp4").split(";")[0].strip().lower()
        # Reuse the simple search app's handling of storage's generic MIME types.
        if content_type in {"binary/octet-stream", "application/octet-stream"}:
            content_type = "video/mp4" if urlsplit(source).path.lower().endswith(".mp4") else "application/octet-stream"
        if upstream.status_code != 416 and not re.fullmatch(r"video/[a-zA-Z0-9.+-]+|application/octet-stream", content_type):
            await close_stream(upstream)
            raise upstream_error()
        if upstream.headers.get("content-encoding", "identity") != "identity":
            await close_stream(upstream)
            raise upstream_error()
        headers["Content-Type"] = content_type if upstream.status_code != 416 else "application/octet-stream"
        if request.method == "HEAD" or upstream.status_code == 416:
            await close_stream(upstream)
            if upstream.status_code == 416:
                headers["Content-Length"] = "0"
            return Response(status_code=upstream.status_code, headers=headers)

        async def body():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            except httpx.HTTPError:
                # After headers are sent, abort with a fixed message (never a JWT URL).
                raise RuntimeError("The video stream was interrupted.") from None

        return ProxyStreamingResponse(upstream, body(), status_code=upstream.status_code, headers=headers)

    @app.api_route("/demo-api/{unknown:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE"])
    async def unknown_api(unknown: str):
        raise DemoError("not_found", "This API route does not exist.", 404)

    if settings.static_dir and settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app


app = create_app()
