# Ranger Duck implementation context

This context supports the [approved plan](RANGER_DUCK_PLAN.md) and [frontend integration contract](RANGER_DUCK_API.md). The user subsequently supplied `apps/ranger-duck/design/` and requested frontend implementation by a subagent, with backend integration, commit, and push. The supplied design is the UX reference; the API contract records its runtime adaptation.

## Current product decisions

- One page contains one animal outside the yellow box, the continuous MuJoCo duck, live search, reference playback and automatic movement status. The animal remains outside the arena and the duck attends to it during search and between clips; original procedural geometry remains because the animal-model replacement was canceled.
- Cat scenarios are Hissing, Greeting and Social play; deer scenarios are Forage together, Follow companion and Herd alert. The agent generates a fresh query for interactions of the selected species or similar individual behavior.
- Cat searches in both modes use tags `meow-10k` and `cat-behavior`; the requested dataset identity is `hf-smgjch-meow-10k`. The live schema exposes no dataset_id search filter, and sampled cat results omit that metadata, so this ID is recorded as requested scope rather than fabricated clip provenance. Deer retains the wildlife tag.
- Returned footage may show a single animal. An explicit supported behavior of the selected species plus complete provenance is sufficient; an actual interaction is not required.
- Exclude `head_scan` and `stand_hold` from retrieval-selected actions in Encounter and Loop. Eligible actions are `short_walk`, `ground_pick`, `head_nod` and `sit_cycle`; a mixed caption can contribute its active behavior. With no active evidence, report no match rather than use a neutral hold.
- Filter all returned candidates for compatible active actions, preserve retrieval order, and take the first three. Display action positions and original source ranks separately. Incompatible clips do not occupy visible slots; later ranks can fill them.
- Whenever an animal appears, the duck turns toward it and approaches only as needed, including while the agent is planning/searching. It maintains attention between clips. Before an action the animal settles at its anchor, then the duck completes positioning and executes the reference-derived motion. The UI shows actual movement commands; navigation remains separate from imitation.
- The controller retains six primitives: `short_walk`, `ground_pick`, `head_nod`, `head_scan`, `sit_cycle` and `stand_hold`. Retrieval uses the four active ones in walk → pick → nod → sit order. Species/actor attribution and negation still apply; exact current reviews keep their explicit behavior and passive reviews are excluded. Retrieval order is unchanged. Unsupported climbing, retreat or lying does not become a fabricated movement.
- Exact reviewed solitary references are usable again. Caption-inferred actions remain labeled unreviewed. Stale, invalid or contradictory reviews do not silently authorize new actions.
- Stop and hidden-tab handling stop navigation and imitation. Visibility-only pauses resume automatically; manual Stop and reference inspection stay paused. Clip transitions and repeated cycles never reset physics.
- Replay is explicit, session-scoped, expires and still needs VSS for video. Broader search relaxes behavior wording while retaining the selected species and allowing interactions or similar individual motion.
- New training, physical robot control, camera recognition and actual live-animal interaction remain outside scope.

These decisions supersede the earlier fixed-animal, strict pair eligibility and raw-rank 1–3 rules recorded in the historical notes below. See the [current plan](RANGER_DUCK_PLAN.md), [API contract](RANGER_DUCK_API.md) and [behavior research](RANGER_DUCK_INTERACTIONS.md).

## Local agent runtime

The demo backend and Codex CLI run on the presenter's Mac using the existing ChatGPT OAuth login. The user explicitly rejected a private SSH bridge; no agent bridge or copied account credentials are part of this implementation. Search and action planning use bounded structured decisions. VSS access still needs its own local configuration.

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

These observations originally motivated a reviewed-only reference manifest. The current automatic flow also allows conservative caption inference, explicitly labeled as unreviewed. Complete provenance, the selected species, and a supported behavior are required; solitary behavior is eligible. Ambiguous, unsupported, or changed evidence cannot supply an action. Never manufacture reviewed examples.

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

## Historical same-species automatic sequence update

The new catalog and automatic sequence replace the earlier Copy control. Original retrieval ranks are preserved, including gaps after invalid or duplicate sources. Cat queries search the authenticated archive without the wildlife tag; deer queries retain it. Exact caption text, source, parent and interval bind each inferred action. The initial implementation used two animal actors; the user then requested one animal facing the duck, with the duck occupying the partner role. Cycle resets are removed so the same physics body persists through all video transitions.

Initial live cat queries found paired observation and directed head-turn captions, but no explicit hiss in the first hissing top three. The deer co-foraging top three described solitary deer and must be skipped. These are archive observations, not guarantees about future results. The research note records the behavior sources and the current API describes the action-basis fields.

Integrated browser verification: a live Cat/Hissing encounter returned 15 candidates in 9.88 seconds. Original rank 1 drove a caption-inferred observing pause, rank 2 a directed head scan, and unsupported rank 3 was skipped. The page completed two automatic cycles without per-action clicks; Stop returned the duck to ready, and Resume began a fresh cycle without a new search. Actual reference video played through the session-scoped proxy. The initial results did not describe a hiss, and the UI displayed their actual inferred behaviors.

Final interaction verification: 96 backend tests and 26 frontend/adapter tests pass; the production build succeeds. Real browser physics checks completed head scan, short walk, ground pick, standing, and another walk across resets with zero recoveries. The head yaw covered 0.509 radians and returned to neutral. Development QA hooks are omitted from production. Deer/Forage returned 15 references in 10.43 seconds, with all top-three solitary results visibly skipped.

## Historical single-animal and continuous-loop corrections

