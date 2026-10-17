# Ranger Duck backend

A read-only FastAPI service for the single-page wildlife encounter demo. The frontend and Microduck simulator are built separately; this directory contains no frontend code. The shared [API contract](../../../docs/RANGER_DUCK_API.md) is the integration reference.

The local service asks the signed-in Codex CLI to generate a query for the selected animal's interactions or similar individual behavior, retrieves ranked VSS clips, and asks the agent to plan bounded actions from their captions or exact reviews. It returns redacted references and proxies segment playback. A deterministic classifier requires the selected species and a supported visible behavior; returned footage may contain a solitary animal. The requested scenario never supplies a missing action. It never trains, uploads, re-ingests, deploys, or changes the shared pipeline.

## Run locally without VSS configuration

Python 3.11 or newer:

```bash
cd apps/ranger-duck/backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m uvicorn ranger_duck.app:app --host 127.0.0.1 --port 18000 --workers 1
```

`GET /demo-api/health` and `GET /demo-api/encounters` work immediately. Search returns `503 live_not_configured` until the backend has all three required environment variables. No mock data masquerades as live results.

Use **one worker**: session capabilities and authentication cache live in memory. Restarting invalidates clip URLs. This is a local workshop service; keep it on loopback or behind your authenticated workshop access.

## Connect the frontend

Use relative `/demo-api` URLs. During frontend development, proxy `/demo-api` to `http://127.0.0.1:18000`, including cookies, `Range`, and `If-Range`. Browser search requests and video URLs must use the frontend origin. This avoids CORS and credential exposure.

The single page uses `/demo-api/runs` for both Loop toggle positions. A run starts with `{run_id, animal, scenario_id, intent, adaptive}`. Loop OFF repeats its validated queue without new agent/search calls. Loop ON asks for a new round after every queued action has an acknowledged actual outcome. Changing the toggle affects the next queue boundary and does not cancel a running action or search.

The first round uses the selected encounter. After a completed live queue, each adaptive round randomly selects a different catalog encounter for the same animal. The chosen `scenario` snapshot is returned with the query plan and search round, and feeds both query and batch-action planning. The original intent remains the overall goal; actual outcomes record the encounter that produced them. Pausing or retrying a pending round retains its chosen encounter, and replay keeps the recorded encounter without consuming the pending live choice. Loop OFF never rotates an encounter during queue repetition.

Runs, query plans, and cancellation are scoped by both the browser cookie and run ID, so separate tabs can execute independently. A browser session retains up to eight runs; starting another retires its oldest paused run, or returns `run_limit_reached` if none is paused. It never silently replaces an active run in another tab.

| Request | Input / result |
| --- | --- |
| `POST /demo-api/runs` | Creates the cookie-scoped run; returns its cursor and 60-second query / 180-second search-plus-actions budgets. |
| `POST /runs/{id}/plan` | `{broaden:false}` → real agent query, reason, opaque `plan_id`, `round_id`, and query timing. Display this before search. |
| `POST /runs/{id}/search` | `{plan_id}` → ranked candidates, first three compatible entries in `queue`, and the first `execution` attempt. |
| `POST /runs/{id}/outcome` | Exact round/action/attempt IDs plus actual playback, duck and companion outcomes. The acknowledgement issues the next attempt, or returns `needs_plan` at an adaptive boundary. |
| `POST /runs/{id}/pause` | Cancels pending planning and invalidates the current attempt; retains completed acknowledgements and the current queue cursor. |
| `POST /runs/{id}/resume` | Retries the interrupted clip from its beginning with a fresh attempt ID. Cancelled planning or an expired queue returns `needs_plan`. |
| `POST /runs/{id}/adaptive` | `{adaptive:boolean}` changes the boundary policy only. |
| `POST /runs/{id}/replay` | Returns the full recorded round with fresh clip capabilities and attempts; runs once, then pauses. No agent/search call and no replay outcome enters live history. |

All route paths above have the `/demo-api` prefix. Successful search replies retain the existing `SearchResult` fields and add `run_id`, `round_id`, `round`, `pass`, `adaptive`, `run_status`, `queue:[{action_id,candidate,role_plan}]`, `execution:{action_id,attempt_id}`, and `timings`. Plans and search replies include `scenario:{id,label,animal,behavior_hint,interaction,description,interaction_partner}`. Cursor replies use `status: ready|needs_plan|paused`; search replies keep their search status separately from `run_status`. Fixed queue wraps increment `pass` while retaining the round; a new search increments `round`.

