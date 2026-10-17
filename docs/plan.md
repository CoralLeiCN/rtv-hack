# Ranger Duck: additional Loop mode implementation plan

Status: implemented with automated contract coverage and local browser checks.
Live Codex/VSS end-to-end acceptance remains to be verified in the workshop
environment. Initial cat/deer scope and supported responses are confirmed.
This plan implements the new mode in [intent.md](intent.md) and
[spec.md](spec.md). It does not replace the existing encounter mode described in
[RANGER_DUCK_PLAN.md](RANGER_DUCK_PLAN.md).

## Scope and mode boundaries

| Concern | Existing encounter mode | New Loop mode |
| --- | --- | --- |
| Starting input | Species and catalog interaction | User's initial prompt |
| Search | Direct, scenario-derived VSS query | Agent-generated query |
| Selection | First three compatible actions in archive order | Agent selects an eligible retrieved clip |
| Repetition | Repeat the same evidence sequence | Search again using the duck's actual reaction |
| Controls | Existing Start, Stop/Resume, Reset | Prompt, Loop toggle, status, Reset/retry |

Preserve existing encounter behavior and API semantics. Share authentication,
video playback, evidence validation, simulator primitives, and completion
tracking where appropriate. Compatible-action selection and repetition without another
search remain rules of the existing mode only.

Enabling Loop mode starts its first cycle when a valid prompt is available.
Turning it off stops progression and settles the duck; it does not automatically
start the existing encounter sequence. Switching modes first invalidates pending
work and settles any active movement. Only one mode owns the simulator at a time.

## Confirmed scope and reaction policy

The user confirmed queries for two cats or two deer interacting. Loop mode
returns the top 10 archive results in original order, including single animals
and weak matches. Do not apply the encounter imitation classifier or a species
presence gate. Give Codex the full candidate list and show it in the Loop panel.
If fewer than 10 results exist, return those results without padding. Keep
unexecutable entries visible with reasons rather than substituting lower ranks.

The scene uses one animal companion plus the duck in both modes. In Loop mode,
Codex assigns the first video animal to the companion and the counterpart to the
duck. Its structured plan names each subject, quotes exact caption evidence,
chooses one supported companion behavior and one bounded duck primitive, and
specifies simultaneous or sequential order. The duck approximates the other
animal's observed action; it is not a third participant choosing an unrelated
reaction.

Companion behaviors are standing, alert, walking, approach, retreat, and feeding;
cats additionally support hissing, greeting, and play. Each scripted animation
is capped at 3000 ms. Duck primitives remain `stand_hold`, `head_scan`,
`short_walk`, and `ground_pick` with existing limits and actual physics completion.

Keep sparse clips selectable. If two supported roles are not established, label
`insufficient_evidence` and normalize both roles to neutral standing without
claiming a counterpart was observed. Validate caption excerpts, distinct role
subjects, action vocabularies, provenance, session/cycle ownership, and outcome
consistency. Interpretation remains caption-inferred, not visually verified.

Begin role actions only after playback starts. Wait for playback, companion
animation, and duck action completion before the next search. Cancel both roles
on stop/reset/mode switch; a delayed second role must not start after cancellation.
Store the role plan and both execution outcomes in next-search history. Show
subjects, excerpts, approximations, ordering, and neutral-fallback status in the UI.
Encounter mode retains its direct search/sequence contracts with a single scene
companion; its caption imitation eligibility rules remain unchanged.

## One interaction cycle

1. Capture the original prompt and create a loop session.
2. Give the agent that prompt, recent interaction history, available movement
   capabilities, and the previous simulator outcome when one exists.
3. Have the agent query the existing archive through a bounded search tool and
   select one eligible result with an explanation. Record the actual query and
   original retrieval rank separately from the agent's selection.
4. Validate that the selected clip belongs to this search and session and that
   its proposed reaction satisfies the chosen interpretation and evidence rules.
5. Play the selected clip and execute the supported reaction. Track playback
   outcome and actual simulator completion; a duration limit is not completion.
6. Record what the duck actually did and its resulting state. Only after the
   cycle has finished successfully may the agent begin the next search.
7. Repeat while Loop mode is enabled. If a cycle fails, follow bounded recovery
   rather than recording an invented successful interaction.

Use the original prompt to maintain direction and recent history to avoid clip
repetition. A successful next cycle requires a fresh search and a new clip, not
an automatic replay of the previous results.

## State and API additions

Keep the existing `/demo-api/search` contract, including its `live` and `replay`
values, unchanged. Add a separate loop-session contract; endpoint names and
schemas are documented in `RANGER_DUCK_API.md`.

The contract provides operations to start a session, obtain the next selected clip
and reaction, submit a completed cycle's outcome, and cancel the session. Bind
sessions to the existing browser session and use cycle IDs to reject stale or
duplicate outcomes. Cancellation must invalidate results even when an upstream
request cannot be interrupted immediately.

Store the initial prompt, current cycle, recent queries, selected evidence,
reaction plans, actual outcomes, and failure counters in bounded server-side
session state. Browser-reported outcomes must reference the action issued for
that cycle and pass schema validation. They are simulator telemetry, not proof
of physical-world behavior.

Return the selected clip through existing opaque playback capabilities. Keep
credentials and raw source identities on the backend. Define an overall agent
cycle deadline and expose it to the frontend; the current single-search timeout
must not silently become the budget for an unbounded agent run.

## Implementation sequence

### 1. Establish mode ownership and contracts

