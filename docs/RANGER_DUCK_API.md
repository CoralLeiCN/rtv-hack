# Ranger Duck frontend and backend contract

Contract version 1, updated 17 October 2026 for local OAuth agent planning, six supported motions and automatic animal attention. The frontend and backend implement these routes.

Use relative `/demo-api/` URLs. For separate frontend development, proxy that prefix to the backend on `127.0.0.1:8000` through the frontend dev server. Forward cookies and Range headers. This preserves same-origin behavior and avoids exposing VSS credentials. Production may serve the built frontend through the same backend when a static directory is configured.

## Health

`GET /demo-api/health`

```json
{
  "status": "ok",
  "api_version": "1",
  "live_configured": false,
  "reviewed_reference_count": 0,
  "search_timeout_ms": 30000,
  "encounter_agent_available": true,
  "encounter_plan_timeout_ms": 60000,
  "encounter_timeout_ms": 180000,
  "loop_agent_available": true,
  "loop_cycle_timeout_ms": 180000
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

IDs are `deer-feeding`, `deer-walking`, `deer-standing`, `cat-hissing`, `cat-greeting`, and `cat-play`. Species and interaction selectors are derived from this catalog. These describe staged scenarios, not verified footage availability. The server's scenario catalog may be adjusted after review; render its returned entries rather than hardcoding labels. `query` and `broader_query` are legacy catalog examples, not executed queries or loading previews; the agent creates the actual query on demand. No scenario includes a robot action.

## Encounter query planning

`POST /demo-api/encounter-plan`

```json
{"encounter_id":"encounter-001","scenario_id":"deer-feeding","broaden":false}
```

The local ChatGPT-authenticated Codex CLI generates a concrete query covering
same-species interaction **or similar individual behavior**. The structured decision requires both an interaction branch and a similar solitary-behavior branch; the server validates both species scopes and joins them with `OR`. The response is:

```json
{
  "encounter_id":"encounter-001",
  "plan_id":"opaque-plan-id",
  "query":"Deer grazing together or a single deer lowering its head to feed",
  "query_reason":"Find observable feeding motion, whether social or solitary.",
  "query_basis":"agent"
}
```

This example is illustrative, not a fixed query. Display the returned query
before search. Plans are session/scenario/encounter/broaden-bound and expire
within five minutes (or the shorter clip TTL). Planning has a 60-second deadline.
`POST /demo-api/encounters/{encounter_id}/cancel` cancels pending planning/search
and invalidates its plan. Stop, Reset and replacement also abort the browser
request; the backend watches disconnection and terminates the CLI subprocess.

## Search

`POST /demo-api/search`

```json
{
  "encounter_id": "encounter-001",
  "scenario_id": "deer-feeding",
  "mode": "live",
  "broaden": false,
  "plan_id": "opaque-plan-id"
}
```

The frontend creates a new encounter ID for every Start or reset cycle. `mode` defaults to `live`; `broaden` defaults to false. Live mode validates and executes the supplied plan. Without `plan_id`, it generates a plan internally. It retrieves VSS clips, then asks the agent for one batched caption-grounded action plan. It never falls back silently to replay. An explicit broader search relaxes the interaction wording while retaining the selected species, and returns `match_type: "broader_behavior"`. Normal searches retain the legacy `species_interaction` match label; individual behavior is also eligible. Cat requests send `tags: ["meow-10k", "cat-behavior"]`; deer requests retain `tags: ["wildlife"]`. This applies to Encounter and Loop mode, including broader searches.

Cat responses include `search_scope` with the two applied tags,
`requested_dataset_id: "hf-smgjch-meow-10k"` and `dataset_filter_applied: false`.
The current VSS metadata schema does not expose `dataset_id` as a filter, so no
unsupported metadata filter is sent. The requested ID describes configuration,
not verified clip provenance. If the archive supplies an actual `dataset_id`,
it is preserved separately in candidate provenance (or the Loop clip).

Replay is an explicit request for the last successful live search in this browser session for the same scenario and broaden setting. It performs no new search or agent call, reuses recorded decisions, returns `mode: "replay"`, and issues fresh scoped clip IDs. A missing or expired snapshot returns 409 `replay_unavailable`. Snapshots expire after the clip TTL and disappear on restart; video playback still needs VSS connectivity. An older slow response cannot replace a newer snapshot. The UI must label replay and show the original recording time separately from the current request duration.

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

Additional response fields are `query_basis: "agent"`, `query_reason`,
`action_planner: "agent"` and `agent_plan: {"summary": "..."}`. Each candidate
adds `action_planner`, `agent_reason` and `evidence_excerpt` (an exact caption
substring for valid inferred actions). All values are redacted for browser
display. Search plus action planning has a 180-second deadline, including the
existing VSS search budget. The browser adds five seconds of transport grace.

Candidate rules:

- `rank` is the original one-based upstream segment rank. Invalid or duplicate sources can leave gaps; no parent-diversity reranking or promotion occurs.
- `review_status` is `reviewed`, `unreviewed`, or `stale`. A non-null `action` can have `action_basis: "reviewed"` or `"video_caption"`. Caption inference never changes the status to reviewed.
- `action_reason` explains the observed role and approximation. `inferred_behavior` describes caption-derived behavior; `reviewed_behavior` is reserved for a valid visual review. `animal` and `interaction_partner` identify the supported pair when available.
- A caption-inferred action requires the selected species, an explicitly supported behavior and complete source/parent/interval metadata. Single-animal footage is eligible. The query permits interactions or similar solitary motion. Shared, solitary and social behavior must retain their actual labels; ambiguous actors, negated statements and unsupported movements remain ineligible.
- The agent proposal must select a permitted primitive and quote an exact contiguous caption excerpt that independently supports it. Skipped, omitted or unverified proposals remain ineligible (`agent_skipped` or `agent_action_unverified`); unavailable evidence cannot be overridden.
- An exact current review can authorize a supported solitary or social behavior. Pair evidence is optional. Stale, invalid or contradictory reviews block caption fallback.
- `similarity` is a retrieval score, not a probability. `dataset` and interval times may be null for incomplete upstream data; such a result may still be playable without authorizing movement.
- `caption_hash` hashes the exact upstream caption before display redaction. `review_reason` is a reviewer's actual recorded note, or null. Do not invent a review.
- `eligibility_reason` is a machine-readable explanation such as `caption_behavior_match`, `reviewed_match`, `reference_changed`, `incomplete_metadata`, or `interaction_not_supported`. Clients tolerate additional reasons.
- Supported `primitive` values are `ground_pick` (8000 ms motion window), `short_walk` (2000), `head_nod` (2400), `head_scan` (2400), `sit_cycle` (6000), and `stand_hold` (3000). `head_nod` needs explicit vertical head movement; `sit_cycle` needs explicit sitting/seated evidence, not lying. Retreat-only evidence is unsupported because backward walking was not reliable in physics checks.
- `max_duration_ms` bounds the controller command; success requires observed execution and settling. It is not a promised completion time. The adapter rejects a sit window below 5500 ms and preserves the native stand-up when canceled; it does not abruptly switch policies.
- `warnings` contains human-readable non-secret messages. No SQL, vectors, VSS tokens, or private storage URIs are returned.

Within each caption, retrieval-eligible actions are considered in this order: `short_walk`, `ground_pick`, `head_nod`, `sit_cycle`. The underlying classifier retains scan/hold for internal compatibility, but retrieval selection explicitly excludes them. The classifier checks all caption phrases at each priority, preserving selected-species actor attribution, negation and uncertainty checks. This selects active observed behavior over a simultaneous static description; it does not override an exact current review or reorder retrieval results. See the [motion inventory](RANGER_DUCK_ANIMATION.md).

Both modes exclude `head_scan` and `stand_hold` from retrieval-selected actions. The backend emits no action for passive-only evidence (`passive_behavior_excluded`), and the frontend also filters passive actions from stale or older responses before choosing slots. Mixed captions can still supply a supported active behavior, such as sitting despite also looking around.

The frontend filters all returned candidates by active compatibility, sorts by original `rank`, and uses up to three eligible actions. Queue positions are 1–3; source rank stays visible for provenance. Incompatible clips do not occupy a card or loop slot, and a later source rank can fill a queue position. If fewer than three qualify, show the actual count.

One animal stays outside the east side of the yellow box. As soon as it appears, the duck faces and approaches it as needed, including during query planning and search. It remains attentive between actions. Before an evidence action, the animal returns to its interaction anchor and faces the duck; the browser waits for that observed settling, then the duck approaches, settles and performs the action. Navigation is distinct from the reference-derived motion and does not overlap it. Preserve the same duck body and physics clock throughout; repeat the same queue without new searches or resets.

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
3. Call encounter-plan and show its generated query/reason, then search with the returned plan ID. The animal remains outside the duck arena.
4. Display results, measured time, and a selected reference video on the same page.
5. Select the first three compatible actions, display their source ranks, and loop through approach, evidence action and attention phases. Preserve physics across clips and cycles; repeat without another search.
6. On Reset, abort the pending fetch, invalidate the encounter ID, stop the motion, and clear the previous evidence selection.

Frontend cancellation does not guarantee the upstream request stops, so the ID check is mandatory. The backend performs no simulator actions and creates no live model-training jobs.

Rehearsal controls may demonstrate explicitly labeled local no-match and timeout states. They must not fabricate live search evidence or enable imitation. Returning to Live clears rehearsal state.

## Additional Agent Loop mode

Agent
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
  "duck": {"subject": "Following deer", "evidence": "the other deer follows"},
  "companion_behavior": "approach",
  "duck_behavior": "moving",
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
`duck_behavior` against its retrieval-eligible primitive: moving → short_walk,
feeding → ground_pick, nodding → head_nod, sitting → sit_cycle. Scanning and
standing holds are excluded; missing behavior cannot become a neutral fallback.

A supported individual behavior uses `grounding: "single_behavior"`, an exact
selected-species duck evidence excerpt, an unassigned stationary companion and
`together` timing. The backend independently checks the excerpt for that
supported motion. No second observed animal is claimed.

When no supported active behavior can be established, the clip cannot be
selected. The backend rejects passive or insufficient-evidence plans instead of
substituting `stand_hold`. With no eligible candidates, Loop makes its bounded
query retry and then reports no compatible active motion. Scene companion
standing remains allowed; the exclusion applies to the duck's evidence action.

An outcome has this shape:

```json
{
  "cycle_id": "opaque-cycle-id",
  "primitive": "short_walk",
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

Loop queries cover cat–cat or deer–deer interactions, or similar individual
behavior of the selected species, and request `top_k: 10`.
The cycle response includes `candidates`, the same ranked list given to Codex:
`candidate_id`, `rank`, `caption`, `observed_behavior`, `evidence_basis`,
`allowed_actions`, and `unavailable_reason`. Return all available results up to
10 in upstream order, without pair, species-presence, or behavior filtering,
deduplication, or promotion from rank 11. Single-animal clips remain selectable when their captions support an active
action; weak/passive matches remain listed with no allowed actions. The UI shows this list separately from the one selected clip.

Unexecutable results remain listed with an empty `allowed_actions`: incomplete
provenance, invalid source, stale/contradictory review, duration over 120 seconds,
a recently issued interval, passive-only evidence or no supported active motion.
The action list contains only the grounded active primitive for that caption or
exact review. Supported active ceilings are walking 2000 ms, beak dip 8000 ms,
head nod 2400 ms and sit/stand 6000 ms. Backend and frontend both reject scan/hold
selection. Caption interpretation remains inferred, not visual review.

Sessions are memory-only, tied to the browser cookie, bounded by the existing
session capacity/TTL, and invalidated on backend restart. Use one backend worker.
