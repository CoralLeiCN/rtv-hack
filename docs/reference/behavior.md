# Ranger Duck runtime behavior

One page and one agent pipeline support encounter and adaptive Loop behavior.
The [archive specification](../spec.md) defines retrieval, ingestion and media
storage; the [status](../status.md) records remaining work and validation limits.

The interface follows the [design guide](../../apps/ranger-duck/design/README.md).
See the [API contract](ranger-duck-api.md), [startup guide](../../apps/ranger-duck/README.md),
[behavior research](interactions.md) and [motion inventory](simulator.md).

## One page, one Loop toggle

Keep Cat/Deer, the encounter presets, an editable intent, Start/Pause/Resume,
and Reset. Keep the simulation and movement HUD on the left, with query,
three active reference cards, current playback and action mapping on the right.
There is one persistent duck and one animal outside its arena.

- Loop off is Encounter behavior: repeat the same up-to-three-action queue without a new search.
- Loop on randomly chooses a different interaction for the same animal after the queue finishes, then plans a fresh query using that interaction, the original intent and actual outcomes. The first round uses the selected preset.
- Changing the toggle preserves the current action and queue. It controls the next round boundary; an already-running search may finish.
- Both toggle positions use the same query model, archive settings, batch action/role planner, validation and execution coordinator.
- A changed intent/species creates a new run without replacing the physics body. Only explicit Reset resets the duck.

If a Loop setting update fails, pause the run and retain the selected value.
Resume retries that value once and waits for the backend acknowledgement before
restarting execution. Another failure leaves the run paused for a later Resume;
Pause or Reset during the retry prevents execution from restarting.

## Inputs and outputs

| Stage | Input | Output |
| --- | --- | --- |
| Start run | Animal, catalog preset, optional intent, Loop setting | Session-scoped run and original intent |
| Plan query | Current interaction, run intent and bounded actual-outcome history | Current scenario snapshot, required interaction and solitary-behavior query branches joined with OR, and a brief reason |
| Retrieve | Validated generated query and species tags | Up to 15 ranked archive segments and measured retrieval duration |
| Batch plan | Eligible captions, exact reviews and bounded motion choices | Grounded duck actions and companion role plans, or skip reasons |
| Select | Validated candidates in archive order | First three compatible active actions, preserving original source ranks |
| Execute | Video, duck action and supported companion role | Actual playback, physics and scripted-companion completion |
| Acknowledge | Run/round/action/attempt identity and observed outcome | Next authorized attempt, repeated queue, or permission to plan the next round |

The scenario and search query cannot supply missing action evidence. Single-animal
footage is valid when its caption supports a selected-species motion. Two-role
plans need caption evidence for both roles. The duck takes the more active
supported role; a solitary clip leaves the companion standing without claiming
a second observed video animal.

A turn is one round of up to three actions. Later Loop rounds choose among the
other same-species presets, so adjacent rounds never repeat the interaction.
Changing the animal's scripted interaction preserves the existing actor, its
position and the duck's physics state. Show the current interaction beside the
query; preserve each round's scenario in history and saved replay. This random
selection adds no model call or archive request.

## Shared architecture and latency

The browser runs React, Three.js, MuJoCo WASM and the existing ONNX controller.
The local FastAPI backend runs Codex CLI with `gpt-6-luna` for query and action
decisions. The
independent archive provides retrieval and playback using Qdrant, Neon Postgres
and local media; Cosmos and EmbeddingGemma 2 support ingestion and search.

One RunService owns planning, retrieval, queue/attempt state, outcome history,
cancellation and replay. Both toggle settings use two agent calls per normal
new round: query generation and one batch action/role plan. All captions with valid provenance and review constraints require model action
planning, including passive or ambiguous descriptions. There is no per-clip agent
call. An all-blocked result skips the batch decision and pauses. Unified runs
have no hidden model/search retries; a broader search is an explicit user retry.
The outcome acknowledgement issues the next queued attempt directly.

Query planning begins alongside animal-facing/approach navigation. Navigation
must not delay the archive request. Expose query_agent_ms, vss_search_ms and
action_agent_ms separately, plus total elapsed time. Shared code and call counts
remove mode-specific overhead; actual model/network times remain variable.

