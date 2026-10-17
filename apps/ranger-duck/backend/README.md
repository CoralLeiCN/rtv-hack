# Ranger Duck backend

A read-only FastAPI service for the single-page wildlife encounter demo. The frontend and Microduck simulator are built separately; this directory contains no frontend code. The shared [API contract](../../../docs/RANGER_DUCK_API.md) is the integration reference.

The local service asks the signed-in Codex CLI to generate a query for the selected animal's interactions or similar individual behavior, retrieves ranked VSS clips, and asks the agent to plan bounded actions from their captions or exact reviews. It returns redacted references and proxies segment playback. A deterministic classifier requires the selected species and a supported visible behavior; returned footage may contain a solitary animal. The requested scenario never supplies a missing action. It never trains, uploads, re-ingests, deploys, or changes the shared pipeline.

## Run locally without VSS configuration

Python 3.11 or newer:

```bash
cd apps/ranger-duck/backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m uvicorn ranger_duck.app:app --host 127.0.0.1 --port 8000 --workers 1
```

`GET /demo-api/health` and `GET /demo-api/encounters` work immediately. Search returns `503 live_not_configured` until the backend has all three required environment variables. No mock data masquerades as live results.

Use **one worker**: session capabilities and authentication cache live in memory. Restarting invalidates clip URLs. This is a local workshop service; keep it on loopback or behind your authenticated workshop access.

## Connect the frontend

Use relative `/demo-api` URLs. During frontend development, proxy `/demo-api` to `http://127.0.0.1:8000`, including cookies, `Range`, and `If-Range`. Browser search requests and video URLs must use the frontend origin. This avoids CORS and credential exposure.

```js
// Await health once before allowing Start; it establishes the playback session.
await fetch('/demo-api/health').then(r => r.json());
const catalog = await fetch('/demo-api/encounters').then(r => r.json());
const response = await fetch('/demo-api/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ encounter_id: crypto.randomUUID(), scenario_id: catalog.encounters[0].id })
});
const result = await response.json();
// Check response.ok; only successful responses contain candidates.
```

Await the health bootstrap before enabling Start, so overlapping searches share one session cookie even if responses finish out of order. Keep the encounter ID when starting a request and ignore responses after Reset changes it. The frontend filters all returned candidates for compatible actions, then displays and loops the first three in retrieval order. Unsupported candidates do not occupy slots; `candidate.rank` retains the original archive rank for transparency. Pass each returned primitive to the simulator adapter and await its actual completion. The backend never starts robot movements. Display a cut video's time from zero; add `provenance.segment_start_sec` only for the archive timestamp.

For one production page, set `RANGER_STATIC_DIR` to the frontend's existing build directory. The backend serves its `index.html` and assets at `/`; no frontend build or modification is performed here.

## Local archive configuration

Required configuration names: `INGRESS_URL`, `USERNAME`, `PASSWORD`. The backend automatically reads `.env` in this backend directory, regardless of the working directory. Exported environment variables take precedence, including empty values. It does not source shell files or search other directories for configuration.

For local setup, copy `example.env` to `.env` in this directory, set `INGRESS_URL` to the full URL including `https://`, and fill in `USERNAME` and `PASSWORD` privately. `.env` is ignored by Git; keep real values out of `example.env`. Quote values containing spaces or `#`; `${...}` is treated literally. Restart the backend after changing `.env`. Use the configured archive service directly from this Mac; local startup does not require a VM backend.

The demo backend and Codex CLI run on the same Mac. Use `codex login` to
complete ChatGPT OAuth if needed, then `codex login status` to check it. The
application uses the existing login and does not read/copy OAuth tokens. Keep
VSS credentials in the ignored backend `.env`; no SSH agent bridge is used.

Search uses the authenticated user's existing VSS ACL scope. Deer scenarios retain the observed `wildlife` tag; cat scenarios use `tags: ["meow-10k", "cat-behavior"]` for the requested cat library. It does not guess metadata filters. The deployed VSS schema rejects `llm_top_n: 0`; this backend explicitly requests `llm_top_n: 1` and discards synthesis. The agent adds one query decision and one batched action-planning decision; VSS search still has its own deadline. Call it **Live search**, not synthesis-free search. Its actual duration is returned as `elapsed_ms`; any timeout is an error, never an automatic replay.

