# Ranger Duck implementation context

This context supports the [approved plan](RANGER_DUCK_PLAN.md) and [frontend integration contract](RANGER_DUCK_API.md). The user will build the frontend separately. Backend work must stay under `apps/ranger-duck/backend/` and its own supporting files; do not create or change frontend files.

## Product decisions

- Present the complete demonstration on one page: a shared animal and Microduck scene, live search results, a reference video, and the Copy this behavior control.
- Use a scripted scene to supply animal and behavior labels. Camera recognition is not part of this version.
- Query VSS when an encounter begins. Select a returned reference and use its reviewed behavior to choose an existing duck movement.
- Core movements are feeding to `ground_pick`, walking to `short_walk`, and standing to `stand_hold`. Resting to `sit` and looking around to `head_scan` are optional.
- New training, real animal interaction, physical robot deployment, voice input, and safari playlists are outside the approved build.
- Keep live retrieval and cached replay visibly distinct. Never enable an action solely from the scenario or search query.

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