- Add explicit encounter/loop mode state without changing the existing sequence.
- Define loop session, cycle, selection, reaction, and outcome schemas.
- Add generation/cycle checks for stale searches, media callbacks, and actions.
- Document the separate loop API and implement response eligibility rules for
  the confirmed action interface without changing existing imitation rules.

### 2. Connect the agent to archive search

- Use Codex CLI structured query and action decisions around backend-owned VSS
  retrieval. The earlier MCP prototype is documented separately and is not used
  by this implementation.
- Use the configured agent runtime and server-held VSS authentication.
- Bound tool calls, runtime, history, and result selection per cycle.
- Validate selected IDs against actual retrieved candidates. Preserve original
  rank as provenance. Request top_k=10 and preserve those ten slots without
  applying the existing mode's top-three restriction or content filters.
- Treat retrieved captions as evidence data, not instructions to the agent.
- Return the actual query and a concise selection/continuation explanation.

### 3. Capture simulator outcomes

- Reuse supported primitives and the simulator's actual completion signals.
- Capture the executed primitive, completion/failure/cancellation, and available
  resulting pose or controller state. Do not invent unavailable observations.
- Keep planned behavior separate from measured execution.
- Apply the confirmed Codex-selected response policy while retaining provenance and
  movement constraints. Label caption-based interpretation as inferred.

### 4. Build the loop coordinator and controls

- Add prompt input and the Loop toggle, with searching, playing/reacting,
  settling, and paused/error states.
- Show the current query, clip, reaction outcome, cycle number, and explanation
  connecting the next search to the previous interaction.
- Allow one active cycle and one simulator action at a time.
- Gate progression on playback success and simulator completion. Show blocked
  autoplay and offer a user playback action rather than silently continuing.
- On toggle-off, mode switch, Reset, or a submitted replacement prompt, cancel
  pending work and safely settle the simulator. Editing draft text alone does
  not restart a session.
- Pause on a hidden tab, following the existing demo convention. The
  behavior is explicit user resume, with no unattended searches while hidden.

### 5. Bound recovery and repetition

- For empty searches, unsupported evidence, or repeated clips, let the agent
  select another candidate or refine its query within a bounded attempt budget.
- Pause after repeated unsuccessful attempts and expose Retry and prompt editing.
- On a simulator failure, settle and pause rather than immediately issuing
  another movement. Preserve the failure outcome for an explicit retry.
- Never substitute replay or fabricate evidence to keep the loop moving.
- Implemented initial limits: two search calls per agent cycle, three consecutive
  failed attempts before pausing, and five recent completed cycles in context.
  These are bounded implementation defaults for the new mode.

### 6. Verify and document

- Preserve regression coverage for the existing mode's compatible-action ordering,
  unchanged repeat behavior, Stop/Resume, and replay semantics.
- Test that the next agent request contains the actual prior simulator outcome
  and original prompt, and that no next cycle starts before completion.
- Test invalid selections, duplicate/stale outcomes, unsupported evidence,
  repeated results, bounded failures, and session isolation.
- Test cancellation during search, playback, and motion, including mode switches
  and late responses. Verify only the active mode can command the simulator.
- Run backend tests, frontend tests, and the production build relevant to the
  implementation; verify supported motions in the actual simulator.
- In the configured workshop environment, demonstrate multiple consecutive
  fresh clips with reaction-dependent queries, then stop mid-cycle and verify
  that no later response restarts the loop.
- Update startup documentation and the API contract to describe both modes and
  distinguish implemented behavior from remaining limitations.

## Completion criteria

The existing encounter demo still behaves as before. In the additional Loop
mode, one user prompt starts successive agent searches, real clip playback, and
supported duck reactions. Each new search uses the preceding actual outcome,
the UI explains the connection, and turning the loop off reliably stops further
progression. Failure handling is bounded and visible. No shared ingest pipeline
changes or deployment are required by this planning task.


## Verification record

The backend suite passed 111 tests, the Ranger Duck frontend passed 33 tests,
and the original search frontend passed 13 tests. The production build passed;
Vite retains its existing large simulator-bundle and MuJoCo module warnings.
A local browser test used labeled synthetic clips and a deterministic injected
agent with the real MuJoCo controller. Two consecutive `stand_hold` reactions
completed, playback ended, and both outcomes reached subsequent agent requests.
Toggle-off interrupted a later cycle and returning to encounter mode restored
its controls. This test does not establish live Codex or archive availability.


The top-10 response update passed 117 backend tests and 33 Ranger Duck frontend
tests, plus the production build. Coverage includes pair-query construction,
single-animal/weak-match acceptance, all four response primitives, preserved
rank slots, unavailable/recent candidates, and unchanged encounter rejection
of solitary-animal imitation. Live Codex/VSS acceptance of this update remains
pending.


The two-role implementation passed 123 backend tests and 40 frontend tests,
plus the production build. A browser check used labeled synthetic clips and a
fixed test agent with the real MuJoCo duck controller: two consecutive cycles
completed a companion approach followed by the duck's still observation. Both
companion completion and measured duck telemetry appeared in the next query's
history. This validates orchestration, not live Codex role interpretation or
visual correctness against real footage. Live archive acceptance remains pending.


Latest-main integration: rebased the uncommitted implementation onto `e91f33f`.
Encounter mode now follows main's compatible-action selection (including solitary
behaviors and later ranks), roaming, and outside-arena animal motor. Loop mode
retains its top-10 list and two-role plan; its companion animation also stays
outside the arena, using the shared animal anchor and updated models. Historical
verification notes above describe their original checkpoints, not current
encounter eligibility.