The user requested exactly one simulated animal interacting with the duck, with no repeated duck reloads. The scene now treats the duck as the partner represented by the reference footage. The archive queries remain cat–cat and deer–deer. `prepareCycle` now waits for balance instead of calling `resetSim`, preserving the same body and physics clock between clips and cycles.

The idle report had three contributors: watching a companion mapped to a motionless hold, strict directed-interaction wording rejected clear focal attention in multi-animal clips, and hiding the page paused the loop without automatic resume. Watching now drives an explicitly labeled attentive head-turn approximation. Clear shared or focal actions in a confirmed same-species pair clip can drive supported motions without being mislabeled as a greeting or hiss. Visibility-only pauses resume on return; intentional Stop and reference inspection remain paused.

Verification of these corrections: 109 backend tests and 30 frontend/adapter tests pass; the production build succeeds. Real browser physics completed 14 consecutive bounded walking actions with no resets or recoveries. The physics clock advanced continuously from 1.54 to 39.86 seconds and X/Y stayed within ±0.633 m, below the 1.15 m boundary. Cycle preparation settles in about 0.2 seconds without replacing the duck. Exact live Social-play captions map companion observation and shared toy attention to head scans; the climbing-only reference remains skipped.

## Historical fixed-animal, navigation, and compatible-action ranking update

At this stage, the user requested a single scripted animal at a fixed position outside the yellow box. Its head and pose may animate toward Microduck, but its root does not translate. Microduck uses the existing locomotion policy to roam inside the box while searching or between action cycles, then approaches the animal and settles before each evidence action. Navigation is labeled separately from imitation. Neither navigation nor cycle preparation resets the duck or replaces its physics body; Stop cancels both navigation and actions.

Search queries still describe cat–cat or deer–deer interactions. Result eligibility now accepts supported solitary behavior as well as interactions. The queue filters the entire response for compatible actions, preserves archive order, and takes up to three. Action positions and original source ranks are displayed separately; incompatible hits do not occupy slots. Existing exact reviews of solitary behaviors are valid again, with the same source, interval, caption, and species checks.

Live retrieval checks on 17 October confirmed the new selection rules: Cat/Social Play returned 15 candidates in 11.37 seconds and selected original ranks 1, 3, and 4. Deer/Forage returned 15 candidates in 11.03 seconds and selected three solitary feeding clips. These measurements establish those runs, not a latency guarantee or a visual review of inferred behavior.

Verification: 126 backend tests (including the three newly merged dotenv configuration checks) and 37 frontend/adapter tests pass, and the production frontend builds. A live Deer/Forage run completed its search in 9.76 seconds, approached the fixed deer, completed all three solitary feeding actions automatically, and continued into a second cycle. Stop paused the active second-cycle action and retained the scene. Real MuJoCo checks also covered 11.5-second and 30-second initial roaming waits followed by approaches, walking, and feeding, without a reset or recovery. The roaming route stays farther inside the yellow box to leave space for the pretrained policy's turning radius.


## Six motions, caption activity priority and animal motor update

The current update adds `head_nod` (2400 ms) for explicit vertical head motion
and `sit_cycle` (6000 ms) for explicit sitting. It does not infer sitting from
lying or turn unsupported motion into a different action. The classifier
examines all caption phrases by supported activity priority while retaining
source ranks and first-three-compatible selection. The backend suite passes
163 tests; the frontend agent reports 45 combined tests and a production build.

A single real MuJoCo session completed all six primitives with approach before
each, roaming, and repeated-Stop cancellation during sitting and nodding.
Physics time advanced from 1.56 to 45.56 seconds with no reset or recovery;
X remained within [-0.670, 0.465] m and Y within [-0.278, 0.047] m. The seated
trunk dropped from about 0.116 m to 0.059 m and returned. The nod covered about
0.52–0.53 rad of actual pitch. An intermediate cancellation test exposed a
native stand-up timer hazard; the final adapter preserves that two-second
handover across repeated Stop/preparation calls. See the [motion inventory,
source references and limitations](RANGER_DUCK_ANIMATION.md).

The animal motor may patrol outside the east side of the box and returns to
(1.05, -0.05) before an action. The wrapper waits for its position, facing and
180 ms of stability before approaching with the duck. Stop/reset cancel both
motors and pending waits. The user canceled the animal-model replacement;
original articulated procedural geometry remains. New animal asset generation or an
animal model-loading pipeline is not part of this deliverable.

Final ordinary-browser verification: Cat/Social Play returned 15 candidates in
9.71 seconds. Source rank 1 now selected the described cat movement as
`short_walk` instead of its companion's watching. The compatible queue used
source ranks 1, 4 and 5 in that run, completed two cycles, and preserved the
same duck scene throughout. The animal returned to its anchor before approach.
Stop during the third cycle's approach canceled movement and left the duck
ready. These are observed run results, not an archive ranking or latency
guarantee.


## Local OAuth and proactive attention validation

The local Codex CLI reported ChatGPT authentication and produced a real structured
query. Both the local Encounter and Loop APIs completed live tagged cat searches.
A normal Encounter run selected compatible archive ranks 1, 4 and 7, ran five
automatic three-action cycles, and Stop preserved the duck while zeroing movement.
The browser showed actual turning/walking commands during positioning.

A separate continuous MuJoCo check completed three consecutive walking actions
and returns to the interior interaction position `(0.12,0)`: 42.6 seconds of
physics, 427 samples, no reset, recovery or arena-boundary failure. The wider
stand-off leaves room for the pretrained policy's forward turning radius.

Cat searches send both requested tags. A live metadata-schema check confirmed
that `dataset_id` is not a supported filter field; sampled tagged clips lacked
a dataset identifier. The configured ID is therefore marked as requested scope.
Actual clip identifiers are preserved only when the archive returns them.
