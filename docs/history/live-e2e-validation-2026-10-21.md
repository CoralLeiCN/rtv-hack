# Live end-to-end validation

## Goal and scope

Validate one connected path from real source footage through Cosmos captioning,
EmbeddingGemma indexing and retrieval, authorized browser playback, and Ranger
Duck execution with Loop off and an adaptive follow-up round. Record measured
results separately from fixture tests. The owning procedure is
[testing](../testing.md#live-model-and-deployment-smoke-test).

Use explicitly selected archive and application configuration and footage with
known provenance. Preserve existing work in this checkout. Do not initialize or
replace external infrastructure, truncate an archive, import supplied captions,
substitute model fixtures, or submit synthetic simulator outcomes.

## Current evidence and prerequisites

Preflight on 21 October 2026:

- All 53 local simulator assets passed the pinned size/hash check.
- FFmpeg, FFprobe, Node, Docker and the Codex executable are present. Executable
  presence does not establish Docker availability or agent authentication.
- The existing backend environment uses Python 3.13.3 and has FastAPI, HTTPX
  and pytest. It lacks psycopg, qdrant-client, torch, sentence-transformers and
  transformers. A separate model-service host may provide these dependencies.
- The user subsequently selected the existing Ranger environment file. A
  presence-only configuration audit found none of the archive connection,
  database, Qdrant, Cosmos or embedding model/revision settings in that file
  or the exported variables. No configuration values were printed.
- The documented local archive and Ranger health endpoints were unreachable
  from this execution environment. Remote deployment health is unknown.
- The user selected one random Meow sample. One MP4 was chosen uniformly from
  all 6,735 MP4 files at the repository's pinned dataset revision, downloaded
  into ignored local media storage, and verified against its upstream checksum.
  FFmpeg decoded all 48 frames of the six-second, 448-by-448 video successfully.
  Its source URL, revision, checksum and selection method remain in the private
  provenance record beside the video. At that preflight stage it had not yet been
  captioned or ingested.
- The user then authorized setup on this machine. Created an ignored, owner-only
  archive environment file and added archive settings to the selected Ranger file,
  preserving its previous contents in an owner-only local backup. No external
  infrastructure was changed.

## Local setup and measured checks

The host is an Apple M4 Pro Mac with 48 GiB unified memory. Docker Desktop runs
an isolated `microduck-local` project with Postgres 17.6 and Qdrant 1.19.2 on
loopback ports 15432 and 16333. The archive schema and collection are initialized.
This is local Postgres validation, not a Neon deployment check.

- Installed the archive/Ranger Python environment and built the frontend. Archive
  liveness and authenticated readiness pass. Ranger serves the production build
  on port 18000; the browser loaded the MuJoCo scene and enabled Start. The Codex
  CLI reports an existing ChatGPT login. A live browser run generated a query in
  8.98 seconds, searched in 0.07 seconds and correctly returned zero references
  from the still-empty archive. This verifies planning and navigation startup,
  not evidence playback or a completed imitation round.
- Real EmbeddingGemma query and document inference pass: 768 finite dimensions,
  unit norms, 10.92 seconds including loading. An authenticated empty-archive
  search also passes, taking 4.74 seconds including API model loading. Empty
  results do not establish retrieval relevance.
- Loading the pinned embedding checkpoint exposed an incompatible Sentence
  Transformers 5.x constraint (`Pooling` configuration failed). Updated the model
  extra to require 6.1 and validated with version 6.1.0. The checkpoint revision
  is `914f7f89142e33e77833254d9c9b90c3cef7303b`.
- Selected the official Cosmos3-Edge reasoner, revision
  `344d602b128d1bbdacb43b08d0a3626f46343e29`, for the local Metal runtime. Added a
  loopback Transformers adapter preserving the archive's inline video request
  contract, four-frame-per-second sampling, and incomplete-generation rejection.
  Its processor decoded all 48 source frames and sampled 24 at four fps. All three
  weight files finished downloading and matched their upstream SHA-256 digests.
  The reasoner loaded on Metal and produced a real caption through the archive
  client. The first worker completed captioning and indexing in 22.64 seconds.
- The sample was ingested without supplied captions. Authenticated retrieval
  returned its one indexed segment with the exact stored caption. The archive
  served a 1,024-byte range with HTTP 206 and rejected unauthenticated playback
  with HTTP 401. The simple search UI on port 18003 retrieved it, played to the
  six-second end, and sought back to three seconds with the decoded frame visible.
  This is actual browser playback through the application adapter, not merely an
  HTTP check. Ranger capability isolation was verified in the final run below.
- Ranger's live cat encounter retrieved the segment (query 7.10 seconds, search
  0.07 seconds), then selected no active action. The real caption describes rolling
  followed by walking away, classified as `unsupported_retreat`. No action was
  issued and no simulator completion was fabricated. The user challenged this
  interpretation and requested Codex with Luna to decide actions instead of fixed
  rules. The final implementation and validation below use the same source clip.
- Fixture checks: 15 root JavaScript tests, 342 Python tests (17 database skips),
  107 frontend tests, production build, and diff whitespace checks passed. The
  Python count includes seven new local-reasoner contract tests.
- A separate disposable Postgres database ran all 359 Python tests: 358 passed;
  the existing `test_missing_stream_duration_uses_video_timeline` failed because
  this host's FFmpeg reported 1.9 seconds for the generated two-second WebM. The
  test database was removed; the real local archive was never used for tests.
  That existing ingestion change is outside this setup diff and is left intact.

