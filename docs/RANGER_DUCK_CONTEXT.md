# Ranger Duck implementation context

This context supports the [approved plan](RANGER_DUCK_PLAN.md) and [frontend integration contract](RANGER_DUCK_API.md). The user subsequently supplied `apps/ranger-duck/design/` and requested frontend implementation by a subagent, with backend integration, commit, and push. The supplied design is the UX reference; the API contract records its runtime adaptation.

## Product decisions

- Present the complete demonstration on one page: a shared animal and Microduck scene, live search results, a reference video, and the Copy this behavior control.
- Use a scripted scene to supply animal and behavior labels. Camera recognition is not part of this version.
- Query VSS when an encounter begins. Select a returned reference and use its reviewed behavior to choose an existing duck movement.
- Core movements are feeding to `ground_pick`, walking to `short_walk`, and standing to `stand_hold`. Resting to `sit` and looking around to `head_scan` are optional.
- New training, real animal interaction, physical robot deployment, voice input, and safari playlists are outside the approved build.
- Keep live retrieval and cached replay visibly distinct. Never enable an action solely from the scenario or search query.
- The implemented replay stores only previous successful live results in the browser's backend session. It is explicit, expires, and still requires VSS for video. Broader retrieval changes the query to a hoofed animal while preserving the deer review requirement.
- The first simulator adapter implements `ground_pick`, `short_walk`, and `stand_hold`. Optional sitting and head scanning are not authorized as imitation actions until implemented and verified.

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

These observations motivate a reviewed reference manifest. Start with an empty manifest rather than manufacturing reviewed examples. Review actual playable segments, record animal and behavior labels, bind them to source identity and caption hash, and only allow a returned matching reference to enable a movement. Unreviewed and changed results remain playable with no action.

Relevant local files for subsequent authorized inspection are `experiments/wildlife/results/wildlife-snapshot.json`, `wildlife-queries.json`, and `prompt-comparison-evaluation.json`, plus `experiments/wildlife/vss_client.py` as an authentication-pattern reference. Do not import that experiment client directly into the new backend: its long request timeouts and ingest-oriented retry behavior do not match this demo.

## Frontend simulator integration

The official [Microduck browser simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator) runs MuJoCo and pretrained ONNX policies in the browser. Pin its source and matching LFS assets. The frontend can add a non-colliding scripted animal in Three.js while preserving the duck's physics controller.

The [controller source contract](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/app/src/game/controls/controller.js) accepts a custom command source. The [game code](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/app/src/game/game.js) connects it to discrete movement handlers and exposes motion state and head targets. Implement a small frontend adapter around these controls; the backend returns primitive names, never joint commands.

Reset must invalidate the current encounter, stop any action, and ignore late responses. Changing evidence must cancel an action selected from the previous clip. Search animations and imitation are separate: a searching scan is a UI cue, while an imitation needs a returned evidence ID. The frontend is responsible for motion completion, bounded walking, and simulator recovery handling.

## Delivery boundary

The backend deliverable includes the HTTP service, dependency metadata, unit/integration tests, example configuration with names only, reference-manifest tooling, and startup instructions. It must run without VSS configuration for local contract testing, report live search as unconfigured, and avoid fake live data.

Tests should cover upstream authentication and timeouts, evidence eligibility, response normalization, scoped opaque video IDs, and range playback. Live access and human review of clips remain separate verification steps when the configured VM is available. Do not deploy, upload, re-ingest, or modify the shared pipeline as part of backend implementation.

## Implementation and verification

The implementation preserves the supplied design's colors, typography, scenario controls, evidence cards, video HUD, behavior mapping, and stage strip. On desktop the scene stays visible while evidence details scroll. The simulator vendors the official Apache-licensed source at revision `ad9d41a763f30dc770817c33d92dcfec0205db1e`; a setup script verifies all 53 downloaded assets by SHA-256. Runtime binaries and private reference manifests are not committed.

The simple video search app arrived in subsequent commits. Ranger Duck adapts its fractional timestamp formatting, playback retry and disposal, generic video MIME handling, sanitized stream cleanup, and JWT-only upstream request handling. Its free-query API and raw-source playback URLs are not used because Ranger Duck needs scenario requests, session-scoped clip IDs, and reviewed movement authorization.

Verification on 17 October: 41 backend tests and 15 frontend/adapter tests pass, and the production frontend builds. Live checks returned archive results, played and sought a real segment, kept Copy disabled for unreviewed results, and distinguished explicit replay from live search. Three real browser controller checks completed without recovery: ground pick about 3.13 seconds, short walk about 2.46 seconds including settling (0.16 m translation, with commands bounded to two seconds), and stand about 3.33 seconds including settling. These controller checks used a development-only test hook, omitted from the production build; they do not establish reviewed wildlife evidence.

The full feeding flow also passed through the ordinary browser UI: Start triggered live retrieval, a visually checked deer-feeding reference enabled Copy, the real controller performed `ground_pick`, and the UI reported completion after the duck returned to standing. The reference was checked in actual browser playback and its private manifest remains on the workshop VM at `/tmp/ranger-duck-smoke.wTyRsF/feeding-review.json`. Set `RANGER_REFERENCE_MANIFEST` to that path on the same VM to reuse it while the temporary directory exists. The reference must still occur in the current live results with unchanged identity, interval, and caption to enable Copy.

The committed default manifest remains empty because real source identities are private. Fresh environments need their own footage review, and walking/standing references have not yet been reviewed. No shared service deployment, upload, or re-ingest was performed for this implementation.
