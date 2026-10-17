# Ranger Duck frontend and backend contract

Contract version 1, updated 17 October 2026 for same-species interactions and an automatic sequence. The frontend and backend implement these routes.

Use relative `/demo-api/` URLs. For separate frontend development, proxy that prefix to the backend on `127.0.0.1:8000` through the frontend dev server. Forward cookies and Range headers. This preserves same-origin behavior and avoids exposing VSS credentials. Production may serve the built frontend through the same backend when a static directory is configured.

## Health

`GET /demo-api/health`

```json
{
  "status": "ok",
  "api_version": "1",
  "live_configured": false,
  "reviewed_reference_count": 0,
  "search_timeout_ms": 30000
}
```

This checks local service configuration, not current upstream availability. It never returns configured endpoints or credential values.

Health also establishes the browser's HttpOnly demo session cookie. Await this request before starting searches, so overlapping initial encounters share one session. The encounter catalog can load in parallel.

`search_timeout_ms` is the configured overall backend deadline, including authentication and search (default 30000; supported 1000–60000). The browser uses this budget plus 5000 ms of connection/proxy grace, falling back to 30000 + 5000 ms if an older backend omits it. A backend timeout remains a visible error, never an automatic replay.

## Encounters

`GET /demo-api/encounters`

```json
{
  "encounters": [
    {
      "id": "deer-feeding",
      "label": "Forage together",
      "animal": "deer",
      "behavior_hint": "feeding",
      "interaction_partner": "deer",
      "interaction": "co-feeding",
      "role": "focal_animal",
      "description": "One deer forages beside Microduck; the duck takes the companion role from the archive reference.",
      "input_mode": "scripted_scene",
      "query": "Two deer interacting while grazing together side by side, one deer lowering its head to feed beside the other deer",
      "broader_query": "Two deer interacting with each other"
    }
  ]
}
```

IDs are `deer-feeding`, `deer-walking`, `deer-standing`, `cat-hissing`, `cat-greeting`, and `cat-play`. Species and interaction selectors are derived from this catalog. These describe staged scenarios, not verified footage availability. The server's scenario catalog may be adjusted after review; render its returned entries rather than hardcoding labels. `query` and `broader_query` are display previews while a request is in flight; the server still selects the actual query. No scenario includes a robot action.

## Search

`POST /demo-api/search`

```json
{
  "encounter_id": "encounter-001",
  "scenario_id": "deer-feeding",
  "mode": "live",
  "broaden": false
}
```

The frontend creates a new encounter ID for every Start or reset cycle. `mode` defaults to `live`; `broaden` defaults to false. Live mode validates the scenario, constructs its query, and requests VSS retrieval. It never falls back silently to replay. An explicit broader search relaxes the interaction wording while retaining the selected species pair, and returns `match_type: "broader_behavior"`. Normal searches return `species_interaction`. Cat requests use the authenticated archive without a wildlife-only tag; deer requests retain the wildlife tag.

Replay is an explicit request for the last successful live search in this browser session for the same scenario and broaden setting. It performs no new search, returns `mode: "replay"`, and issues fresh scoped clip IDs. A missing or expired snapshot returns 409 `replay_unavailable`. Snapshots expire after the clip TTL and disappear on restart; video playback still needs VSS connectivity. An older slow response cannot replace a newer snapshot. The UI must label replay and show the original recording time separately from the current request duration.

Illustrative response with a caption-inferred interaction:

```json
{
  "encounter_id": "encounter-001",
  "search_id": "opaque-search-id",
  "mode": "live",
  "match_type": "species_interaction",
  "status": "ok",
  "query": "Two deer interacting while grazing together side by side, one deer lowering its head to feed beside the other deer",
  "elapsed_ms": 4200,
  "original_elapsed_ms": 4200,
  "recorded_at": "2026-10-17T12:00:00+00:00",
  "candidates": [
    {
      "clip_id": "opaque-clip-id",
      "rank": 1,
      "video_url": "/demo-api/clips/opaque-clip-id/video",
      "caption": "Two deer graze together side by side, lowering their heads to the grass.",
      "caption_hash": "sha256:<64 lowercase hexadecimal characters>",
      "review_reason": null,
      "similarity": 0.72,
      "review_status": "unreviewed",
      "eligibility_reason": "caption_interaction_match",
      "action_basis": "video_caption",
      "action_reason": "The caption describes two deer grazing together; one ground-pick cycle approximates feeding beside a companion.",
      "inferred_behavior": "co_feeding",
      "interaction_partner": "deer",
      "animal": "deer",
      "reviewed_behavior": null,
      "provenance": {
        "dataset": "MammAlps",
        "source_label": "Reference clip 01",
        "parent_id": "opaque-parent-id",
        "segment_start_sec": 5.0,
        "segment_end_sec": 10.0
      },
      "action": {
        "primitive": "ground_pick",
        "evidence_id": "opaque-caption-evidence-id",
        "max_duration_ms": 8000
      }
    }
  ],
  "warnings": []
}
```

