# Ranger Duck frontend

React, TypeScript, and Vite implementation of the interface in `../design/`.
The shared scene uses the pinned upstream Microduck MuJoCo and ONNX runtime;
one cat or deer is a scripted Three.js actor facing the duck. No new policy is
trained.

Use Node 22.12 or newer. From this directory:

```bash
npm ci
npm run assets
npm run dev
```

The development server proxies `/demo-api` to `http://127.0.0.1:8000` by default.
For a backend reached through another local SSH-forwarded port:

```bash
RANGER_BACKEND_URL=http://127.0.0.1:18001 npm run dev
```

Only the proxy target belongs in this environment variable. VSS credentials
stay on the backend. The browser awaits the health response to establish its
session before allowing a search. The encounter catalog supplies scenario
labels and queries.

The browser follows the backend health response's `search_timeout_ms` budget
(1–60 seconds) and allows five additional seconds for its response. Missing or
invalid budgets use a 30-second backend budget, giving a 35-second browser
deadline. Reset still cancels immediately and invalidates late responses.

```bash
npm test
npm run build
```

The `dist/` directory can be served by the backend using its configured static
directory. Run the asset command before building: generated runtime binaries
under `public/simulator/` are verified against pinned SHA256 values and are not
committed. See the simulator setup and attribution beside the asset script.

Choose Cat or Deer and an interaction, then press Start. One animal of the
selected species faces Microduck in the marked zone and triggers one archive
search. The archive query still requests cat–cat or deer–deer footage; supported
behavior in those references is approximated by the duck. The duck automatically
performs the supported actions from original ranks 1, 2,
and 3 in order, then repeats that sequence until Stop or Reset. Missing or
unsupported ranks remain visibly skipped; rank 4 never replaces them. The
current video is selected automatically and attempts muted, looping playback.

Duck physics continue across reference and cycle boundaries: no pose reset,
scene reload, or new search occurs. Every action waits for the physics
controller's observed readiness and completion. The active action and elapsed
time remain visible, including an intentional standing hold. Stop, Reset,
scenario changes, or selecting a reference for inspection cancel the loop.
Hiding the tab pauses motion and clears the active rank; returning resumes from
rank 1 only when visibility caused that pause. Manual Stop stays stopped.
Resume starts a fresh cycle at rank 1 using the same search evidence and duck
pose. A stopped encounter/search can be started again. Stale responses cannot
restart a newer encounter.

Replay is explicit and uses a successful live result from the current backend
session for the same scenario and search scope. Its footage still streams from
VSS. It is not an offline backup. No-match and timeout rehearsal buttons show
clearly labeled UI states without sending a request or fabricating clips.

Archive interval formatting adapts the existing search app's `web/api.js`
millisecond-preserving formatter, keeping the design's zero-padded minutes.
Playback also retains that app's explicit video retry and stream cleanup when
changing the selected reference.
The separate Ranger Duck session and evidence API remains authoritative for
playback and imitation.

Actions are authorized by the backend from the returned video evidence. A
human-reviewed action is labeled Reviewed; an allowed caption-derived action
is labeled Caption-inferred and retains its source caption and inference
reason. These are approximations using pretrained duck movements, not learned
animal responses. The frontend never converts an encounter hint directly into
an action or pretends a caption-derived label was visually reviewed.
