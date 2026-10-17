"""Contract and boundary tests use fabricated non-live fixtures only."""
import asyncio
from dataclasses import replace
import json
import time

from fastapi.testclient import TestClient
import httpx
import pytest

from ranger_duck.app import create_app
from ranger_duck.config import Settings
from ranger_duck.evidence import Manifest, Segment
from ranger_duck.session import COOKIE_NAME
from ranger_duck.encounter_agent import EncounterQueryDecision, EncounterActionsDecision

SETTINGS = Settings(ingress_url="https://vss.invalid", username="test-user", password="test-secret")
ROW = {"source": "s3://test-segments/clip.mp4", "original_video": "s3://test-parents/animal.mp4",
       "reasoning_content": "A deer lowers its head to feed.", "segment_start_sec": 0,
       "segment_end_sec": 5, "similarity_score": 0.8}
PAYLOAD = {"encounter_id": "encounter-01", "scenario_id": "deer-feeding"}


def reviewed(row=None, **overrides):
    item = Segment.parse(row or ROW).review_draft()
    item.update(reviewed=True, evidence_id="ref-01", animal="deer", behavior="feeding", source_label="Test reference")
    item.update(overrides)
    return item


class VideoBytes(httpx.AsyncByteStream):
    def __init__(self, content=b"abcdef"):
        self.content, self.closed, self.read = content, False, False

    async def __aiter__(self):
        self.read = True
        yield self.content

    async def aclose(self):
        self.closed = True


class Upstream:
    def __init__(self, results=None):
        self.results = [dict(ROW)] if results is None else results
        self.requests = []
        self.logins = 0
        self.fail_search_once = False
        self.search_status = 200
        self.search_timeout = False
        self.search_delay = 0
        self.video_status = 200
        self.video_headers = {"content-type": "video/mp4", "content-length": "6", "accept-ranges": "bytes"}
        self.video_fail_once = False
        self.head_405 = False
        self.streams = []

    async def __call__(self, request):
        self.requests.append(request)
        if request.url.path.endswith("/auth/login"):
            self.logins += 1
            return httpx.Response(200, json={"access_token": f"test-token-{self.logins}"})
        if request.url.path.endswith("/auth/me"):
            return httpx.Response(200, json={"username": "test-user"})
        if request.url.path.endswith("/search"):
            if self.search_delay:
                await asyncio.sleep(self.search_delay)
            if self.search_timeout:
                raise httpx.ReadTimeout("do not expose test-secret or test-token", request=request)
            if self.fail_search_once:
                self.fail_search_once = False
                return httpx.Response(401, json={"detail": "test-secret"})
            return httpx.Response(self.search_status, json={"results": self.results,
                "sql_query": "private SQL", "vectors": [0.1], "debug": "test-secret"})
        if request.url.path.endswith("/videos/stream"):
            if self.video_fail_once:
                self.video_fail_once = False
                return httpx.Response(401)
            if request.method == "HEAD" and self.head_405:
                return httpx.Response(405)
            stream = VideoBytes()
            self.streams.append(stream)
            return httpx.Response(self.video_status, headers=self.video_headers, stream=stream)
        raise AssertionError("Unexpected upstream path")


class EncounterAgent:
    available = True

    def __init__(self):
        self.calls = []

    async def decide(self, context, schema):
        self.calls.append(json.loads(json.dumps(context)))
        if schema is EncounterQueryDecision:
            animal = context['animal']
            query = (f"{'Cats' if animal == 'cat' else 'Deer'} interacting" if context['broaden'] else
                     f"{animal.capitalize()} {context['encounter']['behavior_hint']}, interacting with another {animal}")
            return EncounterQueryDecision(query=query, individual_query=f"A {animal} alone showing similar observable motion",
                                          reason='Search the chosen encounter and similar observable individual motion.')
        return EncounterActionsDecision(summary='Use the active observed behaviors, skipping unsupported clips.', actions=[{
            'candidate_id': c['candidate_id'], 'decision': 'imitate' if c['allowed_actions'] else 'skip',
            'primitive': c['preferred_action'], 'evidence_excerpt': c['caption'] if c['allowed_actions'] else '',
            'reason': 'Approximate the supported behavior in this exact caption.' if c['allowed_actions'] else 'No supported behavior.'
        } for c in context['candidates']])


