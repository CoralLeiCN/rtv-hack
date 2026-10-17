# Ranger Duck frontend

React, TypeScript and Vite implement the design in `../design/`. One shared
MuJoCo/ONNX simulator contains Microduck and one scripted cat or deer. The
pretrained duck controller, procedural animal models and camera are preserved.

Use Node 22.12 or newer:

```bash
npm ci
npm run assets
RANGER_BACKEND_URL=http://127.0.0.1:18000 npm run dev
```

The Vite proxy defaults to `http://127.0.0.1:8000`. Only its target belongs in
`RANGER_BACKEND_URL`; archive credentials remain on the backend. Health
establishes the browser session before Start is enabled. Simulator binaries
under `public/simulator/` are downloaded with pinned SHA256 verification and
are not committed.

```bash
npm test
npm run build
```

The backend can serve the resulting `dist/` directory. See
[the current wire contract](../../../docs/RANGER_DUCK_API.md) for deployment and
session behavior.

## One page and one controller

Choose Cat or Deer, a scenario preset and optionally edit the intent. Start
creates one `/demo-api/runs` session. Query planning starts alongside the
animal's appearance and proactive approach; it never waits for navigation.
Both Loop settings use the same query, VSS retrieval and batched action planner.
The query reason and measured Query / VSS / Actions timings remain visible.

- **Loop off:** repeat the issued queue, preserving the query and references.
  No automatic search or agent call occurs between passes.
- **Loop on:** after all actions in the current queue complete and their
  outcomes are acknowledged, the backend chooses a different interaction preset
  for the same species, then creates a fresh query and queue using that context
  and live history. The first round uses the user-selected preset.
- Toggle changes take effect at a queue boundary; they do not replace an
  in-progress action or trigger a second execution controller.

The current round's interaction is shown separately from the original preset
and optional intent. Once its query plan arrives, the same animal actor adopts
that interaction before VSS retrieval begins; actor identity, navigation and
duck physics remain continuous. Replay restores its recorded interaction. The
new ambient behavior supplies search context, not evidence for a duck action.

`session.ts` owns requests, playback, movement, cancellation and progression.
`sessionApi.ts` provides the shared run contract. The simulator stays mounted;
only explicit Reset resets the duck's physical pose. New intent/animal runs
replace the single companion while preserving duck physics.

## Grounded queue and playback

The backend retrieves 15 candidates and validates one batch plan. Up to three
compatible active actions execute in original archive order. Cards show queue
positions 1–3 and their original source ranks separately. Unsupported clips do
not fill empty slots. Walking/turning, beak dipping, head nodding and sitting
then standing are eligible; `head_scan` and `stand_hold` remain controller
capabilities but are excluded from evidence selection.

Each action waits for the duck and animal to settle in their interaction
positions. Actual video playback starts the grounded roles. Advancement waits
for the video to end, the bounded companion animation to finish, observed duck
completion, and the server's outcome acknowledgement. A blocked autoplay shows
Play and cannot start a movement. An individual-animal clip leaves the scene
companion standing; it does not invent a second observed animal. Caption-derived
approximations remain distinct from visually reviewed evidence.

Pause immediately cancels playback, movement and pending work. Resume restarts
only an interrupted reference with a new attempt ID; completed queue items
remain completed. If planning was cancelled, Resume replans. A late response
cannot overwrite the active generation. Hidden tabs pause automatically and
resume on return only when visibility caused the pause. Manual Pause remains
paused. Selecting a card pauses for evidence inspection.

Preset and intent edits are available while paused and require Start new run.
They do not silently change the existing queue. Reset clears the run and resets
the simulator. Navigation, evidence movement and waiting for playback have
separate visible status, and actual completion is captured before navigation
changes controller state.

## History and replay

The recent outcome list records query reasons, source ranks, attempted actions
and actual status. Replay saved round uses the same player and coordinator
without new inference or retrieval; it is explicitly labeled and stops after
one queue. Replay outcomes do not affect live agent history. Resume after a
finished replay plans a fresh live round. Footage still streams from VSS, so
replay is not an offline backup.

Archive timestamp formatting adapts the existing search app's `web/api.js`
millisecond-preserving formatter. Playback retains that app's stream disposal
and explicit retry behavior. Evidence details include returned dataset IDs only
when supplied by actual clip metadata, never inferred from requested filters.
