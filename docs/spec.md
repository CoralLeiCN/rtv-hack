# Specification: web frontend for video search

The Ranger Duck loop below is implemented as an additional mode. Live
Codex/VSS end-to-end verification remains pending. The remaining sections
describe the original search-only implementation; their manual playback and
backend-order requirements apply to that experience, not to agent-directed
selection and automatic playback in Loop mode.

## Ranger Duck Loop mode (additional mode)

Loop mode is additional to the existing encounter mode. Its initial scope is
queries describing two cats or two deer interacting. Return the top 10 archive
results in their original order (or all results when fewer than 10 exist).
The pair is a search preference, not a result eligibility requirement: retain
single animals, weak matches, and unrecognized behaviors.
Both scenes contain one animal model and the duck. Loop mode assigns them the
two video roles; encounter mode keeps direct search and fixed-sequence imitation.

### Interaction flow

1. The user enters a nonblank initial prompt and enables **Loop mode**.
2. The agent searches the existing VSS archive and selects a relevant clip.
3. Codex assigns distinct video subjects to the animal companion and duck,
   quoting caption evidence for each role. It chooses a supported companion
   animation, a duck action approximating the other animal's behavior, and their
   order (`together`, `companion_first`, or `duck_first`). Playback starts both
   roles according to that plan.
4. The simulator reports the movement actually performed, whether it completed,
   and the duck's resulting state. A requested movement or elapsed timer alone
   does not establish completion. Record companion animation completion separately;
   it is scripted animation, not physics telemetry.
5. The agent uses the original prompt, the previous clip's evidence, and the
   simulator's reaction report to generate the next search and select a new clip.
6. Playback, reaction, and agent search repeat while Loop mode remains enabled.

Run one cycle at a time. Wait for the current reaction to finish before asking
the agent for the next search; do not overlap simulator commands or advance on
a presumed reaction. This replaces the fixed result playback sequence for Loop
mode. The separate loop API connects Codex decisions to VSS retrieval and the
simulator; the existing encounter mode continues to use direct VSS search.

### Context and evidence

Keep a bounded, session-local history of recent queries, selected clips, and
actual reactions. Give the agent enough of that history to maintain continuity
and avoid repeatedly selecting the same clips. Preserve the initial prompt as
the user's guiding intent throughout the session.

Choose clips from actual search results. Retain provenance checks and supported
movement limits, and add response-specific eligibility rules for Loop mode.
The original mode's imitation rules remain unchanged. Give Codex all top 10
captions and expose that same list in the Loop panel. Do not require a recognized
behavior, confirmed pair, or confirmed species in each caption. Codex chooses
one clip and maps its two animal roles using the supplied caption and prior
outcome. Role plans require distinct subjects and nonempty exact evidence
excerpts from that caption. This validates provenance, not semantic entailment;
role interpretation remains model-inferred. If either role or a supported
approximation is uncertain, use `insufficient_evidence`: the backend normalizes
the plan to a standing companion and `stand_hold` duck, with an explicit neutral
fallback label. This does not remove the result or claim an observed interaction.
Keep unavailable results in place with an explanation: invalid provenance,
stale/contradictory review, excessive duration, or a recent interval can prevent
execution without removing the result or promoting rank 11. Grounded duck actions
approximate the counterpart role, not an arbitrary response to the scene.
An agent's selection or explanation alone does not bypass validation.

Expose a structured action interface for `stand_hold`, `head_scan`, `short_walk`,
and `ground_pick`, using their existing execution limits. Each command identifies
the clip, cycle, action, allowed parameters, and response rationale. Validate
session/cycle ownership, evidence, parameters, and simulator readiness before
execution. Codex chooses one bounded plan per cycle. Companion animations are
standing, alert, walking, approach, retreat, and feeding; cats additionally support
hissing, greeting, and play. Companion animation lasts at most 3000 ms, with
bounded movement in the clearing. Duck actions retain their existing limits. Validate the declared counterpart
behavior against its primitive: still/stand_hold, looking/head_scan,
moving/short_walk, or feeding/ground_pick.
The next search waits for playback, companion animation, and actual duck
completion. Stop, hidden-tab pause, and mode switches cancel both roles and
prevent the delayed role in a sequential plan from starting.

The initial implementation may use the archive's existing video captions to
interpret clip content. Label that interpretation as inferred and distinguish it
from physical execution. Show the video subjects, supporting excerpts, action
approximations, ordering, and uncertainty. Do not present the generated scene as
visual verification, learned motion, or an exact reconstruction.
Feed the simulator's observed outcome back into the next search, including an
incomplete or failed movement when relevant, rather than inventing a successful
reaction.

### Controls and visible state

