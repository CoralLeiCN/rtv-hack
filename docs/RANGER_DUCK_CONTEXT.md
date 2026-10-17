# Ranger Duck implementation context

This context supports the [approved plan](RANGER_DUCK_PLAN.md) and [frontend integration contract](RANGER_DUCK_API.md). The user subsequently supplied `apps/ranger-duck/design/` and requested frontend implementation by a subagent, with backend integration, commit, and push. The supplied design is the UX reference; the API contract records its runtime adaptation.

## Current product decisions

- One page contains one scripted animal interacting with the MuJoCo duck, live search results, reference playback, and automatic movement status.
- The user selected cat–cat and deer–deer interactions. Cat scenarios are Hissing, Greeting, and Social play; deer scenarios are Forage together, Follow companion, and Herd alert.
- An encounter supplies a species-pair query. A returned segment's existing video-model caption supplies a possible movement; the query itself never authorizes movement.
- Use original upstream ranks 1–3, skip unsupported or missing slots visibly, and repeat supported actions automatically without another search. No per-action Copy click is required. Stop/Resume, Reset, changed scenarios, and hidden-tab cancellation remain available.
- Supported movements are `ground_pick`, `short_walk`, `stand_hold`, and the physics-verified `head_scan`. Backward-walk attempts did not produce meaningful displacement; retreat-only evidence is unsupported.
- Caption-inferred actions remain visibly unreviewed. They require complete provenance, the correct species pair in the reference, and an explicitly described supported action. An optional exact visual review can also authorize a matching interaction; stale or solitary-animal reviews cannot.
- Replay is explicit, session-scoped, expires, and still needs VSS connectivity for video. Broader search relaxes behavior while keeping the same species pair.
- The animal actors are scripted and non-colliding. New training, physical robot deployment, camera recognition, and actual animal interaction are outside scope.

The [current plan](RANGER_DUCK_PLAN.md), [API contract](RANGER_DUCK_API.md), and [research note](RANGER_DUCK_INTERACTIONS.md) supersede the earlier manual-selection flow described in the historical verification below.

## VSS access

Use the repository skills before live requests: [login](../.agents/skills/retrieval-login/SKILL.md), [search](../.agents/skills/retrieval-search/SKILL.md), [metadata](../.agents/skills/retrieval-list-metadata/SKILL.md), and [playback](../.agents/skills/retrieval-videos/SKILL.md).

The backend reads `INGRESS_URL`, `USERNAME`, and `PASSWORD` from its environment. The VM startup procedure may load the existing absolute `/config/` file in Bash. Do not commit real values, discover credentials elsewhere, or print authentication responses. No deployment or pipeline modification is required to use these APIs.

The verified compatible path is `POST /api/v1/search` with `llm_top_n: 1`. On 17 October, the live service rejected zero with HTTP 422 because its schema requires at least one. Inspection of the deployed source confirmed that nonempty chunk results always trigger synthesis, and `/tools/search` uses the same implementation. The backend discards the summary and reports measured end-to-end latency. Label the feature Live search; do not claim synthesis-free performance. Preserve the backend's authenticated ACL scope.

Search returns segment `results` and parent-level `chunk_results`. Playback uses `/api/v1/videos/stream`; segment metadata uses `/api/v1/videos/metadata`. The app proxy must keep the upstream JWT out of browser URLs and support byte ranges. Metadata filters must use values discovered from the metadata API, while observed wildlife tags go in `tags`.

Read-only live checks on 17 October used the wildlife tag, `top_k: 15`, `llm_top_n: 1`, and `min_similarity: 0.3`:

- Feeding, walking, and standing queries returned HTTP 200 in 7.209, 4.618, and 7.304 seconds respectively. Each returned 15 segment hits and 15 parent groups, with synthesis present. These are three measurements, not a latency guarantee or evidence that the footage matches correctly.
- Returned segment rows included source identity, parent identity, caption, and segment start/end. A metadata lookup also returned HTTP 200.
- A 32-byte playback request returned HTTP 206 with valid Content-Range and Accept-Ranges headers. An out-of-bounds range returned 416. Upstream HEAD returned 405, so the proxy needs a GET-headers fallback that closes the body without downloading the full clip.
- The tested stream used `binary/octet-stream`. The proxy must handle this deployed MIME value, with a video MIME type for recognized media extensions, rather than reject playable results.