Only one attempt is authorized at a time. Send its actual outcome once playback, companion animation and duck physics finish; the server never drives the simulator. Retrying the identical acknowledged outcome returns the same acknowledgement without advancing again. Conflicting or stale outcomes fail. Stop/reset must also abort frontend work and ignore late responses. A paused run cannot plan until explicitly resumed. Capture completed physics telemetry before beginning the next approach.

The backend preserves original archive ranks and selects the first three compatible active actions, skipping unavailable clips. It sends only deterministic-eligible captions to one compact batch planner, which may assign exact caption-grounded companion roles in the same decision. Solitary footage leaves the companion unassigned. Both toggle positions use the same query schema, model, top-15 retrieval, evidence checks and batch call. A normal round uses two agent decisions and one archive search; an all-blocked result skips the batch decision and pauses. There are no hidden retries or per-clip agent calls. A broader search is an explicit user retry.

`timings.query_agent_ms`, `timings.vss_search_ms`, and `timings.action_agent_ms` separate agent latency from archive latency. Replay reports zero new phase timings and retains `original_timings`. The original intent and up to nine actual acknowledged outcomes guide later queries. Recent live clip identities are retained privately to avoid immediate adaptive repetition. Display a cut video's time from zero; add `provenance.segment_start_sec` only for its archive timestamp.

For one production page, set `RANGER_STATIC_DIR` to the frontend's existing build directory. The backend serves its `index.html` and assets at `/`; no frontend build or modification is performed here.

## Local archive configuration

Required configuration names: `INGRESS_URL`, `USERNAME`, `PASSWORD`. The backend automatically reads `.env` in this backend directory, regardless of the working directory. Exported environment variables take precedence, including empty values. Set `RANGER_ENV_FILE` to an existing absolute file path to explicitly share one private config across checkouts. The app and exporter use the same loader; an invalid explicit path fails instead of silently falling back. It does not source shell files or search other directories for configuration.

For local setup, copy `example.env` to `.env` in this directory, set `INGRESS_URL` to the full URL including `https://`, and fill in `USERNAME` and `PASSWORD` privately. `.env` is ignored by Git; keep real values out of `example.env`. Quote values containing spaces or `#`; `${...}` is treated literally. Restart the backend after changing `.env`. Use the configured archive service directly from this Mac; local startup does not require a VM backend.

The demo backend and Codex CLI run on the same Mac. Use `codex login` to
complete ChatGPT OAuth if needed, then `codex login status` to check it. The
application uses the existing login and does not read/copy OAuth tokens. Keep
VSS credentials in the ignored backend `.env`; no SSH agent bridge is used.

Search uses the authenticated user's existing VSS ACL scope. Deer scenarios retain the observed `wildlife` tag; cat scenarios use `tags: ["meow-10k", "cat-behavior"]` for the requested cat library. It does not guess metadata filters. The deployed VSS schema rejects `llm_top_n: 0`; this backend explicitly requests `llm_top_n: 1` and discards synthesis. The agent adds one query decision and one batched action-planning decision; VSS search still has its own deadline. Call it **Live search**, not synthesis-free search. Its actual duration is returned as `elapsed_ms`; any timeout is an error, never an automatic replay.

Replay uses the last successful round in the current run and is labeled explicitly. Missing or expired snapshots return 409. Snapshots are memory-only; replayed video still streams from VSS. `broaden: true` relaxes the requested behavior while retaining species and both interaction/solitary query branches.

## Interaction evidence and optional human review

The shipped `references.empty.json` contains zero human reviews. Live captions can enable bounded actions with `action_basis: "video_caption"`, `review_status: "unreviewed"`, and `eligibility_reason: "caption_behavior_match"`. `inferred_behavior`, `interaction_partner`, and `action_reason` explain what is copied and where the motion is approximate. `interaction_partner` is null for solitary footage; it is not inferred from the search query. The original hissing approximation is a standing hold, so a hiss-only clip no longer qualifies. A separately supported active behavior in the clip may qualify; the duck does not synthesize a hiss. A caption action's opaque evidence ID binds its exact source, parent, interval, and original caption hash. It does not expose source identities.

