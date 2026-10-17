# Ranger Duck backend

A read-only FastAPI service for the single-page wildlife encounter demo. The frontend and Microduck simulator are built separately; this directory contains no frontend code. The shared [API contract](../../../docs/RANGER_DUCK_API.md) is the integration reference.

The service turns an encounter into a live VSS search, returns redacted video references, and proxies selected segment playback. A local reviewed manifest is the only authority for imitation actions. It never trains, uploads, re-ingests, deploys, or changes the shared pipeline.

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

Await the health bootstrap before enabling Start, so overlapping searches share one session cookie even if responses finish out of order. Keep the encounter ID when starting a request and ignore responses after Reset changes it. Copy is enabled only for a selected non-null `candidate.action`. Pass the returned primitive to the frontend's simulator adapter. The backend never starts robot movements. Display a cut video's time from zero; add `provenance.segment_start_sec` only for the archive timestamp.

For one production page, set `RANGER_STATIC_DIR` to the frontend's existing build directory. The backend serves its `index.html` and assets at `/`; no frontend build or modification is performed here.

## Live VM startup

Required environment variable names: `INGRESS_URL`, `USERNAME`, `PASSWORD`. They must already be available in the configured workshop environment. The backend does not discover config files or source shell files itself.

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

Search uses the authenticated user's existing VSS ACL scope and the observed `wildlife` tag. It does not guess metadata filters. The deployed VSS schema rejects `llm_top_n: 0`; this backend explicitly requests `llm_top_n: 1` and discards synthesis. Call it **Live search**, not synthesis-free search. Its actual duration is returned as `elapsed_ms`; any timeout is an error, never an automatic replay.

The design's explicit Replay control sends `mode: "replay"` to the same route. It returns the last successful live result for that session, scenario, and `broaden` setting, with a visible replay mode, original timing, and recording timestamp. Missing/expired snapshots return 409. Search snapshots are memory-only and expire with the configured TTL; replayed video still streams from VSS. `broaden: true` searches for a hoofed animal instead of deer while preserving the same reviewed-species requirement for imitation.

## Review actual evidence before enabling Copy

The shipped `references.empty.json` contains zero reviewed references. Live clips remain playable, but every action is null until somebody watches actual footage and records a review. No downloaded/private footage or real source identities belong in Git.

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
  --source-label 'Reviewed feeding example' --confirm-viewed
.venv/bin/python -m ranger_duck.review validate --manifest /tmp/ranger-references.json
export RANGER_REFERENCE_MANIFEST=/tmp/ranger-references.json
```

Restart the service to load the manifest. The CLI does not watch clips or infer labels. `--confirm-viewed` records the operator's explicit confirmation; it is not machine verification.

Each review binds the **exact** segment source, parent identity, start/end, and SHA-256 of the original caption. A replaced source, changed caption, incomplete timing, duplicate match, unsupported behavior, or species mismatch disables imitation. A review cannot add a result absent from the current live search. Reviewed behavior selects the action independently of the scenario's behavior hint.

Supported behavior mappings:

| Reviewed behavior | Primitive | Cancellation ceiling |
| --- | --- | --- |
| `feeding` | `ground_pick` | 8000 ms |
| `walking` | `short_walk` | 2000 ms |
| `standing` | `stand_hold` | 3000 ms |

Resting/sit and looking-around/head-scan remain future capabilities and are not authorized by this release. A ceiling is not evidence of completion. The frontend observes the controller's actual completion and recovery.

## Configuration and limits

| Variable | Default / meaning |
| --- | --- |
| `RANGER_REFERENCE_MANIFEST` | Unset: empty reviews. Invalid file fails closed with a warning. |
| `RANGER_STATIC_DIR` | Unset: API only. Existing frontend build directory if set. |
| `RANGER_SEARCH_TIMEOUT_SEC` | 12 seconds for login/refresh/search combined; allowed 1–60. |
| `RANGER_REQUEST_TIMEOUT_SEC` | 10 seconds per upstream network operation; allowed 1–30. |
| `RANGER_CLIP_TTL_SEC` | 1800 seconds; allowed 30–7200. |
| `RANGER_SECURE_COOKIE` | `false` for local forwarded HTTP; set `true` for HTTPS hosting. |

Up to 15 distinct segment results are returned, with one per parent placed before repeat-parent hits. Later candidates are preserved because they may contain a reviewed reference. UI cards can initially show three while allowing selection of later reviewed candidates.

At most 256 browser sessions and 60 clip capabilities per session are held. Cookies are HttpOnly/SameSite and IDs are opaque. A different session, expiration, restart, or capacity eviction yields the same `404 clip_not_found`. Search again to refresh access.

Video requests accept one standard byte range. The proxy forwards `Range`/`If-Range`, supports GET and HEAD, and preserves 206/416 plus range headers. If upstream HEAD is unsupported, it opens a streaming GET and closes after headers without reading the body. No arbitrary URL proxy, upstream redirect, presigned link, or JWT is sent to the browser. A failure after streaming begins interrupts playback; retrying/researching is the UI recovery.

## Verify

```bash
.venv/bin/python -m pytest -q
```

Tests use fabricated upstream responses. They cover authentication caching/refresh, bounded timeouts, error redaction, live-only results, exact review binding and staleness, normalization, session isolation/expiry, ranges, HEAD, redirect rejection, and no-config startup. They do not establish that current wildlife footage supports the demo. Live playback and human reference review remain necessary on the configured VM.

On 17 October 2026, all 41 backend tests passed. Live smoke tests on the configured VM established a session, returned 15 search candidates, replayed the same recorded result, and streamed 32 video bytes with status 206 and `video/mp4`. HEAD returned 200 with no body; an invalid range returned 416; another session could not access the clip (404). Observed live search times ranged from about 4.5 to 10.1 seconds. The empty manifest correctly kept every action null. These checks do not replace visual footage review.