## Existing wildlife observations

Local experiment files available in the workspace contain snapshot results from 17 October 2026. They are working data, not part of this documentation commit. Their private storage paths, machine settings, and raw snapshots are deliberately not needed by the shared API contract.

- The wildlife snapshot contains eight parent videos and 24 segments. This is a saved sample, not a current inventory.
- Eight saved wildlife-query durations are 3.48, 5.21, 2.72, 4.93, 2.91, 4.04, 4.57, and 7.91 seconds. The request bodies were not preserved, so these do not establish latency for synthesis-free search.
- The small prompt-comparison diagnostic improved the expected source's top-three retrieval count from 3/8 to 4/8. It is not a representative benchmark.
- Caption review found deer described as horses or sheep, unsupported elephant claims, and missed or incorrect behaviors. A pipeline success flag does not establish correct recognition.

These observations originally motivated a reviewed-only reference manifest. The current automatic flow also allows conservative caption inference, explicitly labeled as unreviewed. Complete provenance and pair-specific behavior are required; ambiguous, unsupported, or changed evidence remains playable without an action. Never manufacture reviewed examples.

Relevant local files for subsequent authorized inspection are `experiments/wildlife/results/wildlife-snapshot.json`, `wildlife-queries.json`, and `prompt-comparison-evaluation.json`, plus `experiments/wildlife/vss_client.py` as an authentication-pattern reference. Do not import that experiment client directly into the new backend: its long request timeouts and ingest-oriented retry behavior do not match this demo.

## Frontend simulator integration

The official [Microduck browser simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator) runs MuJoCo and pretrained ONNX policies in the browser. Pin its source and matching LFS assets. The frontend can add a non-colliding scripted animal in Three.js while preserving the duck's physics controller.

The [controller source contract](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/app/src/game/controls/controller.js) accepts a custom command source. The [game code](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/app/src/game/game.js) connects it to discrete movement handlers and exposes motion state and head targets. Implement a small frontend adapter around these controls; the backend returns primitive names, never joint commands.

Reset must invalidate the current encounter, stop any action, and ignore late responses. Changing evidence must cancel an action selected from the previous clip. Search animations and imitation are separate: a searching scan is a UI cue, while an imitation needs a returned evidence ID. The frontend is responsible for motion completion, bounded walking, and simulator recovery handling.

## Delivery boundary

The backend deliverable includes the HTTP service, dependency metadata, unit/integration tests, example configuration with names only, reference-manifest tooling, and startup instructions. It must run without VSS configuration for local contract testing, report live search as unconfigured, and avoid fake live data.

Tests should cover upstream authentication and timeouts, evidence eligibility, response normalization, scoped opaque video IDs, and range playback. Live access and human review of clips remain separate verification steps when the configured VM is available. Do not deploy, upload, re-ingest, or modify the shared pipeline as part of backend implementation.

## Earlier implementation and verification (manual flow)

The implementation preserves the supplied design's colors, typography, scenario controls, evidence cards, video HUD, behavior mapping, and stage strip. On desktop the scene stays visible while evidence details scroll. The simulator vendors the official Apache-licensed source at revision `ad9d41a763f30dc770817c33d92dcfec0205db1e`; a setup script verifies all 53 downloaded assets by SHA-256. Runtime binaries and private reference manifests are not committed.

The simple video search app arrived in subsequent commits. Ranger Duck adapts its fractional timestamp formatting, playback retry and disposal, generic video MIME handling, sanitized stream cleanup, and JWT-only upstream request handling. Its free-query API and raw-source playback URLs are not used because Ranger Duck needs scenario requests, session-scoped clip IDs, and evidence-bound movement authorization.

Verification on 17 October: 41 backend tests and 15 frontend/adapter tests pass, and the production frontend builds. Live checks returned archive results, played and sought a real segment, kept Copy disabled for unreviewed results, and distinguished explicit replay from live search. Three real browser controller checks completed without recovery: ground pick about 3.13 seconds, short walk about 2.46 seconds including settling (0.16 m translation, with commands bounded to two seconds), and stand about 3.33 seconds including settling. These controller checks used a development-only test hook, omitted from the production build; they do not establish reviewed wildlife evidence.

