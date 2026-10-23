# Ranger Duck frontend

React, TypeScript and Vite render one shared MuJoCo/ONNX simulation containing
MicroDuck and one scripted cat or deer. Follow [application startup](../README.md#run)
and the [design guide](../design/README.md).

Use Node.js 22.12+. Install dependencies with `npm ci` in this directory
(or the root-relative command in [development](../../../docs/development.md)).
The Vite proxy uses Ranger Duck's default backend address. Override it with
`RANGER_BACKEND_URL` as described in [development](../../../docs/development.md#run-locally).
Only the proxy target belongs in that variable; credentials stay on the backend.

## Code map

| File | Responsibility |
| --- | --- |
| [App.tsx](src/App.tsx) | Unified page, controls and visible state |
| [session.ts](src/session.ts) | Requests, playback, motion, cancellation and progression |
| [sessionApi.ts](src/sessionApi.ts) | Unified run client and outcome contract |
| [ReferencePanel.tsx](src/components/ReferencePanel.tsx) | Caption, rank and evidence display |
| [MicroduckScene.tsx](src/simulator/MicroduckScene.tsx) | Persistent simulator and action coordination |
| [adapter.ts](src/simulator/adapter.ts) | Bounded primitives, navigation and observed physics completion |
| [animalMotor.ts](src/simulator/animalMotor.ts), [clearing.ts](src/simulator/clearing.ts) | Scripted animal movement and settling |
| [upstream/](src/simulator/upstream/) | Pinned simulator source and attribution |

Health establishes the browser session before Start. The simulator stays mounted
across clips and rounds; only explicit Reset resets the duck. Capture actual
completion before navigation changes state, and reject late async responses.
The existing VSS label and `vss_search_ms` field mean archive retrieval.

[Runtime behavior](../../../docs/reference/behavior.md) owns execution and replay;
[the API reference](../../../docs/reference/ranger-duck-api.md) owns wire formats.
Archive timestamps add the segment offset to local video time; do not seek a cut
video to its parent offset. Playback retains the simple UI's millisecond-preserving
formatting, stream disposal and explicit retry behavior. Dataset IDs come from
returned metadata, never requested filters.

Run `npm test` and `npm run build` here. The backend can serve the resulting
`dist/` directory. For browser checks and pinned asset verification, see
[testing](../../../docs/testing.md); for movement limits see
[the simulator reference](../../../docs/reference/simulator.md).