def make_client(upstream=None, manifest=None, settings=SETTINGS, agent=None):
    upstream = upstream or Upstream()
    app = create_app(settings, httpx.MockTransport(upstream), Manifest(manifest), agent or EncounterAgent())
    return TestClient(app), upstream, app


def search(client):
    response = client.post("/demo-api/search", json=PAYLOAD)
    assert response.status_code == 200, response.text
    return response.json()


def test_no_configuration_is_runnable_and_reports_it():
    client, upstream, _ = make_client(settings=Settings())
    with client:
        health = client.get("/demo-api/health").json()
        assert {key: health[key] for key in ("status", "api_version", "live_configured", "reviewed_reference_count", "search_timeout_ms")} == {"status": "ok", "api_version": "1", "live_configured": False, "reviewed_reference_count": 0, "search_timeout_ms": 30000}
        assert health["loop_cycle_timeout_ms"] == 180000
        assert isinstance(health["loop_agent_available"], bool)
        scenarios = client.get("/demo-api/encounters").json()["encounters"]
        assert len(scenarios) == 6 and all("action" not in s for s in scenarios)
        assert all(s["animal"] == s["interaction_partner"] for s in scenarios)
        response = client.post("/demo-api/search", json=PAYLOAD)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "live_not_configured"
        assert upstream.requests == []


def test_unreviewed_solitary_behavior_is_actionable_without_private_fields():
    client, upstream, _ = make_client()
    with client:
        result = search(client)
        assert result["encounter_id"] == PAYLOAD["encounter_id"]
        assert result["mode"] == "live" and result["status"] == "ok"
        item = result["candidates"][0]
        assert item["action"]["primitive"] == "ground_pick" and item["review_status"] == "unreviewed"
        assert item["action_basis"] == "video_caption" and item["eligibility_reason"] == "caption_behavior_match"
        assert item["animal"] == "deer" and item["interaction_partner"] is None
        assert item["provenance"]["segment_start_sec"] == 0
        assert item["provenance"]["dataset"] is None
        rendered = json.dumps(result)
        for forbidden in ("s3://", "sql_query", "private SQL", "test-secret", "test-token", "test-user", "vectors"):
            assert forbidden not in rendered
        sent = json.loads(next(r.content for r in upstream.requests if r.url.path.endswith("/search")))
        assert sent["llm_top_n"] == 1 and sent["tags"] == ["wildlife"]
        assert "metadata_filters" not in sent
        cookie = client.cookies.get(COOKIE_NAME)
        assert cookie


def test_current_review_controls_action_instead_of_scenario():
    row = {**ROW, "reasoning_content": "Two deer interact. One deer follows another deer."}
    client, _, _ = make_client(Upstream([row]), manifest=[reviewed(row, behavior="walking",
        interaction_partner="deer", interaction_evidence=row["reasoning_content"])])
    with client:
        result = search(client)
        assert result["status"] == "ok"
        assert result["candidates"][0]["action"] == {"primitive": "short_walk", "evidence_id": "ref-01", "max_duration_ms": 2000}
        assert result["candidates"][0]["action_basis"] == "reviewed"


