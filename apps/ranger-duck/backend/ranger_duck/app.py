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
from .vss import VSSClient, animal_search_scope
from .loop import LoopService, install_loop_routes
from .loop_agent import CYCLE_TIMEOUT, CodexAgent
from .encounter import EncounterService, PLAN_TIMEOUT, ENCOUNTER_TIMEOUT
from .capture import Capture, CapturedAgent
from .loop import StrictModel, Telemetry
from .loop_agent import Primitive

SCENARIOS = {
    "deer-feeding": {"id": "deer-feeding", "label": "Forage together", "animal": "deer", "behavior_hint": "feeding",
        "interaction": "co-feeding", "description": "A deer meets the duck, which copies one animal's role from deer–deer foraging footage.",
        "query": "Two deer interacting while grazing together side by side, one deer lowering its head to feed beside the other deer"},
    "deer-walking": {"id": "deer-walking", "label": "Follow companion", "animal": "deer", "behavior_hint": "following",
        "interaction": "following a companion", "description": "A deer meets the duck, which copies the following animal from deer–deer footage.",
        "query": "Two deer interacting, one deer walking behind and following another deer"},
    "deer-standing": {"id": "deer-standing", "label": "Herd alert", "animal": "deer", "behavior_hint": "alert",
        "interaction": "shared alert pause", "description": "A deer meets the duck, which copies an alert response from deer–deer footage.",
        "query": "Two deer interacting, both deer stop together and stand still alert beside each other"},
    "cat-hissing": {"id": "cat-hissing", "label": "Hissing", "animal": "cat", "behavior_hint": "hissing",
        "interaction": "directed hiss and boundary response", "description": "A cat meets the duck, which copies a supported response from cat–cat footage.",
        "query": "Two domestic cats interacting, one cat hissing at another cat and the other cat backing away"},
    "cat-greeting": {"id": "cat-greeting", "label": "Greeting", "animal": "cat", "behavior_hint": "greeting",
        "interaction": "social approach and greeting", "description": "A cat meets the duck, which copies one animal's greeting from cat–cat footage.",
        "query": "Two domestic cats interacting, one cat approaching another cat and sniffing the other cat in a greeting"},
    "cat-play": {"id": "cat-play", "label": "Social play", "animal": "cat", "behavior_hint": "play",
        "interaction": "play with a companion", "description": "A cat meets the duck, which copies one animal's play movement from cat–cat footage.",
        "query": "Two domestic cats interacting and playing with each other, one cat playfully following or chasing the other cat"},
}
for scenario in SCENARIOS.values():
    scenario.update(interaction_partner=scenario["animal"], role="focal_animal", input_mode="scripted_scene",
                    broader_query=f"Two {('cats' if scenario['animal'] == 'cat' else 'deer')} interacting with each other")


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    encounter_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    scenario_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    mode: Literal["live", "replay"] = "live"
    broaden: bool = False
    plan_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    encounter_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    scenario_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    broaden: bool = False


