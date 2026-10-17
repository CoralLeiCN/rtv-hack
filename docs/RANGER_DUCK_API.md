# Ranger Duck frontend and backend contract

Contract version 1, agreed implementation target on 17 October 2026. The user owns the frontend; the backend implements these routes. Any changes needed during implementation must be reflected here before handoff.

Use relative `/demo-api/` URLs. For separate frontend development, proxy that prefix to the backend on `127.0.0.1:8000` through the frontend dev server. Forward cookies and Range headers. This preserves same-origin behavior and avoids exposing VSS credentials. Production may serve the built frontend through the same backend when a static directory is configured.

## Health

`GET /demo-api/health`

```json
{
  "status": "ok",
  "api_version": "1",
  "live_configured": false,
  "reviewed_reference_count": 0
}
```

This checks local service configuration, not current upstream availability. It never returns configured endpoints or credential values.

Health also establishes the browser's HttpOnly demo session cookie. Await this request before starting searches, so overlapping initial encounters share one session. The encounter catalog can load in parallel.

## Encounters

`GET /demo-api/encounters`

```json
{
  "encounters": [
    {
      "id": "deer-feeding",
      "label": "Feeding",
      "animal": "deer",
      "behavior_hint": "feeding",
      "description": "A deer lowers its head to feed in a clearing.",
      "input_mode": "scripted_scene"
    }
  ]
}
```

Initial IDs are `deer-feeding`, `deer-walking`, and `deer-standing`. These describe staged scenarios, not verified footage availability. The server's scenario catalog may be adjusted after review; render its returned entries rather than hardcoding labels. No scenario includes a robot action.

## Search

`POST /demo-api/search`

```json
{
  "encounter_id": "encounter-001",
  "scenario_id": "deer-feeding"
}
```

The frontend creates a new encounter ID for every Start or reset cycle. The backend validates the scenario, constructs its query, and requests live VSS retrieval. It must not fall back silently to replay.

Example response with a reviewed result:

```json
{
  "encounter_id": "encounter-001",
  "search_id": "opaque-search-id",
  "mode": "live",
  "status": "ok",
  "query": "deer feeding with its head lowered",
  "elapsed_ms": 4200,
  "candidates": [
    {
      "clip_id": "opaque-clip-id",
      "video_url": "/demo-api/clips/opaque-clip-id/video",
      "caption": "The animal lowers its head toward the grass.",
      "similarity": 0.72,
      "review_status": "reviewed",
      "eligibility_reason": "reviewed_match",
      "animal": "deer",
      "reviewed_behavior": "feeding",
      "provenance": {
        "dataset": "MammAlps",
        "source_label": "Reference clip 03",
        "parent_id": "opaque-parent-id",
        "segment_start_sec": 5.0,
        "segment_end_sec": 10.0
      },
      "action": {
        "primitive": "ground_pick",
        "evidence_id": "reference-03",
        "max_duration_ms": 8000
      }
    }
  ],
  "warnings": []
}
```

This is an illustrative contract example, not a real reviewed reference or measured result. Opaque IDs have no meaningful format for the frontend.

Response `status` is `ok` when at least one candidate supports imitation, `no_supported_imitation` when clips exist but none are eligible, or `no_results` when there are no usable segment candidates. All three are successful HTTP responses.

Candidate rules:

- `review_status` is `reviewed`, `unreviewed`, or `stale`. `action` is non-null only for a reviewed, current, supported match.
- `animal` and `reviewed_behavior` are null without a valid review. `similarity` may be null and is a retrieval score, not a probability.
- `dataset` and segment times may be null if upstream data is incomplete. Missing timing or identity prevents imitation but may still permit playback.
- `eligibility_reason` is a machine-readable string such as `reviewed_match`, `not_reviewed`, `reference_changed`, `incomplete_metadata`, `unsupported_behavior`, or `species_mismatch`. Clients must tolerate additional reasons.
- `primitive` is `ground_pick`, `short_walk`, or `stand_hold` for the core demo. Optional supported values are `sit` and `head_scan`.
- `max_duration_ms` is a cancellation ceiling, not a claim of successful completion. The simulator must observe completion. Short walk is bounded to 2000 ms and stand hold to 3000 ms.
- `warnings` is a list of human-readable non-secret messages. No SQL, vectors, VSS tokens, or private storage URIs are returned.

The frontend should show up to three candidates, enable Copy only for a selected non-null action, and ignore any response whose encounter ID is no longer current. Changing a result cancels the previous action. The backend may include more candidates to retain a reviewed reference beyond the first three ranks.

## Video

`GET /demo-api/clips/{clip_id}/video` and `HEAD` on the same route.

The route accepts ordinary byte-range requests and forwards status and relevant headers, including `Content-Type`, `Content-Length`, `Content-Range`, and `Accept-Ranges`. A valid range can return 206; an invalid range can return 416. The response must never redirect the browser to a token-bearing upstream URL.

Clip IDs are scoped to the browser's local demo session using an HttpOnly, SameSite cookie. Health establishes that session; search also creates it if missing. An unknown, expired, or different-session ID returns 404. The frontend must not persist clip IDs across backend restarts; rerun the search if a clip expires. No arbitrary URL or S3 URI parameter is accepted.

Playback of a cut segment starts at zero. For the displayed archive timestamp, add `segment_start_sec` when present. Do not use that offset as the video's local seek position.

## Errors

Errors use a consistent JSON body:

```json
{
  "error": {
    "code": "upstream_timeout",
    "message": "The video search timed out. Please retry.",
    "retryable": true
  }
}
```

Expected cases include 422 `invalid_request`, 404 `unknown_scenario`, 503 `live_not_configured`, 502 `upstream_error`, 504 `upstream_timeout`, and 404 `clip_not_found`. Authentication failures upstream are reported without credential or response-body details. Errors do not contain a fabricated successful result.

## Frontend integration sequence

1. Load health and the encounter catalog. Await health before sending any searches to establish the session cookie.
2. Start the selected scene and create a new encounter ID.
3. Send the search request when the scripted animal enters the encounter zone.
4. Display results, measured time, and a selected reference video on the same page.
5. On Copy, send the returned action to the frontend simulator adapter and show execution status.
6. On Reset, abort the pending fetch, invalidate the encounter ID, stop the motion, and clear the previous evidence selection.

Frontend cancellation does not guarantee the upstream request stops, so the ID check is mandatory. The backend performs no simulator actions and creates no live model-training jobs.

Replay support is deferred until live search and playback work. Any future replay route must return `mode: "replay"` and remain distinct from this live endpoint.