def test_explicit_replay_uses_only_this_sessions_matching_live_search():
    client, upstream, app = make_client(manifest=[reviewed()])
    with client:
        missing = client.post("/demo-api/search", json={**PAYLOAD, "mode": "replay"})
        assert missing.status_code == 409 and not upstream.requests
        live = search(client)
        before = len(upstream.requests)
        replay = client.post("/demo-api/search", json={**PAYLOAD, "encounter_id": "encounter-02", "mode": "replay"}).json()
        assert len(upstream.requests) == before
        assert replay["mode"] == "replay" and replay["encounter_id"] == "encounter-02"
        assert replay["recorded_at"] == live["recorded_at"]
        assert replay["original_elapsed_ms"] == live["original_elapsed_ms"]
        assert replay["candidates"][0]["action"] == live["candidates"][0]["action"]
        assert replay["candidates"][0]["clip_id"] != live["candidates"][0]["clip_id"]
        assert client.get(replay["candidates"][0]["video_url"]).status_code == 200
        assert client.post("/demo-api/search", json={**PAYLOAD, "mode": "replay", "broaden": True}).status_code == 409
        assert client.post("/demo-api/search", json={**PAYLOAD, "mode": "replay", "scenario_id": "deer-walking"}).status_code == 409
        cookie = client.cookies.get(COOKIE_NAME)
        client.cookies.clear()
        assert client.post("/demo-api/search", json={**PAYLOAD, "mode": "replay"}).status_code == 409
        client.cookies.set(COOKIE_NAME, cookie)
        app.state.registry.sessions[cookie].searches[(PAYLOAD["scenario_id"], False)].expires = time.monotonic() - 1
        assert client.post("/demo-api/search", json={**PAYLOAD, "mode": "replay"}).status_code == 409


def test_failed_live_search_never_falls_back_to_existing_replay():
    client, upstream, _ = make_client()
    with client:
        search(client)
        upstream.search_timeout = True
        failed = client.post("/demo-api/search", json=PAYLOAD)
        assert failed.status_code == 504 and "candidates" not in failed.json()
        explicit = client.post("/demo-api/search", json={**PAYLOAD, "mode": "replay"})
        assert explicit.status_code == 200 and explicit.json()["mode"] == "replay"


def test_broader_search_changes_query_without_relaxing_review_or_species_rules():
    client, upstream, _ = make_client(manifest=[reviewed(animal="goat")])
    with client:
        response = client.post("/demo-api/search", json={**PAYLOAD, "broaden": True})
        result = response.json()
        sent = json.loads(next(r.content for r in upstream.requests if r.url.path.endswith("/search")))
        assert sent["query"] == result["query"] == "Deer interacting OR A deer alone showing similar observable motion"
        assert result["match_type"] == "broader_behavior"
        assert result["candidates"][0]["action"] is None
        assert result["candidates"][0]["eligibility_reason"] == "species_mismatch"


def test_evidence_details_include_exact_caption_hash_and_redacted_review_reason():
    from ranger_duck.evidence import caption_hash
    client, _, _ = make_client(manifest=[reviewed(review_note="Head is lowered. s3://private/key test-secret")])
    with client:
        item = search(client)["candidates"][0]
        assert item["caption_hash"] == "sha256:" + caption_hash(ROW["reasoning_content"])
        assert item["review_reason"].startswith("Head is lowered.")
        assert "s3://" not in item["review_reason"] and "test-secret" not in item["review_reason"]


def test_older_live_request_does_not_overwrite_newer_replay_snapshot():
    from ranger_duck.session import ClipRegistry, SearchSnapshot
    registry = ClipRegistry(60, 2)
    session = registry.session(None)
    key = ("deer-feeding", False)
    newer = SearchSnapshot("new", (), 10, "new", 20, time.monotonic() + 60)
    older = SearchSnapshot("old", (), 10, "old", 10, time.monotonic() + 60)
    registry.remember(session, key, newer)
    registry.remember(session, key, older)
    assert registry.replay(session, key) is newer


@pytest.mark.parametrize("change,reason,status", [
    ({"reasoning_content": "The caption was replaced."}, "reference_changed", "stale"),
    ({"source": "s3://test-segments/reingested.mp4"}, "reference_changed", "stale"),
    ({"segment_end_sec": 10}, "reference_changed", "stale"),
    ({"original_video": "s3://test-parents/other.mp4"}, "reference_changed", "stale"),
    ({"segment_start_sec": None}, "incomplete_metadata", "unreviewed"),
])
def test_stale_or_incomplete_returned_evidence_never_enables_action(change, reason, status):
    client, _, _ = make_client(Upstream([{**ROW, **change}]), [reviewed()])
    with client:
        item = search(client)["candidates"][0]
        assert item["action"] is None
        assert item["eligibility_reason"] == reason and item["review_status"] == status