The design's explicit Replay control sends `mode: "replay"` to the same route. It returns the last successful live result for that session, scenario, and `broaden` setting, with a visible replay mode, original timing, and recording timestamp. Missing/expired snapshots return 409. Search snapshots are memory-only and expire with the configured TTL; replayed video still streams from VSS. `broaden: true` relaxes the requested behavior while retaining the species and permitting interactions or similar solitary motion.

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

At most 256 browser sessions and 60 clip capabilities per session are held. Cookies are HttpOnly/SameSite and IDs are opaque. A different session, expiration, restart, or capacity eviction yields the same `404 clip_not_found`. Search again to refresh access.

Video requests accept one standard byte range. The proxy forwards `Range`/`If-Range`, supports GET and HEAD, and preserves 206/416 plus range headers. If upstream HEAD is unsupported, it opens a streaming GET and closes after headers without reading the body. No arbitrary URL proxy, upstream redirect, presigned link, or JWT is sent to the browser. A failure after streaming begins interrupts playback; retrying/researching is the UI recovery.

## Verify

```bash
.venv/bin/python -m pytest -q
```

Tests use fabricated upstream responses. They cover authentication caching/refresh, bounded timeouts, error redaction, live-only results, exact review binding and staleness, rank preservation, species and interaction grounding, negation, session isolation/expiry, ranges, HEAD, redirect rejection, and no-config startup. They do not establish the accuracy of a live video-model caption. Live playback remains the way to inspect the actual evidence.

On 17 October 2026, all 163 backend tests passed after active-caption preference and the sitting/nodding additions. They cover later-rank selection, solitary behaviors, original rank preservation, exact legacy reviews, wrong actors/species, negation, provenance, and active behavior appearing after a still pose. Earlier live smoke tests established a session, returned 15 search candidates, replayed the same recorded result, and streamed 32 video bytes with status 206 and `video/mp4`. HEAD returned 200 with no body; an invalid range returned 416; another session could not access the clip (404). These checks do not replace visual footage review.

## Local agent decisions

Both Encounter and Agent Loop modes use a locally installed Codex CLI with the
presenter's existing ChatGPT OAuth login. No OpenAI API key is required. The
CLI must support `exec --ignore-user-config --ephemeral --output-schema`; see
the [official CLI reference](https://developers.openai.com/codex/cli/reference).

Encounter mode first calls `POST /demo-api/encounter-plan`. The returned query
and reason are shown before `/demo-api/search` uses its session-scoped
`plan_id`. Calling search without a plan remains supported and generates one
internally. Queries request interactions **or similar individual behavior** of
the selected species. The structured decision requires both an interaction branch and a similar solitary-behavior branch; the server validates both species scopes and joins them with `OR`. After retrieval, one batched agent decision proposes
actions for up to 15 clips. The backend validates exact caption excerpts,
selected species, supported behavior, review/provenance vetoes and primitive
limits. It keeps archive order; the frontend takes the first three compatible
actions. Replay reuses recorded decisions without another agent call.

`loop_agent.py` runs ephemeral structured decisions in temporary directories
using `gpt-6-luna` and forced ChatGPT sign-in. It disables shell tools, apps,
web search, hooks and multi-agent tools, and does not load user custom config.
Workshop credentials and API-key environment variables are excluded. Source
URIs and video tokens never enter the agent context.

Health reports executable availability, not a successful paid inference probe.
Missing login, incompatible CLI or unavailable model returns `agent_failed`.
Query planning is limited to 60 seconds; search plus action planning and each
Loop cycle have a 180-second ceiling. At most two Codex decisions run at once.
Stop/reset cancel pending work, including the CLI child process. The application
does not install Codex or modify its login/configuration.

Agent Loop mode adds context from actual playback and controller outcomes to
the next query. Paired captions can assign two grounded roles; single-animal
clips can supply a supported duck behavior without inventing a second observed
animal. See the [Loop contract](../../../docs/RANGER_DUCK_API.md#additional-agent-loop-mode).

Both Encounter and Loop exclude passive scan/hold actions before selecting references. With no active supported result, the service reports that state (Loop may try a bounded broader query); it never fabricates an active action or falls back to a neutral hold.