The classifier rejects incomplete provenance, absent or wrong species, unsupported behavior, and local negation or uncertainty. Single-animal feeding, walking, sitting and explicit vertical head motion can authorize retrieval-selected approximations. Standing, watching, head scanning and hiss-only poses are excluded from action selection. Pair-specific labels still require evidence of a pair. The underlying controller mapping for watching is `head_scan`, which is now excluded from retrieval selection; explicit shared-object attention and focal behavior receive their own labels. Parallel toy attention is never mislabeled as greeting or hissing. Unambiguous animal pronouns can resolve to a companion only when a pair is established and there is no competing object referent. Presence alone does not authorize a movement. Returned behavior can differ from the selected encounter; the UI displays the actual inference. These are caption-derived approximations, not learned imitation or a claim of visual review.

The controller inventory still contains six primitives. Retrieval selection in both modes excludes `head_scan` and `stand_hold`, including passive exact reviews. The active-only classifier prefers `short_walk`, `ground_pick`, `head_nod`, then `sit_cycle`, even when the active behavior appears later in the caption. A caption describing looking plus sitting can still supply `sit_cycle`; it is not discarded merely because looking appears first. Semantic specificity breaks ties within a primitive. It binds the predicate to the selected animal; a moving toy or a walking person cannot supply the animal's motion. An ambiguous pronoun stays conservative. This preference selects the action for one clip; it never reranks archive results or changes the first-three-compatible rule. An exact human review remains authoritative even when its caption also mentions a more active behavior.

An optional exact human review authorizes its supported behavior without requiring a partner. Previously reviewed solitary feeding footage is valid again when its source, parent, interval, caption hash, species, and behavior still match. Optional `interaction_partner` and `interaction_evidence` can describe a reviewed interaction but are not needed for a solitary pose. A stale, invalid, unsupported, or wrong-species review blocks action instead of silently falling back to inference. No downloaded/private footage or real source identities belong in Git.

Store a raw VSS search JSON response in a private file **outside the repo**, then prepare a draft:

```bash
.venv/bin/python -m ranger_duck.review draft --input /tmp/ranger-search.json --output /tmp/ranger-references.json
```

The input must contain `results[]` with exact segment fields `source`, `original_video`, `reasoning_content`, `segment_start_sec`, and `segment_end_sec`. The local experiment query summaries and browser API responses are not raw VSS response files. Drafts are unreviewed and written with owner-only permissions; the command prints only counts.

Watch the corresponding actual segment through the authorized VSS UI or demo playback. Only after verifying its animal and visible behavior:

```bash
.venv/bin/python -m ranger_duck.review approve \
  --manifest /tmp/ranger-references.json --index 0 \
  --evidence-id reference-01 --animal deer --behavior feeding \
  --interaction-partner deer \
  --interaction-evidence 'Two deer graze together side by side.' \
  --source-label 'Reviewed feeding example' --confirm-viewed
.venv/bin/python -m ranger_duck.review validate --manifest /tmp/ranger-references.json
export RANGER_REFERENCE_MANIFEST=/tmp/ranger-references.json
```

Restart the service to load the manifest. The CLI does not watch clips or infer labels. `--confirm-viewed` records the operator's explicit confirmation; it is not machine verification.

Each review binds the **exact** segment source, parent identity, start/end, and SHA-256 of the original caption. A replaced source, changed caption, incomplete timing, duplicate match, unsupported behavior, or species mismatch disables imitation. A review cannot add a result absent from the current live search. The explicit review evidence is interpreted independently of the scenario's behavior hint. Write the review description only after verifying the actual footage; the sample text above is a format example.

The review CLI retains these pose labels:

| Reviewed behavior | Primitive | Cancellation ceiling |
| --- | --- | --- |
| `feeding` | `ground_pick` | 8000 ms |
| `walking` | `short_walk` | 2000 ms |
| `standing` | `stand_hold` | 3000 ms |

Caption interpretation supports these six primitives:

