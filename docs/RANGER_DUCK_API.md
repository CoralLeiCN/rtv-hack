# Ranger Duck frontend and backend contract

Contract version 1, updated 17 October 2026 for six supported motions, caption activity priority and an automatic sequence. The frontend and backend implement these routes.

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
      "eligibility_reason": "caption_behavior_match",
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

Response `status` is `ok` when any returned candidate supports imitation, `no_supported_imitation` when clips exist but none is eligible, or `no_results` when there are no usable segment candidates. All three are successful HTTP responses.

Candidate rules:

- `rank` is the original one-based upstream segment rank. Invalid or duplicate sources can leave gaps; no parent-diversity reranking or promotion occurs.
- `review_status` is `reviewed`, `unreviewed`, or `stale`. A non-null `action` can have `action_basis: "reviewed"` or `"video_caption"`. Caption inference never changes the status to reviewed.
- `action_reason` explains the observed role and approximation. `inferred_behavior` describes caption-derived behavior; `reviewed_behavior` is reserved for a valid visual review. `animal` and `interaction_partner` identify the supported pair when available.
- A caption-inferred action requires the selected species, an explicitly supported behavior and complete source/parent/interval metadata. Single-animal footage is eligible. The query asks for interactions, but the returned action does not require one. Shared, solitary and social behavior must retain their actual labels; ambiguous actors, negated statements and unsupported movements remain ineligible.
- An exact current review can authorize a supported solitary or social behavior. Pair evidence is optional. Stale, invalid or contradictory reviews block caption fallback.
- `similarity` is a retrieval score, not a probability. `dataset` and interval times may be null for incomplete upstream data; such a result may still be playable without authorizing movement.
- `caption_hash` hashes the exact upstream caption before display redaction. `review_reason` is a reviewer's actual recorded note, or null. Do not invent a review.
- `eligibility_reason` is a machine-readable explanation such as `caption_behavior_match`, `reviewed_match`, `reference_changed`, `incomplete_metadata`, or `interaction_not_supported`. Clients tolerate additional reasons.
- Supported `primitive` values are `ground_pick` (8000 ms motion window), `short_walk` (2000), `head_nod` (2400), `head_scan` (2400), `sit_cycle` (6000), and `stand_hold` (3000). `head_nod` needs explicit vertical head movement; `sit_cycle` needs explicit sitting/seated evidence, not lying. Retreat-only evidence is unsupported because backward walking was not reliable in physics checks.
- `max_duration_ms` bounds the controller command; success requires observed execution and settling. It is not a promised completion time. The adapter rejects a sit window below 5500 ms and preserves the native stand-up when canceled; it does not abruptly switch policies.
- `warnings` contains human-readable non-secret messages. No SQL, vectors, VSS tokens, or private storage URIs are returned.

Within each caption, supported actions are considered in this order: `short_walk`, `ground_pick`, `head_nod`, `head_scan`, `sit_cycle`, `stand_hold`. The classifier checks all caption phrases at each priority, preserving selected-species actor attribution, negation and uncertainty checks. This selects active observed behavior over a simultaneous static description; it does not override an exact current review or reorder retrieval results. See the [motion inventory](RANGER_DUCK_ANIMATION.md).

The frontend filters all returned candidates by compatibility, sorts by original `rank`, and uses up to three eligible actions. Queue positions are 1–3; source rank stays visible for provenance. Incompatible clips do not occupy a card or loop slot, and a later source rank can fill a queue position. If fewer than three qualify, show the actual count.

One animal may patrol outside the east side of the yellow box while the duck roams. Before an evidence action, the animal returns to its interaction anchor and faces the duck; the browser waits for that observed settling, then the duck approaches, settles and performs the action. Navigation is distinct from the reference-derived motion and does not overlap it. Preserve the same duck body and physics clock throughout; repeat the same queue without new searches or resets.

Stop/Resume controls both navigation and the action sequence. Reset, changed encounters, replacement searches, hidden-tab pause and teardown cancel motion. A visibility-only pause automatically resumes on return; manual Stop or reference inspection stays paused. Ignore responses whose encounter ID is no longer current.

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
3. Send the search request when the one-animal encounter is ready. The animal may patrol outside the box; it never enters the duck arena.
4. Display results, measured time, and a selected reference video on the same page.
5. Select the first three compatible actions, display their source ranks, and loop through approach, evidence action and roaming phases. Preserve physics across clips and cycles; repeat without another search.
6. On Reset, abort the pending fetch, invalidate the encounter ID, stop the motion, and clear the previous evidence selection.

Frontend cancellation does not guarantee the upstream request stops, so the ID check is mandatory. The backend performs no simulator actions and creates no live model-training jobs.

Rehearsal controls may demonstrate explicitly labeled local no-match and timeout states. They must not fabricate live search evidence or enable imitation. Returning to Live clears rehearsal state.

## Additional Agent Loop mode

The existing encounter routes and top-three sequence above are unchanged. Agent
Loop mode uses separate sessions and may select an eligible result at any
original rank. Health adds `loop_agent_available` (CLI executable present, not a
login or connectivity check) and `loop_cycle_timeout_ms` (180000).

Bootstrap with health to establish the cookie, then:

