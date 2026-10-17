# Ranger Duck implementation plan

Current scope, updated 17 October 2026: one page combines one fixed animal outside the duck arena, a roaming physics-simulated duck, live archive search, and the three highest-ranked compatible video actions. This supersedes the original manual-selection/Copy flow. The user selected cat–cat and deer–deer reference interactions.

The implementation follows the [design handoff](../apps/ranger-duck/design/README.md), with added species/interaction controls and automatic sequence status. See the [API contract](RANGER_DUCK_API.md), [behavior research](RANGER_DUCK_INTERACTIONS.md), and [startup instructions](../apps/ranger-duck/README.md).

## Inputs and outputs

| Stage | Input | Output |
| --- | --- | --- |
| Choose encounter | Cat or deer, plus one interaction | One stationary animal outside the box, facing the duck |
| Start | Selected catalog entry | Encounter ID, focal animal, same-species partner, behavior hint |
| Retrieve | A query describing that species pair and interaction | Actual ranked VSS segment results and measured latency |
| Interpret evidence | Each returned segment's video-model caption and provenance | A supported bounded action, or a visible reason to skip |
| Run sequence | First three compatible actions in retrieval order | Approach the fixed animal, play a reference and perform its action |
| Repeat | The same compatible action queue | Roam between passes, then approach again; no reset or new search |
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

The [research note](RANGER_DUCK_INTERACTIONS.md) gives authoritative behavior sources and observable signals. The scene shows one animal at a fixed position outside the yellow box. It may animate its posture and face the duck but does not translate. The duck roams inside the arena when no evidence action is running, approaches the animal before responding, and continues with the same physics body. Navigation is labeled separately from video-induced behavior. The scripted animal has no MuJoCo collision body. The duck remains a real MuJoCo body controlled by the pinned pretrained policies. No new training, physical robot control, live animal interaction, or camera recognition is part of this demo.

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

Use the deployed VSS search API with `top_k: 15`, `llm_top_n: 1`, and the existing authorization scope. Preserve upstream rank when normalizing valid, distinct sources. Filter out incompatible results, then choose the first three remaining actions in retrieval order. Preserve each source rank separately from its action-queue position; source rank 4 can become action 2 when earlier results are incompatible. Do not manufacture missing actions.

The deployed endpoint has no advertised retrieval-only flag and requires synthesis for nonempty chunk results. A measured request took 0.24 seconds for embeddings, 7.75 seconds for database retrieval, 2.02 seconds for synthesis, and about 0.83 seconds for remaining work. Database retrieval runs parallel text/visual SQL similarity queries with fresh connections and overfetching. Raising a timeout does not make this path faster.

The backend search budget defaults to 30 seconds; health reports the configured value and the browser allows five seconds of extra grace. Display actual elapsed time. Explicit Replay reuses a previous successful live search for this session, scenario and query scope. It is labeled, expires, and still needs VSS for video. There is no automatic fallback to replay on an error.

## Evidence-derived actions

Use the existing video-model caption to avoid another inference request. Require complete source/parent/interval metadata, the selected animal species and an explicit supported behavior. Single-animal footage is usable: interaction wording constrains the search query, not action eligibility. A solitary feeding deer, a walking cat, and shared attention can all supply actions. Describe the actual returned behavior without claiming the requested interaction occurred. Ambiguous or negated behavior, wrong species, incomplete metadata and unsupported movement remain ineligible.

| Described behavior | Bounded approximation |
| --- | --- |
| Feeding or foraging, alone or beside another animal | One `ground_pick` cycle |
| Directed approach, following, supported play movement | `short_walk` |
| Watching a partner or object | `head_scan`, labeled as an attentive head-turn approximation |
| Alert pause or stationary hissing boundary | `stand_hold` |
| Turning or raising the head | `head_scan` |

The hissing scene is scripted. A pause is not an actual reproduced hiss. Backward walking did not produce reliable movement in physics checks, so retreat-only clips remain unsupported. Unsupported jumping, grooming, biting and pouncing do not become arbitrary duck movements.

Each candidate exposes its action basis, inferred behavior, reason, evidence ID and maximum duration. Caption inference never becomes a visual review. Exact private manifests remain available for reviewed references, including solitary-animal behavior; a valid feeding review does not need to attest to a pair. Stale or contradictory reviews must not silently become inferred approvals.

## Automatic sequence

After search, filter all returned candidates for supported actions, preserve retrieval order, and take up to three. Display action positions 1–3 with their original source ranks. Incompatible clips do not occupy a card or loop slot. Show the actual queue size if fewer than three actions qualify. If none qualify, keep the duck roaming and explain why no evidence action is available.

Before an evidence action, navigate toward the fixed animal, settle and then execute the bounded motion. Between passes, roam without resetting physics or sending another search. Navigation and evidence actions never run at the same time.

Repeat until Stop, Reset, a changed scenario, replacement search or teardown. Stop also halts roaming and approach. Pause while hidden and resume on return only when visibility caused the pause. Manual Stop and reference inspection remain paused. Only explicit Reset or a new encounter resets the body; clip and cycle transitions preserve it.

Never overlap movements. Reset and cancellation invalidate both pending searches and actions. Controller recovery, failed playback, missing evidence and timeouts have visible outcomes; they do not produce fabricated success.

## Verification

Check query specificity and source rank preservation, caption inference and negation, review compatibility, replay/session scope, and range playback in backend tests. Check compatible-action selection, preserved source ranks, navigation cancellation, pause/resume and stale result handling in frontend tests. Verify new primitives using actual MuJoCo physics, then run at least one live cat interaction sequence through the browser with no per-action clicks. Build the production frontend and check that development-only instrumentation is omitted.

Archive availability remains an external input. The initial cat queries found observation/head-turn clips, while deer co-foraging queries returned solitary deer. Both can supply supported actions under the current policy; the description must still reflect what the footage actually contains.