This is an illustrative contract example, not real archive evidence or a measured result. Opaque IDs have no meaningful format for the frontend.

Response `status` is `ok` when at least one candidate at original rank 1–3 supports imitation, `no_supported_imitation` when clips exist but none of those three is eligible, or `no_results` when there are no usable segment candidates. All three are successful HTTP responses.

Candidate rules:

- `rank` is the original one-based upstream segment rank. Invalid or duplicate sources can leave gaps; no parent-diversity reranking or promotion occurs.
- `review_status` is `reviewed`, `unreviewed`, or `stale`. A non-null `action` can have `action_basis: "reviewed"` or `"video_caption"`. Caption inference never changes the status to reviewed.
- `action_reason` explains the observed role and approximation. `inferred_behavior` describes caption-derived behavior; `reviewed_behavior` is reserved for a valid visual review. `animal` and `interaction_partner` identify the supported pair when available.
- A caption-inferred action requires the selected species pair, a supported directed, collective, or explicitly described focal action in that pair clip, and complete source/parent/interval metadata. Shared or parallel activity is labeled as such, never relabeled as the queried greeting or hiss. Solitary animals, ambiguous actor/target claims, negated statements, and unsupported actions do not authorize motion.
- An exact reviewed entry must also confirm the interaction partner and evidence. A solitary-animal review is insufficient. Stale, invalid or contradictory reviews block caption fallback.
- `similarity` is a retrieval score, not a probability. `dataset` and interval times may be null for incomplete upstream data; such a result may still be playable without authorizing movement.
- `caption_hash` hashes the exact upstream caption before display redaction. `review_reason` is a reviewer's actual recorded note, or null. Do not invent a review.
- `eligibility_reason` is a machine-readable explanation such as `caption_interaction_match`, `reviewed_match`, `reference_changed`, `incomplete_metadata`, or `interaction_not_supported`. Clients tolerate additional reasons.
- Supported `primitive` values are `ground_pick` (8000 ms ceiling), `short_walk` (2000), `stand_hold` (3000), and `head_scan` (2400). Retreat-only evidence is unsupported because backward walking was not reliable in physics checks.
- `max_duration_ms` bounds the controller command; success requires observed execution and settling. It is not a promised completion time.
- `warnings` contains human-readable non-secret messages. No SQL, vectors, VSS tokens, or private storage URIs are returned.

The frontend uses exactly original ranks 1–3. Each eligible reference is selected and played muted automatically, then its action runs to observed completion before the next slot. Unsupported or missing slots remain visible with a skip reason. Rank 4 is never substituted. After the sequence, wait for the same duck body to settle and repeat the evidence without resetting physics or sending another search. If no slot is eligible, remain still and show why.

Stop/Resume pauses or restarts this sequence; Reset, a new encounter, a replacement search, hidden-tab pause, and page teardown cancel current motion. A visibility-only pause automatically resumes when the tab returns; manual Stop or reference inspection stays paused. Selecting a reference manually pauses automatic motion for inspection. Ignore responses whose encounter ID is no longer current.

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

Expected cases include 422 `invalid_request`, 404 `unknown_scenario`, 503 `live_not_configured`, 502 `upstream_error`, 504 `upstream_timeout`, 409 `replay_unavailable`, and 404 `clip_not_found`. Authentication failures upstream are reported without credential or response-body details. Errors do not contain a fabricated successful result.

## Frontend integration sequence

1. Load health and the encounter catalog. Await health before sending any searches to establish the session cookie.
2. Start the selected scene and create a new encounter ID.
3. Send the search request when the scripted animal enters the encounter zone.
4. Display results, measured time, and a selected reference video on the same page.
5. Automatically run supported original ranks 1–3 in order through the simulator adapter, displaying evidence basis, rank, cycle, and actual execution status. Preserve the duck body, pose and physics clock across clips and cycles; repeat without searching again.
6. On Reset, abort the pending fetch, invalidate the encounter ID, stop the motion, and clear the previous evidence selection.

Frontend cancellation does not guarantee the upstream request stops, so the ID check is mandatory. The backend performs no simulator actions and creates no live model-training jobs.

Rehearsal controls may demonstrate explicitly labeled local no-match and timeout states. They must not fabricate live search evidence or enable imitation. Returning to Live clears rehearsal state.