| Request | Body | Result |
| --- | --- | --- |
| `POST /demo-api/loop` | `session_id` (client-generated UUID), `prompt` (1–1000 characters), `animal` (`cat` or `deer`) | Creates/replaces this browser's loop; returns ID and cycle timeout |
| `POST /demo-api/loop/{id}/next` | None | Generates a query, searches, and returns one validated clip/action |
| `POST /demo-api/loop/{id}/outcome` | Outcome below | Acknowledges actual execution; permits the next search only after completion |
| `POST /demo-api/loop/{id}/pause` | None | Cancels active agent work and invalidates outstanding actions |
| `POST /demo-api/loop/{id}/resume` | None | Resumes with preserved context and a fresh search; resets failure counter |

A cycle response includes `session_id`, `cycle_id`, `cycle`, `query`,
`query_reason`, `response_reason`, `action`, `role_plan`, `candidates`, and `clip`. The action uses the
existing `primitive`, `evidence_id`, and `max_duration_ms` fields. The clip
includes an opaque `clip_id`/`video_url`, caption, original retrieval `rank`,
`observed_behavior`, `evidence_basis`, and parent `start_sec`/`end_sec` offsets.
Playback starts at zero. Source URIs and credentials remain server-side.

`role_plan` binds the two video subjects to one scene companion and the duck:

```json
{
  "grounding": "caption_roles",
  "companion": {"subject": "Approaching deer", "evidence": "one deer approaches"},
  "duck": {"subject": "Watching deer", "evidence": "the other deer watches"},
  "companion_behavior": "approach",
  "duck_behavior": "looking",
  "companion_duration_ms": 3000,
  "timing": "together"
}
```

The subjects must be distinct and both excerpts must occur in the selected
caption. This checks the source binding, not the semantic correctness of the
model's interpretation. `timing` is `together`, `companion_first`, or `duck_first`.
Supported companion behaviors are standing, alert, walking, approach, retreat,
and feeding; cats also allow hissing, greeting, and play. Durations are fixed
by the backend at 3000 ms. The duck action approximates the counterpart's
observed behavior with the existing bounded primitives. The backend validates
`duck_behavior` against its primitive: still → stand_hold, looking → head_scan,
moving → short_walk, feeding → ground_pick. Unknown roles use the neutral fallback.

When two supported roles cannot be established, Codex sets
`grounding: "insufficient_evidence"`. The backend normalizes the plan to standing
plus `stand_hold`, empty excerpts, unassigned subjects, and simultaneous timing.
The result remains selectable and playable, with an explicit neutral-fallback
explanation. No counterpart behavior is claimed. The UI labels both role mappings
as caption-inferred approximations, not an exact video reconstruction.

An outcome has this shape:

```json
{
  "cycle_id": "opaque-cycle-id",
  "primitive": "head_scan",
  "status": "completed",
  "playback": "ended",
  "companion": {"behavior": "approach", "status": "completed"},
  "state": {
    "status": "complete",
    "position": [0.1, 0.0, 0.2],
    "head_yaw": 0.01,
    "simulation_time": 12.0
  }
}
```

Outcome status is `completed`, `failed`, or `cancelled`; playback is `ended`,
`failed`, or `cancelled`. Completion requires ended playback and controller state
`complete`, plus a completed companion animation matching the issued behavior.
Companion completion describes a scripted render animation, not physics. Other
outcomes pause the session. The next query receives both outcomes and the role
plan. Cancellation prevents a delayed second role from starting. Telemetry comes from the browser
simulator, is schema-validated and cycle-bound, and is not independent physical
attestation. Duplicate or stale outcomes return 409. The browser must stop its
own movement/video immediately on cancellation; server cancellation alone cannot
control browser physics.

Only one next request or outstanding action is allowed per session. Each cycle
has a 180-second overall deadline, at most two VSS searches, and at most four
structured Codex decisions (query and action selection per attempt). No-match
attempts refine the query. Three consecutive failed cycle requests pause the
session. The browser does not retry configuration failures or simulator failures
automatically. The last five issued clip intervals cannot execute again, and the last
five reaction records inform the agent. Clips longer than 120 seconds remain listed but cannot execute,
so playback waiting is bounded. There is no automatic replay fallback.

Loop searches ask for two cats or two deer interacting and request `top_k: 10`.
The cycle response includes `candidates`, the same ranked list given to Codex:
`candidate_id`, `rank`, `caption`, `observed_behavior`, `evidence_basis`,
`allowed_actions`, and `unavailable_reason`. Return all available results up to
10 in upstream order, without pair, species-presence, or behavior filtering,
deduplication, or promotion from rank 11. Single-animal and weak matches remain
selectable. The UI shows this list separately from the one selected clip.

Unexecutable results remain listed with an empty `allowed_actions`: incomplete
provenance, invalid source, stale/contradictory review, duration over 120 seconds,
or a recently issued interval. When no candidate can execute, bounded recovery
still applies. These checks are independent of caption content.
All executable candidates offer `stand_hold`, `head_scan`, `short_walk`, and
`ground_pick`, with ceilings of 3000/2400/2000/8000 ms respectively.
`observed_behavior: "caption_context"` does not assert a classified animal
behavior. The caption is inferred evidence; the role plan separately identifies
the two subjects and supported approximations, or a neutral fallback. Encounter
imitation checks are unchanged, while its scene now shows one animal plus the duck.

Sessions are memory-only, tied to the browser cookie, bounded by the existing
session capacity/TTL, and invalidated on backend restart. Use one backend worker.
