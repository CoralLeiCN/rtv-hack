# Ranger Duck implementation plan

Current scope, updated 17 October 2026: one page combines a scripted same-species animal encounter, live archive search, reference playback, and an automatic loop of video-induced Microduck movements. This supersedes the original manual-selection/Copy flow. The user selected cat–cat and deer–deer reference interactions.

The implementation follows the [design handoff](../apps/ranger-duck/design/README.md), with added species/interaction controls and automatic sequence status. See the [API contract](RANGER_DUCK_API.md), [behavior research](RANGER_DUCK_INTERACTIONS.md), and [startup instructions](../apps/ranger-duck/README.md).

## Inputs and outputs

| Stage | Input | Output |
| --- | --- | --- |
| Choose encounter | Cat or deer, plus one interaction | A scripted pair of animals in the shared scene |
| Start | Selected catalog entry | Encounter ID, focal animal, same-species partner, behavior hint |
| Retrieve | A query describing that species pair and interaction | Actual ranked VSS segment results and measured latency |
| Interpret evidence | Each returned segment's video-model caption and provenance | A supported bounded action, or a visible reason to skip |
| Run sequence | Original search ranks 1–3 | Muted reference playback and one controller action at a time |
| Repeat | The same three evidence slots | Another cycle after recentering; no new archive request |
| Stop or Reset | Presenter control or a changed encounter | Cancellation of the current sequence and movement |

The encounter hint supplies the query only. It never directly supplies the duck action. Each action is an approximation of a behavior described in its own reference, with the copied role and limitations shown. Caption-derived actions are labeled as inferred rather than visually reviewed.

## Interaction catalog

| Animal pair | Encounter | Query intent |
| --- | --- | --- |
| Cat–cat | Hissing boundary | One cat hisses toward another cat |
| Cat–cat | Friendly greeting | Directed approach, sniffing, nose contact or rubbing |
| Cat–cat | Social play | Reciprocal play or attention to another cat |
| Deer–deer | Forage together | Two deer feeding beside one another |
| Deer–deer | Follow companion | One deer follows another |
| Deer–deer | Herd alert | One deer responds to another becoming alert |

The [research note](RANGER_DUCK_INTERACTIONS.md) gives authoritative behavior sources and observable signals. The scene shows two scripted actors; they have no MuJoCo collision bodies. The duck remains a real MuJoCo body controlled by the pinned pretrained policies. No new training, physical robot control, live animal interaction, or camera recognition is part of this demo.

## Architecture

| Component | Location | Responsibility |
| --- | --- | --- |
| React / Three.js | Browser | One-page interface, scripted animals, sequence and playback |
| MuJoCo / ONNX WASM | Same browser | Existing Microduck controller and observed motion completion |
| FastAPI app | Workshop VM | Authentication, interaction queries, evidence-to-action mapping, video proxy |
| Existing VSS | Workshop infrastructure | Ranked retrieval, existing video-model captions, video access |

Keep the original hard borders, typography, colors, scene/evidence columns and stage strip. Desktop evidence can scroll without moving the scene out of view. Species and interaction selectors, Start, Stop/Resume, and Reset remain accessible. The current reference rank, cycle, inferred behavior and controller state explain the automatic sequence.

Credentials and raw storage identities stay on the backend. Video URLs use opaque session-scoped IDs and preserve range requests. Serve the compiled frontend and backend on one origin, or use the development proxy and an SSH tunnel.

## Search behavior

Queries name both animals and their relationship. Cat searches use the existing authenticated archive without a wildlife-only tag, since domestic cats may not carry it. Deer searches retain the observed wildlife tag. A broader search relaxes the interaction wording while retaining the selected species pair.

Use the deployed VSS search API with `top_k: 15`, `llm_top_n: 1`, and the existing authorization scope. Preserve upstream rank when normalizing valid, distinct sources. Do not diversify by parent, promote a lower result into ranks 1–3, or manufacture a missing result.

The deployed endpoint has no advertised retrieval-only flag and requires synthesis for nonempty chunk results. A measured request took 0.24 seconds for embeddings, 7.75 seconds for database retrieval, 2.02 seconds for synthesis, and about 0.83 seconds for remaining work. Database retrieval runs parallel text/visual SQL similarity queries with fresh connections and overfetching. Raising a timeout does not make this path faster.

The backend search budget defaults to 30 seconds; health reports the configured value and the browser allows five seconds of extra grace. Display actual elapsed time. Explicit Replay reuses a previous successful live search for this session, scenario and query scope. It is labeled, expires, and still needs VSS for video. There is no automatic fallback to replay on an error.

## Evidence-derived actions

Use the existing video-model caption to avoid an additional inference call for every result. Require complete source/parent/interval metadata, the correct species pair and an explicit supported interaction. Reject solitary animals, wrong species, ambiguous/negated claims, and unsupported movements. A pair's mere presence does not establish a directed interaction.

| Described behavior | Bounded approximation |
| --- | --- |
| Feeding beside another deer | One `ground_pick` cycle |
| Directed approach, following, supported play movement | `short_walk` |
| Watching a partner, alert pause or hissing boundary without described movement | `stand_hold` |
| Turning the head toward the partner | `head_scan` |

The hissing scene is scripted. A pause is not an actual reproduced hiss. Backward walking did not produce reliable movement in physics checks, so retreat-only clips remain unsupported. Unsupported jumping, grooming, biting and pouncing do not become arbitrary duck movements.

Each candidate exposes its action basis, inferred behavior, reason, evidence ID and maximum duration. Caption inference never becomes a visual review. Exact private manifests remain available for reviewed references, but an old solitary-deer review does not establish an interaction. Stale or contradictory reviews must not silently become inferred approvals.

## Automatic sequence

After a successful search, take only original ranks 1–3. Automatically show each supported reference, attempt muted playback and await its actual controller completion before advancing. Keep unavailable slots visible with a skip reason. If all three are unsupported, show an explanation and stay still.

Repeat the same evidence sequence until Stop, Reset, a species/scenario change, a replacement search, or page teardown. Stop/Resume does not trigger a new search. Pause when the tab is hidden. Recenter between cycles through the simulator adapter while preserving the animal scene and without firing another encounter event.

Never overlap movements. Reset and cancellation invalidate both pending searches and actions. Controller recovery, failed playback, missing evidence and timeouts have visible outcomes; they do not produce fabricated success.

## Verification

Check query specificity and source rank preservation, caption inference and negation, review compatibility, replay/session scope, and range playback in backend tests. Check sequence order, skips, cancellation, pause/resume and stale result handling in frontend tests. Verify new primitives using actual MuJoCo physics, then run at least one live cat interaction sequence through the browser with no per-action clicks. Build the production frontend and check that development-only instrumentation is omitted.

Archive availability remains an external input. The initial cat queries found real paired observation/head-turn clips, while the first deer co-foraging top three described solitary animals. A missing interaction must remain visible instead of being inferred from the requested scenario.