@pytest.mark.parametrize("changes,reason", [({"animal": "elephant"}, "species_mismatch"),
    ({"behavior": "jumping"}, "unsupported_behavior"), ({"behavior": "resting"}, "unsupported_behavior"),
    ({"behavior": "looking_around"}, "unsupported_behavior")])
def test_reviewed_species_and_supported_behavior_required(changes, reason):
    client, _, _ = make_client(manifest=[reviewed(**changes)])
    with client:
        item = search(client)["candidates"][0]
        assert item["action"] is None and item["eligibility_reason"] == reason


def test_review_cannot_add_absent_evidence_and_duplicates_are_ambiguous():
    client, _, _ = make_client(Upstream([]), [reviewed()])
    with client:
        result = search(client)
        assert result["status"] == "no_results" and result["candidates"] == []
    client, _, _ = make_client(manifest=[reviewed(), reviewed(evidence_id="ref-02")])
    with client:
        assert search(client)["candidates"][0]["action"] is None


def test_normalization_deduplicates_without_changing_upstream_rank_or_parent_order():
    second = {**ROW, "source": "s3://test-segments/clip2.mp4", "segment_start_sec": 5, "segment_end_sec": 10}
    other = {**ROW, "source": "s3://test-segments/other.mp4", "original_video": "s3://test-parents/other.mp4"}
    client, _, _ = make_client(Upstream([ROW, ROW, second, other, {"source": "https://arbitrary.invalid"}]), [reviewed(second)])
    with client:
        items = search(client)["candidates"]
        assert len(items) == 3
        assert items[0]["provenance"]["parent_id"] == items[1]["provenance"]["parent_id"]
        assert items[1]["provenance"]["parent_id"] != items[2]["provenance"]["parent_id"]
        assert [item["rank"] for item in items] == [1, 3, 4]
        assert items[1]["action"]["evidence_id"] == "ref-01"
        assert all(item["action"] is not None for item in items)


def test_search_budget_reaches_browser_and_upstream_without_extending_other_reads():
    settings = replace(SETTINGS, search_timeout_sec=25, request_timeout_sec=7)
    client, upstream, _ = make_client(settings=settings)
    with client:
        budget = client.get("/demo-api/health").json()["search_timeout_ms"]
        assert budget == 25000
        result = search(client)
        assert client.get(result["candidates"][0]["video_url"]).status_code == 200
        for request in upstream.requests:
            timeouts = request.extensions["timeout"]
            assert timeouts["read"] == (budget / 1000 if request.url.path.endswith("/search") else 7)
            assert timeouts["connect"] == timeouts["write"] == timeouts["pool"] == 7


def test_auth_is_verified_cached_and_retried_once():
    upstream = Upstream()
    upstream.fail_search_once = True
    client, _, _ = make_client(upstream)
    with client:
        search(client)
        search(client)
        assert upstream.logins == 2
        assert sum(r.url.path.endswith("/auth/me") for r in upstream.requests) == 2
        assert sum(r.url.path.endswith("/search") for r in upstream.requests) == 3


def test_cat_scope_survives_auth_refresh_and_broadening_without_unsupported_dataset_filter():
    upstream = Upstream()
    upstream.fail_search_once = True
    client, _, _ = make_client(upstream)
    with client:
        response = client.post("/demo-api/search", json={**PAYLOAD, "scenario_id": "cat-play", "broaden": True})
        assert response.status_code == 200
        scope = response.json()["search_scope"]
        assert scope == {"tags": ["meow-10k", "cat-behavior"],
                         "requested_dataset_id": "hf-smgjch-meow-10k", "dataset_filter_applied": False}
        assert response.json()["candidates"][0]["provenance"]["dataset_id"] is None
        replay = client.post("/demo-api/search", json={**PAYLOAD, "scenario_id": "cat-play", "broaden": True, "mode": "replay"})
        assert replay.json()["search_scope"] == scope
    requests = [json.loads(r.content) for r in upstream.requests if r.url.path.endswith("/search")]
    assert len(requests) == 2
    assert all(item["tags"] == ["meow-10k", "cat-behavior"] for item in requests)
    assert all("metadata_filters" not in item for item in requests)