class ActionCapture(StrictModel):
    clip_id: str = Field(min_length=1, max_length=100)
    search_id: str = Field(min_length=1, max_length=100)
    execution_id: str = Field(min_length=1, max_length=150)
    cycle: int = Field(ge=1)
    primitive: Primitive
    status: Literal['started', 'completed', 'failed', 'cancelled']
    state: Telemetry | None = None


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
               manifest: Manifest | None = None, loop_agent=None) -> FastAPI:
    settings = settings or Settings.from_env()
    manifest = manifest if manifest is not None else Manifest.load(settings.manifest_path)
    registry = ClipRegistry(settings.clip_ttl_sec, settings.max_sessions)
    capture = Capture(settings.capture_dir, (settings.password, settings.username))
    client = VSSClient(settings, transport, capture)
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
        await encounter_service.close()
        await loop_service.close()
        await client.close()

    app = FastAPI(title="Ranger Duck backend", version="1", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.registry = registry
    app.state.vss = client
    app.state.capture = capture
    agent = CapturedAgent(loop_agent if loop_agent is not None else CodexAgent(capture), capture)
    loop_service = LoopService(registry, client, manifest, public_text, agent, capture)
    encounter_service = EncounterService(registry, manifest, public_text, agent, capture)
    app.state.loop_service = loop_service
    app.state.encounter_service = encounter_service
    install_loop_routes(app, loop_service)

    @app.exception_handler(DemoError)
    async def demo_error_handler(_: Request, error: DemoError):
        return JSONResponse(error.body(), status_code=error.status, headers={"Cache-Control": "no-store"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request_handler(_: Request, error: RequestValidationError):
        # Never echo request bodies or Pydantic inputs into public errors.
        return JSONResponse(DemoError("invalid_request", "Provide valid fields for this request.", 422).body(), status_code=422)

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
                "reviewed_reference_count": len(manifest.entries),
                "search_timeout_ms": round(settings.search_timeout_sec * 1000),
                "loop_agent_available": loop_service.agent.available,
                "loop_cycle_timeout_ms": CYCLE_TIMEOUT * 1000,
                "encounter_agent_available": agent.available,
                "capture_enabled": capture.directory is not None, "capture_write_failed": capture.failed,
                "encounter_plan_timeout_ms": PLAN_TIMEOUT * 1000,
                "encounter_timeout_ms": ENCOUNTER_TIMEOUT * 1000})
        establish_cookie(response, registry.session(request.cookies.get(COOKIE_NAME)))
        return response

    @app.get("/demo-api/encounters")
    async def encounters():
        return {"encounters": list(SCENARIOS.values())}

    @app.post("/demo-api/encounter-plan")
    async def plan_encounter(payload: PlanRequest, request: Request):
        scenario = SCENARIOS.get(payload.scenario_id)
        if scenario is None:
            raise DemoError("unknown_scenario", "Choose an encounter from the scenario catalog.", 404)
        client._require_config()
        owner = encounter_service.owner(request)
        plan = await encounter_service.run(owner, payload.encounter_id,
            lambda: encounter_service.plan(owner, payload.encounter_id, scenario, payload.broaden), request, PLAN_TIMEOUT)
        response = JSONResponse({"encounter_id": payload.encounter_id, "plan_id": plan.id,
                                 "query": plan.query, "query_reason": plan.reason, "query_basis": "agent",
                                 "search_scope": animal_search_scope(scenario["animal"])})
        establish_cookie(response, owner)
        return response

    @app.post("/demo-api/encounters/{encounter_id}/cancel")
    async def cancel_encounter(encounter_id: str, request: Request):
        owner = request.cookies.get(COOKIE_NAME)
        if owner in registry.sessions:
            encounter_service.cancel(owner, encounter_id)
        return {"status": "cancelled", "encounter_id": encounter_id}

    @app.post("/demo-api/search")
    async def search(payload: SearchRequest, request: Request):
        scenario = SCENARIOS.get(payload.scenario_id)
        if scenario is None:
            raise DemoError("unknown_scenario", "Choose an encounter from the scenario catalog.", 404)
        started = time.monotonic()
        key = (payload.scenario_id, payload.broaden)
        if payload.mode == "replay":
            snapshot = registry.replay(request.cookies.get(COOKIE_NAME), key)
            session_id = registry.session(request.cookies.get(COOKIE_NAME))
        else:
            client._require_config()
            session_id = encounter_service.owner(request)
            async def live_search():
                if payload.plan_id:
                    plan = encounter_service.planned(session_id, payload.plan_id, payload.encounter_id, payload.scenario_id, payload.broaden)
                else:
                    plan = await encounter_service.plan(session_id, payload.encounter_id, scenario, payload.broaden)
                scope = animal_search_scope(scenario["animal"])
                result = await client.search(plan.query, tags=scope["tags"])
                segments = tuple(normalize_segments(result["results"]))
                annotations, summary = await encounter_service.actions(segments, scenario, plan.query)
                return SearchSnapshot(query=plan.query, segments=segments,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                    recorded_at=datetime.now(timezone.utc).isoformat(), started=started,
                    expires=time.monotonic() + settings.clip_ttl_sec, annotations=annotations,
                    query_reason=plan.reason, agent_summary=summary, search_scope=scope)
            snapshot = await encounter_service.run(session_id, payload.encounter_id, live_search, request, ENCOUNTER_TIMEOUT)
        if payload.mode == "live":
            registry.remember(session_id, key, snapshot)
        candidates = []
        for segment, recorded_annotation in zip(snapshot.segments, snapshot.annotations):
            annotation = dict(recorded_annotation)
            reference = annotation.pop("_reference", None)
            clip_id = registry.add(session_id, segment.source)
            source_label = (reference or {}).get("source_label") or f"Reference clip {segment.rank:02d}"
            dataset = (reference or {}).get("dataset") or segment.dataset
            candidates.append({"clip_id": clip_id, "rank": segment.rank, "video_url": f"/demo-api/clips/{clip_id}/video",
                "caption": public_text(segment.caption), "similarity": segment.similarity,
                "caption_hash": "sha256:" + caption_hash(segment.caption),
                "review_reason": public_text((reference or {}).get("review_note"), 1000) or None,
                **annotation,
                "provenance": {"dataset": public_text(dataset, 100) or None,
                    "dataset_id": public_text(segment.dataset_id, 100) or None,
                    "source_label": public_text(source_label, 150), "parent_id": opaque_parent(segment.parent),
                    "segment_start_sec": segment.start, "segment_end_sec": segment.end}})
        search_id = secrets.token_urlsafe(24)
        run_id = capture.run_id(session_id, 'encounter:' + payload.encounter_id)
        for candidate in candidates:
            if candidate['action']:
                registry.sessions[session_id].actions[candidate['clip_id']] = {
                    'search_id': search_id, 'run_id': run_id, 'action': candidate['action']}
        body = {"encounter_id": payload.encounter_id,
            "search_id": search_id, "mode": payload.mode,
            "match_type": "broader_behavior" if payload.broaden else "species_interaction",
            "status": "ok" if any(c["action"] for c in candidates) else "no_supported_imitation" if candidates else "no_results",
            "query": snapshot.query, "elapsed_ms": round((time.monotonic() - started) * 1000),
            "query_basis": "agent", "query_reason": snapshot.query_reason,
            "search_scope": snapshot.search_scope,
            "action_planner": "agent", "agent_plan": {"summary": snapshot.agent_summary},
            "original_elapsed_ms": snapshot.elapsed_ms, "recorded_at": snapshot.recorded_at,
            "candidates": candidates,
            "warnings": ([manifest.warning] if manifest.warning else []) +
                (["Agent-planned actions marked video_caption use exact excerpts from existing video-model captions, not a visual review. Interaction or similar individual behavior can supply evidence; the requested encounter never supplies a missing motion."]
                 if any(c["action_basis"] == "video_caption" for c in candidates) else []) +
                (["Replaying a previous live search. Video playback still requires VSS access."] if payload.mode == "replay" else [])}
        capture.emit('encounter.result', payload.model_dump(), body, run_id=run_id)
        response = JSONResponse(body)
        establish_cookie(response, session_id)
        return response

    @app.post('/demo-api/action-outcome')
    async def action_outcome(payload: ActionCapture, request: Request):
        owner = request.cookies.get(COOKIE_NAME)
        registry.resolve(owner, payload.clip_id)
        issued = registry.sessions[owner].actions.get(payload.clip_id)
        if not issued or issued['search_id'] != payload.search_id or issued['action']['primitive'] != payload.primitive:
            raise DemoError('invalid_outcome', 'The outcome must match an issued action.', 409)
        if payload.status == 'completed' and (payload.state is None or payload.state.status != 'complete'):
            raise DemoError('invalid_outcome', 'Completion requires completed simulator state.', 422)
        capture.emit('encounter.action.' + payload.status, issued['action'], payload.model_dump(),
                     run_id=issued['run_id'], outcome_source='browser_report')
        return {'status': 'recorded' if capture.directory and not capture.failed else 'capture_unavailable'}

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