| Primitive | Caption evidence | Cancellation ceiling |
| --- | --- | --- |
| `short_walk` | Explicit walking, following, approach, or supported social-play movement | 2000 ms |
| `ground_pick` | Feeding or foraging; shared feeding receives a separate label | 8000 ms |
| `head_nod` | Explicit nodding or vertical head raise/lower/dip (`focal_head_nod`) | 2400 ms |
| `head_scan` | Head orientation or an attentive watching approximation | 2400 ms |
| `sit_cycle` | Explicit sitting, seated posture, or sitting down (`focal_sitting`); sit briefly and stand again | 6000 ms |
| `stand_hold` | Standing, still alert posture, or a hissing boundary-pause approximation | 3000 ms |

Sitting does not imply lying down, and merely looking up remains a head-attention approximation unless vertical head movement is explicit. The tested policy cannot reliably walk backward: retreat itself never becomes a forward walk or a still pause. A clip containing retreat may still supply a separately described supported motion; otherwise it remains ineligible with reason `unsupported_retreat`. Unsupported jumping, lying, fighting, biting, and contact do not become motions. A ceiling is not evidence of completion. The frontend observes the controller's actual completion and recovery.

## Configuration and limits

| Variable | Default / meaning |
| --- | --- |
| `RANGER_REFERENCE_MANIFEST` | Unset: empty reviews. Invalid file fails closed with a warning. |
| `RANGER_STATIC_DIR` | Unset: API only. Existing frontend build directory if set. |
| `RANGER_SEARCH_TIMEOUT_SEC` | 30 seconds for login/refresh/search combined; allowed 1–60. Search response reads use this budget rather than the shorter generic read timeout. |
| `RANGER_REQUEST_TIMEOUT_SEC` | 10 seconds for connection, write, pool, authentication, and video reads; allowed 1–30. |
| `RANGER_CLIP_TTL_SEC` | 1800 seconds; allowed 30–7200. |
| `RANGER_SECURE_COOKIE` | `false` for local forwarded HTTP; set `true` for HTTPS hosting. |

Health returns `search_timeout_ms` so the browser waits for the configured backend budget plus five seconds of connection/proxy grace. This avoids the earlier 10-second upstream read and 13-second browser abort cutting off valid slower searches. The timer still displays actual elapsed time, and the overall backend deadline remains enforced.

Up to 15 distinct segment results are returned in original upstream order. `rank` preserves the original 1-based index even when a duplicate or invalid source is omitted. There is no parent diversity reranking. Any compatible action contributes to response `status: "ok"`; the frontend takes the first three compatible results after filtering the whole returned set. For example, eligible archive ranks 4, 7, 13, and 15 yield three displayed action slots backed by ranks 4, 7, and 13.

At most 256 browser sessions and 60 clip capabilities per session are held. Each retained run protects only its selected queue (at most three capabilities, 24 across eight runs) from capacity eviction by other tabs. New rounds replace that protection; retirement and capability expiry release it. Cookies are HttpOnly/SameSite and IDs are opaque. A different session, expiration, restart, or capacity eviction of an unselected clip yields the same `404 clip_not_found`. Search again to refresh access.

Video requests accept one standard byte range. The proxy forwards `Range`/`If-Range`, supports GET and HEAD, and preserves 206/416 plus range headers. If upstream HEAD is unsupported, it opens a streaming GET and closes after headers without reading the body. No arbitrary URL proxy, upstream redirect, presigned link, or JWT is sent to the browser. A failure after streaming begins interrupts playback; retrying/researching is the UI recovery.

## Capture search, Codex decisions, and action outcomes

Normal backend startup records private JSONL events in `backend/.captures/`
(override with `RANGER_CAPTURE_DIR`). Restart the backend and rebuild/reload the
frontend after installing this change. Files are owner-only and ignored by Git.
Each event has a timestamp, event ID and run ID linking:

- The complete VSS search response, before filtering, normalization, deduplication
  or selection. This includes every returned hit and its original source, caption,
  score, segment times and other returned fields; it does not download video bytes.
- Codex instructions, context, output schema, raw final output, validated decision
  and returned explanation. Private internal reasoning is not available.
- Unified run action issuance and validated browser-reported outcomes, including
  round/attempt IDs, simulator state, playback and companion status. Fixed and
  adaptive runs share the same capture path; replay outcomes are labelled.
  Pausing an issued attempt without a report records an unknown outcome, not
  completion. Legacy encounter and loop endpoints retain their capture events.