@pytest.mark.parametrize("kind,expected", [("timeout", 504), ("deadline", 504), ("error", 502), ("authentication", 502), ("unsupported_fast_search", 502)])
def test_upstream_failures_are_bounded_redacted_and_never_replayed(kind, expected):
    upstream = Upstream()
    settings = replace(SETTINGS, search_timeout_sec=0.01) if kind == "deadline" else SETTINGS
    upstream.search_timeout = kind == "timeout"
    upstream.search_delay = 0.1 if kind == "deadline" else 0
    upstream.search_status = {"error": 500, "authentication": 401, "unsupported_fast_search": 422}.get(kind, 200)
    client, _, _ = make_client(upstream, settings=settings)
    with client:
        response = client.post("/demo-api/search", json=PAYLOAD)
        assert response.status_code == expected
        assert set(response.json()) == {"error"}
        assert "test-secret" not in response.text and "test-token" not in response.text
        assert upstream.logins <= 2


def test_validation_and_unknown_scenario_do_not_echo_inputs_or_contact_upstream():
    client, upstream, _ = make_client()
    with client:
        response = client.post("/demo-api/search", json={**PAYLOAD, "password": "test-secret"})
        assert response.status_code == 422 and "test-secret" not in response.text
        response = client.post("/demo-api/search", json={**PAYLOAD, "scenario_id": "missing"})
        assert response.status_code == 404 and response.json()["error"]["code"] == "unknown_scenario"
        assert not upstream.requests


def test_cookie_scopes_video_and_expiry_restart_remove_access():
    client, _, app = make_client()
    with client:
        response = client.post("/demo-api/search", json=PAYLOAD)
        url = response.json()["candidates"][0]["video_url"]
        assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
        cookie = client.cookies.get(COOKIE_NAME)
        assert client.get(url).content == b"abcdef"
        client.cookies.clear()
        assert client.get(url).status_code == 404
        client.cookies.set(COOKIE_NAME, "different-session")
        assert client.get(url).status_code == 404
        client.cookies.clear()
        client.cookies.set(COOKIE_NAME, cookie)
        app.state.registry.sessions[cookie].expires = time.monotonic() - 1
        assert client.get(url).status_code == 404
        assert client.get("/demo-api/clips/missing/video?source=https://arbitrary.invalid").status_code == 404


def test_range_passthrough_uses_fixed_upstream_endpoint_and_closes_stream():
    upstream = Upstream()
    upstream.video_status = 206
    upstream.video_headers.update({"content-range": "bytes 2-7/100"})
    client, _, _ = make_client(upstream)
    with client:
        url = search(client)["candidates"][0]["video_url"]
        response = client.get(url, headers={"Range": "bytes=2-7", "If-Range": '"etag"'})
        assert response.status_code == 206 and response.content == b"abcdef"
        assert response.headers["content-range"] == "bytes 2-7/100"
        assert response.headers["content-length"] == "6"
        assert response.headers["accept-ranges"] == "bytes"
        request = upstream.requests[-1]
        assert request.url.path == "/api/v1/videos/stream"
        assert request.url.params["source"] == ROW["source"]
        assert request.url.params["token"] == "test-token-1"
        assert request.headers["range"] == "bytes=2-7" and request.headers["if-range"] == '"etag"'
        assert upstream.streams[-1].closed
        assert "location" not in response.headers


