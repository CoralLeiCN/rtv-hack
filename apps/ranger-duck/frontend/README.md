# Ranger Duck frontend

React, TypeScript, and Vite implementation of the interface in `../design/`.
The shared scene uses the pinned upstream Microduck MuJoCo and ONNX runtime;
the deer is a scripted Three.js actor. No new policy is trained.

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

Start brings the deer into the marked zone, then requests archive references.
Select a card to watch its segment. Copy remains disabled until the backend
returns an eligible reviewed action and the physics controller is ready.
Reset and changed references cancel pending actions; stale search responses
cannot replace a newer encounter.

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

The default backend reference manifest is empty. A full imitation demo requires
reviewing actual footage and configuring that manifest. The frontend never
turns a caption or encounter hint directly into a robot action.