Use ArchiveClient with top_k 15 and server-side Bearer authentication. Search
embeds the query and retrieves indexed caption vectors; it does not generate a
summary. Cat requests use tags meow-10k and cat-behavior. The
requested dataset identity is hf-smgjch-meow-10k, but dataset_id is not an exposed
filter and absent result metadata must not be fabricated. Deer uses wildlife.

## Evidence and action selection

Code requires complete source/parent/interval metadata and enforces exact current
review constraints, caption quotation, command types and duration limits. Stale,
invalid or contradictory reviews veto inference. Keep caption inference visibly
distinct from visual review.

Codex with `gpt-6-luna` decides whether each full caption describes a supported
selected-species action, which actor performs it, and whether evidence is negated
or uncertain. It chooses among short_walk, ground_pick, head_nod and sit_cycle,
or skips the clip with a reason. There is no phrase classifier or fixed
within-caption action priority in the runtime path. A walk away may be ordinary
forward locomotion; the agent distinguishes that from unsupported reverse steps.
Head scan and standing hold remain internal controller capabilities. Rolling,
jumping, climbing, grooming and lying have no enabled imitation command.
Planner instructions explicitly distinguish unspecified head motion from a
vertical nod and grooming a body part from feeding. A positively described
seated pose supports sit/stand even when no sit-down transition is described.

The agent receives recent-clip flags and actual outcome history. It should avoid
pointless repetition but may explain a useful repeat when alternatives are absent.
Recency does not automatically veto a reference. The application verifies exact
quotes and command/role compatibility, not the semantic correctness of the model's
interpretation; real model evaluation remains necessary.

Filter before taking three; retain archive rank separately from queue position.
Show the actual count when fewer qualify. Bound no-match recovery and report
failure explicitly; never silently substitute cached evidence or a passive hold.

## Continuous execution and outcomes

Before each action, settle the animal at its outside-arena anchor, align the duck
inside its arrival corridor, and wait for balance. Start the grounded roles when
video playback begins. Their timing may be together, companion_first or duck_first.
Advance only after playback, duck motion and required companion animation finish.
Blocked autoplay shows a Play control and cannot start movement.
Capture completed physics telemetry before navigation changes the controller state.

The same body and simulation clock continue across references, passes, fresh
searches and toggle changes. Navigation is labeled separately from imitation.
No overlapping commands or assumed timer-based success are allowed.

Use run, round, action and attempt IDs. Acknowledgements are idempotent; stale
or conflicting outcomes cannot advance the queue. Pause cancels pending work,
video, navigation and both roles, retaining acknowledged entries. An in-progress
sit uses its native standing return. Resume restarts an interrupted entry from
the beginning with a new attempt ID; a paused/expired search requires planning
again. A visibility-only pause can resume automatically when the tab returns;
manual Pause and reference inspection remain paused. Preset and intent edits
while paused require Start new run; they do not silently replace the queue.

Reference access has a fixed lifetime (30 minutes by default). Before issuing
another action, the backend checks the round's expiry. An expired queue pauses
with `references_expired`, retaining the completed outcome and issuing no new
attempt. The UI explains that Resume searches for fresh references. There is no
automatic search or extension of old playback capabilities. Successful run
requests renew the owning browser's session cookie, independently of reference
expiry; an idle expired session still requires a new run.

## Recorded rounds

Replay saved round uses recorded decisions through the same queue/player/controller.
It issues fresh playback capabilities, makes no agent/search call, stays clearly
labeled as recorded and ends paused after one pass. Replay outcomes do not enter
live planning history. Resume after a finished replay plans a fresh live round.
Playback still needs archive access. Snapshot identity belongs
to the run/round and its intent/scope, not only a scenario name.

## Verification

Backend checks cover equal search/model call counts with Loop on/off, scope and
rank preservation, passive/invalid evidence exclusion, grounded role plans,
real-outcome requirements, idempotent acknowledgements and cancellation.
Frontend checks cover boundary-only toggle behavior, fixed-queue repeat versus
fresh planning, playback/motion gating, pause/resume and stale response handling.
Run a production build and verify live cat searches with both toggle settings,
including a second adaptive round and continuous physical returns. Measure
per-phase timings rather than promising identical remote response times.