def test_head_falls_back_without_reading_body_and_range_416_is_preserved():
    upstream = Upstream()
    upstream.head_405 = True
    client, _, _ = make_client(upstream)
    with client:
        url = search(client)["candidates"][0]["video_url"]
        response = client.head(url)
        assert response.status_code == 200 and response.content == b""
        assert response.headers["content-length"] == "6"
        assert not upstream.streams[-1].read and upstream.streams[-1].closed
        upstream.video_status = 416
        upstream.video_headers = {"content-range": "bytes */6"}
        response = client.get(url, headers={"Range": "bytes=99-"})
        assert response.status_code == 416 and response.headers["content-range"] == "bytes */6"
        assert response.content == b"" and upstream.streams[-1].closed


def test_invalid_range_is_local_and_redirect_is_not_forwarded():
    upstream = Upstream()
    client, _, _ = make_client(upstream)
    with client:
        url = search(client)["candidates"][0]["video_url"]
        before = len(upstream.requests)
        assert client.get(url, headers={"Range": "bytes=0-1,3-4"}).status_code == 416
        assert len(upstream.requests) == before
        upstream.video_status = 302
        upstream.video_headers["location"] = "https://private.invalid/?token=test-secret"
        response = client.get(url)
        assert response.status_code == 502 and "location" not in response.headers
        assert "test-secret" not in response.text
        assert upstream.streams[-1].closed


def test_video_auth_retry_does_not_expose_token_to_browser():
    upstream = Upstream()
    upstream.video_fail_once = True
    client, _, _ = make_client(upstream)
    with client:
        url = search(client)["candidates"][0]["video_url"]
        response = client.get(url)
        assert response.status_code == 200 and upstream.logins == 2
        assert "test-token" not in str(response.headers)


def test_changed_caption_hash_and_invalid_manifest_fail_closed(tmp_path):
    reference = reviewed()
    reference["caption"] = "Changed after review"
    assert Manifest([reference]).entries == []
    path = tmp_path / "invalid.json"
    path.write_text("not json")
    app = create_app(replace(SETTINGS, manifest_path=path), httpx.MockTransport(Upstream()), loop_agent=EncounterAgent())
    with TestClient(app) as client:
        result = search(client)
        assert result["warnings"] and result["candidates"][0]["action"] is None
        assert str(path) not in json.dumps(result)


@pytest.mark.parametrize("mime", ["binary/octet-stream", "application/octet-stream", "Application/Octet-Stream"])
def test_deployed_binary_mime_type_is_normalized_for_mp4_playback(mime):
    upstream = Upstream()
    upstream.video_headers["content-type"] = mime
    client, _, _ = make_client(upstream)
    with client:
        url = search(client)["candidates"][0]["video_url"]
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp4"
        assert response.content == b"abcdef"


def test_upstream_cookies_are_not_sent_and_rejected_token_is_cleared():
    async def run():
        base = Upstream()

        async def handler(request):
            assert "cookie" not in request.headers
            response = await base(request)
            response.headers["set-cookie"] = "upstream-session=private; Path=/"
            return response

        app = create_app(SETTINGS, httpx.MockTransport(handler), loop_agent=EncounterAgent())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://demo.test") as client:
            await client.get("/demo-api/health")
            result = (await client.post("/demo-api/search", json=PAYLOAD)).json()
            assert (await client.get(result["candidates"][0]["video_url"])).status_code == 200
            base.search_status = 401
            assert (await client.post("/demo-api/search", json=PAYLOAD)).status_code == 502
            assert app.state.vss._token is None
        await app.state.vss.close()

    asyncio.run(run())


def test_stream_cleanup_errors_do_not_escape_with_private_diagnostics():
    from ranger_duck.stream import close_stream

    class FailedClose(VideoBytes):
        async def aclose(self):
            raise httpx.ReadError("private upstream URL with test-token")

    asyncio.run(close_stream(httpx.Response(200, stream=FailedClose())))


