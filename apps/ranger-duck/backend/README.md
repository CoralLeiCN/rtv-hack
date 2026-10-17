# Ranger Duck backend

A read-only FastAPI service for the single-page wildlife encounter demo. The frontend and Microduck simulator are built separately; this directory contains no frontend code. The shared [API contract](../../../docs/RANGER_DUCK_API.md) is the integration reference.

The service turns an animal–duck encounter into a live species-pair VSS search, returns redacted video references, and proxies segment playback. Bounded imitation actions come from each returned video's existing model caption or an exact human review. A deterministic classifier requires the selected species and a supported visible behavior; returned footage may contain a solitary animal. The requested scenario never supplies a missing action. It never trains, uploads, re-ingests, deploys, or changes the shared pipeline.

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

## Live VM startup

Required configuration names: `INGRESS_URL`, `USERNAME`, `PASSWORD`. The backend automatically reads `.env` in this backend directory, regardless of the working directory. Exported environment variables take precedence, including empty values. It does not source shell files or search other directories for configuration.

For local setup, copy `example.env` to `.env` in this directory, set `INGRESS_URL` to the full URL including `https://`, and fill in `USERNAME` and `PASSWORD` privately. `.env` is ignored by Git; keep real values out of `example.env`. Quote values containing spaces or `#`; `${...}` is treated literally. Restart the backend after changing `.env`. Alternatively, continue loading the VM's existing `/config/*.config` into Bash as shown below.

The checked workshop VM has Python 3.12 but lacks pip and the venv bootstrap package. If the ordinary venv setup above fails there, install dependencies into a private temporary directory without changing system packages. From this backend directory:

```bash
RANGER_RUNTIME_DIR="$(mktemp -d /tmp/ranger-duck-runtime.XXXXXX)"
curl -fsSL https://bootstrap.pypa.io/pip/pip.pyz -o "$RANGER_RUNTIME_DIR/pip.pyz"
python3 "$RANGER_RUNTIME_DIR/pip.pyz" install --quiet --target "$RANGER_RUNTIME_DIR/deps" .
export PYTHONPATH="$RANGER_RUNTIME_DIR/deps${PYTHONPATH:+:$PYTHONPATH}"
```

For this setup, use `python3` in place of `.venv/bin/python` in the startup command below and keep the same shell session. The temporary directory lasts only until VM cleanup; repeat setup when it is removed.

If the VM has exactly one existing team configuration, run these commands in **Bash 4+**, not zsh:

```bash
mapfile -t RANGER_CONFIG_FILES < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
(( ${#RANGER_CONFIG_FILES[@]} == 1 )) || { echo 'Expected exactly one workshop configuration'; exit 1; }
set -a
source "${RANGER_CONFIG_FILES[0]}" >/dev/null
set +a
.venv/bin/python -m uvicorn ranger_duck.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Forward the VM port through the team's existing SSH connection. If frontend development runs on your laptop, point its proxy at that forwarded backend port. Never put VSS credentials or tokens into frontend settings, browser URLs, tracked `.env` files, or logs.

Search uses the authenticated user's existing VSS ACL scope. Deer scenarios retain the observed `wildlife` tag; cat scenarios use `tags: []` to include domestic cats in the authorized archive. It does not guess metadata filters. The deployed VSS schema rejects `llm_top_n: 0`; this backend explicitly requests `llm_top_n: 1` and discards synthesis. Caption interpretation adds no model calls. Call it **Live search**, not synthesis-free search. Its actual duration is returned as `elapsed_ms`; any timeout is an error, never an automatic replay.

The design's explicit Replay control sends `mode: "replay"` to the same route. It returns the last successful live result for that session, scenario, and `broaden` setting, with a visible replay mode, original timing, and recording timestamp. Missing/expired snapshots return 409. Search snapshots are memory-only and expire with the configured TTL; replayed video still streams from VSS. `broaden: true` relaxes the requested behavior but keeps the same species pair: two cats interacting or two deer interacting.

## Interaction evidence and optional human review

The shipped `references.empty.json` contains zero human reviews. Live captions can enable bounded actions with `action_basis: "video_caption"`, `review_status: "unreviewed"`, and `eligibility_reason: "caption_behavior_match"`. `inferred_behavior`, `interaction_partner`, and `action_reason` explain what is copied and where the motion is approximate. `interaction_partner` is null for solitary footage; it is not inferred from the search query. Hissing maps to a still boundary pause; the duck does not synthesize a hiss. A caption action's opaque evidence ID binds its exact source, parent, interval, and original caption hash. It does not expose source identities.

The classifier rejects incomplete provenance, absent or wrong species, unsupported behavior, and local negation or uncertainty. Single-animal feeding, walking, standing, sitting, head movement, watching, and hissing can authorize supported approximations. Pair-specific labels still require evidence of a pair. Watching maps to an attentive `head_scan` approximation; explicit shared-object attention and focal behavior receive their own labels. Parallel toy attention is never mislabeled as greeting or hissing. Unambiguous animal pronouns can resolve to a companion only when a pair is established and there is no competing object referent. Presence alone does not authorize a movement. Returned behavior can differ from the selected encounter; the UI displays the actual inference. These are caption-derived approximations, not learned imitation or a claim of visual review.

Within each caption, the classifier prefers an active supported behavior over a still pose, even when the active behavior appears in a later sentence: `short_walk`, `ground_pick`, `head_nod`, `head_scan`, `sit_cycle`, then `stand_hold`. Semantic specificity breaks ties within a primitive. It binds the predicate to the selected animal; a moving toy or a walking person cannot supply the animal's motion. An ambiguous pronoun stays conservative. This preference selects the action for one clip; it never reranks archive results or changes the first-three-compatible rule. An exact human review remains authoritative even when its caption also mentions a more active behavior.

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

## Agent Loop mode

The additional Agent Loop mode uses a Codex CLI installed on the backend host,
with that OS user's existing Codex login. Run `codex login` interactively there
if needed; do not paste credentials into chat or configuration files. The CLI
must support `exec --ignore-user-config --ephemeral --output-schema` (see the
[official CLI reference](https://developers.openai.com/codex/cli/reference)).
No OpenAI API key is required by this integration.

`loop_agent.py` makes ephemeral structured decisions in temporary directories:
first a query, then a selected clip and supported response after the backend
performs retrieval. It uses read-only execution, disables shell tools, apps,
web search, hooks, and multi-agent tools, and does not load the user's custom
config. Both query and response decisions explicitly use `gpt-6-luna` via
`--model`; there is no automatic model fallback. Workshop credentials and API-key
environment variables are not passed to the subprocess. The backend validates
all returned decisions; the agent never receives source URIs or video tokens.

Health reports executable availability only. A missing login, incompatible CLI,
or unavailable model service returns a safe `agent_failed` error on the first
cycle. The overall cycle deadline is 180 seconds, including waiting for one of
two agent-process slots. Stopping a session cancels the active decision process.
The application does not install Codex or modify its login/configuration.

See the [loop API contract](../../../docs/RANGER_DUCK_API.md#additional-agent-loop-mode)
for session operations, response rules, telemetry, and retry limits. Existing
encounter search/replay behavior is unchanged.