- Show a clearly labeled **Loop mode** toggle with its current on/off state.
- Show the original prompt, current search query, selected clip, duck reaction,
  and a concise explanation of why the next query follows from that reaction.
- Distinguish searching, playing/reacting, settling, and paused/error states.
- Turning Loop mode off cancels pending searches, prevents new cycles, and lets
  the duck settle safely. Ignore late responses from a canceled cycle so they
  cannot restart playback or movement.
- Reset clears the interaction history and cancels the current cycle. Replacing
  the initial prompt starts a fresh interaction context rather than mixing old
  responses into the new loop.

Automatic clip playback is part of the user-enabled loop. Handle browser
playback restrictions visibly; do not advance as though blocked playback
succeeded.

### Recovery

If a selected clip cannot support a duck reaction, explain the reason and try
another result or an agent-refined search. Do not fabricate a reaction to keep
the loop moving. Use a bounded retry policy and pause after repeated failures,
including empty searches, unsupported clips, playback failures, or simulator
failures. Show why the loop paused and allow the user to retry or change the
prompt. Each cycle allows at most two searches; three consecutive failed cycle
requests pause the loop. Configuration and simulator failures pause immediately.

### Example sequence

An illustrative sequence, contingent on the retrieved evidence:

> Initial prompt: "Meet a curious deer" → a caption describes one deer approaching
> while another watches → the companion uses `approach`, and the duck uses
> `stand_hold` to approximate the watching animal → both finish and playback ends
> → the next search uses the role plan and actual outcome to continue.

### Loop acceptance criteria

- A nonblank user prompt and enabling Loop mode start an agent-mediated search.
- Each selected clip comes from a real search result. Codex chooses each reaction
  through the supported action interface, and execution requires valid evidence,
  response eligibility, parameters, and simulator readiness.
- The second and subsequent searches use the preceding simulator outcome and
  clip context, while retaining the original user prompt.
- The loop continues across new clips without further user submissions and
  uses recent history to avoid repeats.
- Only one cycle is active; progression waits for the simulator's actual
  reaction outcome.
- The UI makes the query, reaction, and reason for the next search visible and
  labels caption-derived reactions as inferred.
- Disabling Loop mode or resetting prevents late results from starting another
  clip or movement and allows the duck to settle safely.
- Unsupported evidence and repeated failures produce visible recovery or a
  pause rather than fabricated actions or an unbounded retry loop.

## Original search-only scope

This specification implements [intent.md](intent.md): submit a natural-language
query, review matching video segments, and play them inline in a browser,
without signing in.

## User experience

1. Enter a query and submit it with the Search button or Enter.
2. Review matching segments in the order returned by the backend. Each result
   shows its available description and timestamps.
3. Play an available segment within its result using native video controls.
   Use `preload="none"` so results do not download video before playback is
   requested. Do not autoplay. Show a clear message when a result has no source.

Reject blank or whitespace-only queries locally. While a search is running,
show a loading state and prevent duplicate submissions. Show a clear message
when no matches are returned. On failure, preserve the query and allow retry.
Clear previous results when starting another search so they cannot appear to
match a pending or failed query.

A playback failure shows a safe message and a Retry video button within that
result. Keep its description, timestamps, and the search query available.

There are no sign-in or sign-out controls. The initial scope excludes filters,
generated answers, uploads, and dashboards.

## API integration

The HTML, CSS, and JavaScript frontend in `web/` calls the same-origin FastAPI
server in `server.py`. The verified workshop VSS service rejects the local
frontend origin through CORS, and VSS authentication is handled on the server.
The browser does not call VSS directly or receive its credentials or token.

FastAPI reads `INGRESS_URL`, `USERNAME`, and `PASSWORD` from the environment,
loaded from the trusted workshop configuration. It authenticates through
`POST /api/v1/auth/login` with `username` and `password`, and caches the returned
`access_token` in server memory. On an upstream request 401, it refreshes that
session and retries once. Concurrent requests share session refresh rather than
each logging in separately. Authentication failures appear as request failures;
the user is never asked to sign in.

The browser sends only the query to `POST /api/v1/search`:

```json
{
  "query": "forklift near a person"
}
```

FastAPI forwards the same payload to the existing VSS search endpoint with an
`Authorization: Bearer <token>` header, preserving the backend defaults. It
returns `results[]` in backend order. Search and indexing remain VSS
responsibilities; the adapter has no account database or search index.

All users of this frontend search as the configured workshop account. VSS
applies that account's access controls. Keep passwords, tokens, and real
configuration values out of the browser, source code, committed files, and logs.
Return safe error messages without exposing upstream diagnostics.

### Segment playback