The full feeding flow also passed through the ordinary browser UI: Start triggered live retrieval, a visually checked deer-feeding reference enabled Copy, the real controller performed `ground_pick`, and the UI reported completion after the duck returned to standing. The reference was checked in actual browser playback and its private manifest remains on the workshop VM at `/tmp/ranger-duck-smoke.wTyRsF/feeding-review.json`. Set `RANGER_REFERENCE_MANIFEST` to that path on the same VM to reuse it while the temporary directory exists. The reference must still occur in the current live results with unchanged identity, interval, and caption to enable Copy.

The committed default manifest remains empty because real source identities are private. Fresh environments need their own footage review, and walking/standing references have not yet been reviewed. No shared service deployment, upload, or re-ingest was performed for this implementation.

The first user run exposed intermittent Feeding search failures around 10.3 seconds. The generic upstream read timeout was only 10 seconds, with a 12-second overall backend deadline and 13-second browser abort, leaving too little room for the observed VSS response times. Search now uses a 30-second overall default and gives the search response read that full budget; connection/authentication/video timeouts stay at 10 seconds. Health advertises the configured budget and the browser adds five seconds of grace, so the two deadlines stay aligned. The updated 42 backend and 16 frontend tests and production build pass. After restarting the running demo with the fix, a live Feeding encounter completed in 10.57 seconds and returned 15 candidates including the reviewed feeding reference.

## Same-species automatic sequence update

The new catalog and automatic sequence replace the earlier Copy control. Original retrieval ranks are preserved, including gaps after invalid or duplicate sources. Cat queries search the authenticated archive without the wildlife tag; deer queries retain it. Exact caption text, source, parent and interval bind each inferred action. The initial implementation used two animal actors; the user then requested one animal facing the duck, with the duck occupying the partner role. Cycle resets are removed so the same physics body persists through all video transitions.

Initial live cat queries found paired observation and directed head-turn captions, but no explicit hiss in the first hissing top three. The deer co-foraging top three described solitary deer and must be skipped. These are archive observations, not guarantees about future results. The research note records the behavior sources and the current API describes the action-basis fields.

Integrated browser verification: a live Cat/Hissing encounter returned 15 candidates in 9.88 seconds. Original rank 1 drove a caption-inferred observing pause, rank 2 a directed head scan, and unsupported rank 3 was skipped. The page completed two automatic cycles without per-action clicks; Stop returned the duck to ready, and Resume began a fresh cycle without a new search. Actual reference video played through the session-scoped proxy. The initial results did not describe a hiss, and the UI displayed their actual inferred behaviors.

Final interaction verification: 96 backend tests and 26 frontend/adapter tests pass; the production build succeeds. Real browser physics checks completed head scan, short walk, ground pick, standing, and another walk across resets with zero recoveries. The head yaw covered 0.509 radians and returned to neutral. Development QA hooks are omitted from production. Deer/Forage returned 15 references in 10.43 seconds, with all top-three solitary results visibly skipped.

## Single-animal and continuous-loop corrections

The user requested exactly one simulated animal interacting with the duck, with no repeated duck reloads. The scene now treats the duck as the partner represented by the reference footage. The archive queries remain cat–cat and deer–deer. `prepareCycle` now waits for balance instead of calling `resetSim`, preserving the same body and physics clock between clips and cycles.

The idle report had three contributors: watching a companion mapped to a motionless hold, strict directed-interaction wording rejected clear focal attention in multi-animal clips, and hiding the page paused the loop without automatic resume. Watching now drives an explicitly labeled attentive head-turn approximation. Clear shared or focal actions in a confirmed same-species pair clip can drive supported motions without being mislabeled as a greeting or hiss. Visibility-only pauses resume on return; intentional Stop and reference inspection remain paused.

Verification of these corrections: 109 backend tests and 30 frontend/adapter tests pass; the production build succeeds. Real browser physics completed 14 consecutive bounded walking actions with no resets or recoveries. The physics clock advanced continuously from 1.54 to 39.86 seconds and X/Y stayed within ±0.633 m, below the 1.15 m boundary. Cycle preparation settles in about 0.2 seconds without replacing the duck. Exact live Social-play captions map companion observation and shared toy attention to head scans; the climbing-only reference remains skipped.