Package versions, private logs, process IDs and source provenance are kept in
ignored local storage. Restart commands and configuration belong to
[archive operations](../guides/archive.md#isolated-local-database-services).

## Final agent implementation and live result

Codex CLI `gpt-6-luna` now receives all structurally valid captions, controller
capabilities, current exact-review constraints, original intent and actual outcome
history. It owns semantic action selection, actor/role interpretation and decisions
to repeat or skip. Removed runtime phrase vetoes and fixed motion preferences from
Encounter/unified runs and legacy Loop. Exact quotations, provenance-bound evidence
IDs, review vetoes, bounded commands, ownership and actual-outcome checks remain
application invariants. Missing/duplicate/unknown batch decisions are rejected.
The UI says “No action selected” when no action is issued.

The original Social Play run was declined because the clip does not show play.
The validation intent was then set to copy a supported movement from the cat,
including walking, while treating the preset as context. An intermediate adaptive
run exposed that batch action planning lacked the original intent; it now receives
that intent directly, as query planning already did.

The final browser run completed on 21 October 2026:

- The single Meow clip retained its real Cosmos caption, “A brown cat is rolling
  on the brown surface and then walks away.” Luna selected `short_walk`, quoted
  the full exact caption and explained that ordinary walking is supported, while
  rolling and the requested play/greeting interaction are not reproduced.
- Loop off completed four passes of the same queue with one query/search/action
  batch. Round 1 timings were 6.831 s query planning, 0.072 s retrieval and 6.147 s
  action planning. Playback reached the six-second end on each pass and the
  simulator reported observed walking completion.
- Enabling Loop at the boundary produced round 2 with Greeting, followed by round
  3 with Social Play. Both adaptive rounds completed. Luna explicitly justified
  reusing the sole reference for the original movement-copying goal. Round 2
  timings were 7.440 s query, 0.074 s retrieval and 6.940 s action planning; round 3
  timings were 8.266 s, 0.073 s and 5.352 s respectively.
- Six browser outcomes recorded `completed`, playback `ended`, duck state
  `complete` and a completed stationary companion. Simulation times advanced from
  33.40 through 50.16, 66.78, 83.76, 105.42 and 126.32 seconds without a scene
  reset between passes/rounds. No outcome was submitted by a test script.
- A separate newly established Ranger session received HTTP 404 when requesting
  the active browser's clip capability. The original browser played it normally.
- The run was paused after completion. Private capture records, filtered results
  and a screenshot remain in ignored local storage; no captures were exported.

A separate real Luna batch passed eight caption checks: ordinary walking away,
alternative walking wording, a moving dog observed by a stationary cat, negation,
uncertainty, backward steps, unsupported rolling/grooming and multiple available
motions. These are agent evaluations on supplied text, not eight additional
videos or Cosmos ingestion checks.

Final fixture checks passed: 15 root JavaScript tests, 351 Python tests with 17
DB skips, 107 frontend tests and the production build. The Python tests cover
agent decision authority, original intent, repeats with actual history, literal
quotes, exact review constraints and stable caption/provenance bindings. Existing
session/cancellation/playback tests also passed. Diff and document-link checks
passed. The separate disposable-DB FFmpeg discrepancy recorded above remains an
unrelated validation limitation.

## Ordered execution and acceptance checks

1. Select configuration, deployment host, footage and provenance. Confirm
   immutable model revisions, the direct worker database connection, shared
   media storage, installed package versions and the authenticated agent.
2. Check archive liveness and authenticated readiness. Check Ranger configuration
   and capture availability. Do not treat readiness as successful inference.
3. Ingest fresh footage without imported captions. Observe the real worker
   completing the selected job, with nonempty Cosmos captions, the expected
   embedding identity, published segment IDs and successful vector indexing.
   Do not process unrelated queued jobs as a side effect of validation.
4. Search through the running archive using real query embeddings. Match returned
   IDs, exact captions and intervals to the newly ingested footage, and inspect
   relevance. Keep source identities and raw evidence in private records.
5. In the browser, play and seek the returned evidence through the authorized
   application route. Check range handling and rejection from a different
   session. A successful HTTP response alone does not prove video playback.
6. Complete a Loop-off queue and observe its repetition without another search.
   Enable Loop at a queue boundary, then complete an adaptive follow-up round
   with a different interaction of the same species. Preserve the same scene
   and advancing simulation clock. If footage supplies insufficient supported
   actions, record the no-match result and obtain appropriate source footage.
7. Correlate actual browser playback, duck and companion completion with issued
   attempts and backend capture events. Confirm original retrieval ranks,
   caption/review labels and exact evidence bindings. Do not fabricate outcomes
   to advance the backend cursor.
8. Record revisions, commands, timings, observed results and limitations. Only
   mark the corresponding [status](../status.md) checkboxes complete after
   observing their outcomes. Move this plan to history when finished.

## Decisions and limitations

The requested connected local validation and agent-selection implementation are
complete. Only one real video was imported; adaptive rounds deliberately reused
it on the agent's decision. This validates the connected path, not broad behavior
coverage, a paired-actor action, all four controller primitives or caption-model
accuracy across the dataset. Cosmos ran on Metal and the archive used local
Postgres; Neon and a remote Cosmos deployment still need separate checks.

No alternative credential files were searched, no external infrastructure was
modified and no additional dataset clips were imported. The older deterministic
caption helper remains only for historical fixture coverage; runtime planners do
not call it. Semantic accuracy remains the agent's responsibility and cannot be
proved by literal quotation checks alone. Keep broader model evaluation separate
from the eight text checks and this one-video run.
