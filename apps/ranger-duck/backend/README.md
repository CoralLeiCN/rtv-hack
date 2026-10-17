# Ranger Duck backend

The FastAPI app uses the independent archive for retrieval and playback and the
existing locally authenticated Codex CLI for bounded action decisions. See the
[API contract](../../../docs/RANGER_DUCK_API.md).

## Setup

First follow [archive setup](../../../docs/ARCHIVE.md). From this directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
cp example.env .env
```

Privately set ARCHIVE_URL and ARCHIVE_API_KEY in .env. Run the existing Codex CLI
login flow on the backend host. Start with `.venv/bin/ranger-duck-serve`.
Health and encounter metadata work without the archive; search reports missing
configuration explicitly. Use one worker because session capabilities live in
memory. Restarting invalidates clip URLs. Bind to loopback for local use.

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


## Interaction evidence and optional human review

The shipped `references.empty.json` contains zero human reviews. Live captions can enable bounded actions with `action_basis: "video_caption"`, `review_status: "unreviewed"`, and `eligibility_reason: "caption_behavior_match"`. `inferred_behavior`, `interaction_partner`, and `action_reason` explain what is copied and where the motion is approximate. `interaction_partner` is null for solitary footage; it is not inferred from the search query. The original hissing approximation is a standing hold, so a hiss-only clip no longer qualifies. A separately supported active behavior in the clip may qualify; the duck does not synthesize a hiss. A caption action's opaque evidence ID binds its exact source, parent, interval, and original caption hash. It does not expose source identities.

The classifier rejects incomplete provenance, absent or wrong species, unsupported behavior, and local negation or uncertainty. Single-animal feeding, walking, sitting and explicit vertical head motion can authorize retrieval-selected approximations. Standing, watching, head scanning and hiss-only poses are excluded from action selection. Pair-specific labels still require evidence of a pair. The underlying controller mapping for watching is `head_scan`, which is now excluded from retrieval selection; explicit shared-object attention and focal behavior receive their own labels. Parallel toy attention is never mislabeled as greeting or hissing. Unambiguous animal pronouns can resolve to a companion only when a pair is established and there is no competing object referent. Presence alone does not authorize a movement. Returned behavior can differ from the selected encounter; the UI displays the actual inference. These are caption-derived approximations, not learned imitation or a claim of visual review.

The controller inventory still contains six primitives. Retrieval selection in both modes excludes `head_scan` and `stand_hold`, including passive exact reviews. The active-only classifier prefers `short_walk`, `ground_pick`, `head_nod`, then `sit_cycle`, even when the active behavior appears later in the caption. A caption describing looking plus sitting can still supply `sit_cycle`; it is not discarded merely because looking appears first. Semantic specificity breaks ties within a primitive. It binds the predicate to the selected animal; a moving toy or a walking person cannot supply the animal's motion. An ambiguous pronoun stays conservative. This preference selects the action for one clip; it never reranks archive results or changes the first-three-compatible rule. An exact human review remains authoritative even when its caption also mentions a more active behavior.

An optional exact human review authorizes its supported behavior without requiring a partner. Previously reviewed solitary feeding footage is valid again when its source, parent, interval, caption hash, species, and behavior still match. Optional `interaction_partner` and `interaction_evidence` can describe a reviewed interaction but are not needed for a solitary pose. A stale, invalid, unsupported, or wrong-species review blocks action instead of silently falling back to inference. No downloaded/private footage or real source identities belong in Git.

Store a raw archive search JSON response in a private file **outside the repo**, then prepare a draft:

```bash
.venv/bin/python -m ranger_duck.review draft --input /tmp/ranger-search.json --output /tmp/ranger-references.json
```

The input must contain `results[]` with exact segment fields `source`, `original_video`, `reasoning_content`, `segment_start_sec`, and `segment_end_sec`. The local experiment query summaries and browser API responses are not raw archive response files. Drafts are unreviewed and written with owner-only permissions; the command prints only counts.

Watch the corresponding actual segment through the authorized application playback. Only after verifying its animal and visible behavior:

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

## Capture search, Codex decisions, and action outcomes

Normal backend startup records private JSONL events in `backend/.captures/`
(override with `RANGER_CAPTURE_DIR`). Files are owner-only and ignored by Git.
Each event has a timestamp, event ID and run ID linking:

- The complete archive search response, before filtering, normalization, deduplication
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
writing. Stable video source identities remain private training provenance. Capture
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

## Verification

Run `.venv/bin/python -m pytest tests -q`. Tests use fabricated archive responses
and agent decisions. Full archive integration checks are documented in ARCHIVE.md.
