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
For the local demo backend on port 18000:

```bash
RANGER_BACKEND_URL=http://127.0.0.1:18000 npm run dev
```

Only the proxy target belongs in this environment variable. VSS credentials
stay on the backend. The browser awaits the health response to establish its
session before allowing a search. The encounter catalog supplies scenario
labels; the agent generates each initial query on demand.

The browser follows health budgets for query planning (up to 60 seconds),
archive search plus action planning (up to 180 seconds), and replay, with five
seconds of response grace. Query generation and search/action planning are
labeled separately. Stop and Reset cancel immediately and invalidate late
responses, including the backend's pending decision process.

```bash
npm test
npm run build
```

The `dist/` directory can be served by the backend using its configured static
directory. Run the asset command before building: generated runtime binaries
under `public/simulator/` are verified against pinned SHA256 values and are not
committed. See the simulator setup and attribution beside the asset script.

Choose Cat or Deer and an interaction, then press Start. One animal of the
selected species stays outside the marked box. Microduck faces and approaches the animal during query planning and
archive search. The animal returns and settles
at its interaction mark before Microduck approaches for each evidence action.
Queries cover interactions or similar individual behavior; an explicitly
described supported single-animal motion can authorize an approximation. The complete
ranked response is filtered for compatible actions before choosing up to three.
For example, source ranks 2, 4, and 7 can become actions 1, 2, and 3; each card
preserves its original source rank. Unsupported references do not appear as
cards or empty queue slots. Fewer than three compatible actions are shown as
the actual count. The current video is selected automatically and attempts
muted, looping playback.

Within each caption, supported active behavior takes priority over stillness.
The six evidence actions are walking/turning, beak dipping, head nodding, head
scanning, sitting then standing, and a standing hold. The complete native
controller inventory and tested limits are in
[the motion reference](../../../docs/RANGER_DUCK_ANIMATION.md).

Duck physics continue across reference and cycle boundaries: no pose reset,
scene reload, or new search occurs. The duck maintains attention between cycles and when no
compatible action is found. Scripted navigation has its own visible status;
it is not presented as a video-derived action. Every action waits for arrival,
physics readiness, and the previous action's observed completion. The active
action and elapsed time remain visible, including an intentional standing hold.
Stop, Reset,
scenario changes, or selecting a reference for inspection cancel the loop.
Hiding the tab pauses both navigation and evidence motion and clears the active
action; returning resumes only the loop or attention that visibility paused.
Manual Stop stays stopped. Resume starts a fresh cycle at action 1 using the same search evidence and duck
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