The browser requests `GET /api/v1/videos/stream?source=...` from FastAPI.
Only sources returned by authenticated searches are eligible for playback;
the server retains the most recent 1,024 sources in memory and rejects other
sources. After a server restart or eviction, repeat the search to load that
video again. FastAPI calls the existing VSS stream endpoint
with `source` and the server-held JWT as query parameters. The browser never
receives the JWT or a direct upstream playback URL.

Forward the browser's `Range` header and preserve the upstream partial response
status, `Content-Range`, `Content-Length`, and `Accept-Ranges` headers so native
controls can seek within a clip. Stream bytes without buffering the entire
video. The verified VSS endpoint can return a generic binary content type for
an MP4; serve `video/mp4` for sources with that extension.

`source` identifies the individual segment clip. Its playback begins at zero,
even when the displayed `segment_start_sec` is a nonzero offset in the parent
video. Do not seek the segment player to that parent offset.

## Result timestamps

Render `reasoning_content` as plain text. The live API and backend source confirm
`segment_start_sec` and `segment_end_sec` as numeric offsets in seconds on the
parent video timeline. Display those values as timestamps; omit absent values.
Zero is valid, although VSS also uses zero for some missing underlying values,
which the frontend cannot distinguish.

If another deployment changes its timing contract, configure
`VSS_RESULT_START_FIELD`, `VSS_RESULT_END_FIELD`, and `VSS_RESULT_TIME_UNIT`
(`seconds`, `milliseconds`, or `text`) on the server.

## Run the implementation

Run `make` or `make help` for the available commands. Python 3.10+ is required
for the service. Use the configured workshop environment where VSS is reachable.
In Bash, load the trusted configuration for your assigned team, then start the
app from this implementation's checkout:

```bash
bash
set +x
set -a
source /config/YOUR_TEAM.config
set +a
make setup
make run
```

Replace `YOUR_TEAM.config` with the existing filename. Do not print or copy its
credential values. If necessary, list filenames with
`find /config -maxdepth 1 -type f -name '*.config'`. If the configured environment
is unavailable, obtain access from the organizers; do not guess an endpoint or
paste secrets into chat. Loading the file on the VM does not configure your
laptop.

`make run` checks that `INGRESS_URL`, `USERNAME`, and `PASSWORD` are present
without printing their values. The VSS address must be reachable from the
FastAPI host. Open `http://127.0.0.1:8000` and search immediately. Press Ctrl+C to
stop the service. Use `make setup PYTHON=python3.12` to choose the virtual
environment interpreter or `make run PORT=8080` to change the port. Make invokes
the virtual environment directly; shell activation is unnecessary.

The service binds to loopback by default. To use an app running on the workshop
VM from your laptop, keep this SSH tunnel open:

```bash
ssh -L 8000:127.0.0.1:8000 YOUR_WORKSHOP_SSH_ALIAS
```

Use your configured alias and keep local port 8000 free for the tunnel.

## Verification and acceptance criteria

- A user can submit a nonblank query immediately, without signing in.
- The server authenticates with the configured workshop account and forwards
  only the query to the existing VSS search API.
- An expired VSS session is refreshed server-side, with at most one request retry.
- Results preserve backend order and show available descriptions and timestamps.
- Each available segment plays inline with native controls and supports seeking.
  Playback starts at the clip's beginning and is requested only by user action.
- Missing videos and playback failures are visible; failed playback can be retried
  without repeating the search.
- Playback is limited to sources returned by authenticated searches.
- Blank input, loading, empty results, and failures are visible; failures do not
  discard the query or display stale results.
- Credentials and VSS tokens stay on the server.

Run the automated checks with Python 3.11+ in the virtual environment and
Node.js 20+:

```bash
make test
```

For browser checks without workshop access, run `make demo` and open
`http://127.0.0.1:8001`. The separate test server uses synthetic data, requires
no sign-in, and never connects to VSS. Search normally for sample results, or
use `empty`, `error`, `slow`, `malformed`, and `markup` to exercise state changes
and safe text rendering. Fixture timing names do not establish the live contract.

Live contract verification confirmed successful VSS login, account verification,
and a query-only search for `person` returning 15 matches with the expected
description and timing fields. The updated frontend also returned those 15
matches in a live browser search without any sign-in step. A live `red bus`
search also returned 15 matches; its first result was a five-second MP4 segment
whose range request returned 206 with the expected byte-range headers. Browser
verification confirmed that this clip rendered and played through to completion
inside its result card. Automated checks cover range responses, authentication
refresh, rejected sources, safe failures, and stream cleanup after disconnect.
Recheck playback, seeking, and retry after integration changes, as well as the
search's empty and error states.

API references: [retrieval guide](../.agents/references/retrieval.md),
[login](../.agents/skills/retrieval-login/SKILL.md),
[search](../.agents/skills/retrieval-search/SKILL.md), and
[video playback](../.agents/skills/retrieval-videos/SKILL.md).