def test_malformed_source_and_configuration_do_not_crash():
    client, _, _ = make_client(Upstream([{**ROW, "source": "s3://[broken/clip.mp4"}]))
    with client:
        assert search(client)["status"] == "no_results"
    client, _, _ = make_client(settings=replace(SETTINGS, ingress_url="https://[broken"))
    with client:
        assert client.get("/demo-api/health").json()["live_configured"] is False


def test_extra_metadata_only_exposes_redacted_dataset():
    row = {**ROW, "extra_metadata": json.dumps({"dataset": "MammAlps", "private": "test-secret"})}
    client, _, _ = make_client(Upstream([row]))
    with client:
        result = search(client)
        assert result["candidates"][0]["provenance"]["dataset"] == "MammAlps"
        assert "test-secret" not in json.dumps(result)


@pytest.mark.parametrize("metadata", [
    {"dataset_id": "actual-archive-dataset"},
    {"metadata": {"dataset_id": "actual-archive-dataset"}},
    {"extra_metadata": {"dataset_id": "actual-archive-dataset"}},
    {"extra_metadata": json.dumps({"dataset_id": "actual-archive-dataset", "private": "test-secret"})},
])
def test_dataset_identity_comes_from_clip_metadata_not_requested_scope(metadata):
    client, _, _ = make_client(Upstream([{**ROW, **metadata}]))
    with client:
        result = client.post("/demo-api/search", json={**PAYLOAD, "scenario_id": "cat-play"}).json()
    assert result["search_scope"]["requested_dataset_id"] == "hf-smgjch-meow-10k"
    assert result["candidates"][0]["provenance"]["dataset_id"] == "actual-archive-dataset"
    assert "test-secret" not in json.dumps(result)


def test_health_bootstrap_keeps_replaced_search_in_one_session():
    async def run():
        base = Upstream()

        async def reordered(request):
            if request.url.path.endswith("/search") and "feeding" in json.loads(request.content)["query"]:
                await asyncio.sleep(0.03)
            return await base(request)

        app = create_app(SETTINGS, httpx.MockTransport(reordered), loop_agent=EncounterAgent())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://demo.test") as client:
            await client.get("/demo-api/health")
            session = client.cookies.get(COOKIE_NAME)
            old = asyncio.create_task(client.post("/demo-api/search", json=PAYLOAD))
            await asyncio.sleep(0.005)
            current = await client.post("/demo-api/search", json={"encounter_id": "encounter-02", "scenario_id": "deer-walking"})
            previous = await old
            assert current.status_code == 200 and previous.status_code == 409
            assert client.cookies.get(COOKIE_NAME) == session
            assert len(app.state.registry.sessions) == 1
            for response in (current,):
                url = response.json()["candidates"][0]["video_url"]
                assert (await client.get(url)).status_code == 200
        await app.state.vss.close()

    asyncio.run(run())


def test_stream_cleanup_finishes_when_browser_cancels_or_send_fails():
    import anyio
    from ranger_duck.app import ProxyStreamingResponse

    class BlockingBytes(httpx.AsyncByteStream):
        def __init__(self):
            self.closed = False

        async def __aiter__(self):
            yield b"first"
            await anyio.sleep_forever()

        async def aclose(self):
            await anyio.sleep(0.01)
            self.closed = True

    async def run(fail_send):
        stream = BlockingBytes()
        upstream = httpx.Response(200, stream=stream)
        response = ProxyStreamingResponse(upstream, upstream.aiter_raw())
        started = anyio.Event()

        async def send(message):
            if fail_send:
                raise RuntimeError("Client disconnected before body iteration")
            if message["type"] == "http.response.body":
                started.set()

        async def receive():
            await anyio.sleep_forever()

        scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
        if fail_send:
            with pytest.raises(RuntimeError):
                await response(scope, receive, send)
        else:
            async with anyio.create_task_group() as group:
                group.start_soon(response, scope, receive, send)
                await started.wait()
                group.cancel_scope.cancel()
        assert stream.closed

    asyncio.run(run(False))
    asyncio.run(run(True))