Credentials, bearer tokens and signed URL query strings are stripped before
writing. Stable video source paths remain private training provenance. Capture
does not sample or truncate search hits/captions. `/demo-api/health` exposes
`capture_enabled` and `capture_write_failed`; a disk failure is also logged
without payloads. Unified runs stop issuing actions if capture storage fails;
outcomes must be saved before acknowledgement.

To send captures to W&B Weave, create a team-only project, set
`RANGER_WEAVE_PROJECT=ENTITY/PROJECT` and `WANDB_API_KEY` privately in the backend
`.env` (or use an existing SDK login). Start the app and exporter together so both restart from the same saved configuration:

```bash
.venv/bin/python -m pip install -e '.[capture]'
.venv/bin/ranger-duck-serve --port 18000
```

For another checkout, use `ranger-duck-serve --env-file /absolute/path/to/backend/.env`. The startup log prints the selected file path, never its values. Secrets stay outside Git and are not copied into future worktrees. Install `.[capture]` in each checkout's Python environment. Captures remain local to the running checkout unless `RANGER_CAPTURE_DIR` is explicitly set.

For a separately managed backend, run `ranger-duck-export-captures --follow` alongside it; do not also use the combined launcher. Omit `--follow` for a one-time export. The exporter reads the same `.env`, uploads
pending events, and verifies their event IDs by reading them back from Weave.
Private per-project acknowledgement files let subsequent runs skip confirmed
events. Stop the exporter before starting another against the same directory.
The continuous exporter also retries initialization failures after restart. An interrupted upload may create a duplicate remote call; `event_id` is the
deduplication key. Use `run_id` to group decisions, results and outcomes in Weave.
Original event time and elapsed duration are retained as attributes; the Weave
call itself is created at export time. Local files remain the durable copy when
W&B is unavailable. This adds capture only, with no labelling or training job.

## Verify

```bash
.venv/bin/python -m pytest -q
```

Tests use fabricated upstream responses. They cover authentication caching/refresh, bounded timeouts, error redaction, live-only results, exact review binding and staleness, rank preservation, species and interaction grounding, negation, session isolation/expiry, ranges, HEAD, redirect rejection, and no-config startup. They do not establish the accuracy of a live video-model caption. Live playback remains the way to inspect the actual evidence.

On 17 October 2026, all 163 backend tests passed after active-caption preference and the sitting/nodding additions. They cover later-rank selection, solitary behaviors, original rank preservation, exact legacy reviews, wrong actors/species, negation, provenance, and active behavior appearing after a still pose. Earlier live smoke tests established a session, returned 15 search candidates, replayed the same recorded result, and streamed 32 video bytes with status 206 and `video/mp4`. HEAD returned 200 with no body; an invalid range returned 416; another session could not access the clip (404). These checks do not replace visual footage review.

## Local agent decisions

The unified run pipeline uses a locally installed Codex CLI with the presenter's existing ChatGPT OAuth login. No OpenAI API key is required. The CLI must support `exec --ignore-user-config --ephemeral --output-schema`; see the [official CLI reference](https://developers.openai.com/codex/cli/reference).

The first query uses the selected animal, encounter and optional original intent. Later adaptive rounds use that same intent plus real acknowledged outcomes. The structured decision requires both a same-species interaction branch and a similar solitary-behavior branch; the server validates each species scope and joins them with `OR`. Query generation is identical with Loop ON or OFF. Requested actions and failed attempts are never presented as observed successes.

`loop_agent.py` remains the shared CLI runner. It runs ephemeral structured decisions using `gpt-6-luna` and forced ChatGPT sign-in, disables shell tools/apps/web/hooks/multi-agent tools, and does not load user custom config. Workshop credentials and API-key environment variables are excluded. Source URIs and video tokens never enter agent context. At most two decisions run concurrently across sessions.

Health reports executable availability, not a successful inference probe. Missing login, incompatible CLI or unavailable model returns `agent_failed`. The application never installs Codex or modifies login/configuration. Pause/reset cancels pending work, including the CLI child process.

Legacy `/encounter-plan`, `/search`, and `/loop` routes remain for compatibility. The single-page frontend uses only `/runs`; the legacy standalone Loop selector is not a second agent path for the new page. The shared run service reuses Encounter query/action validation, adding bounded optional role plans, session history, ordered execution attempts, and idempotent outcomes.
