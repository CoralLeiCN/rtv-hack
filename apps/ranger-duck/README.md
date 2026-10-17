# Ranger Duck

One page for a scripted wildlife encounter, live archive retrieval, reference playback, and evidence-guided imitation by a physics-simulated Microduck. The interface follows the [design handoff](design/README.md); the scene uses the official Microduck MuJoCo/ONNX controller.

## Start development

Use Node.js 22.12 or newer, Python 3.11 or newer, and two terminals. From the repository root:

```bash
python3 apps/ranger-duck/scripts/simulator-assets.py
cd apps/ranger-duck/frontend
npm ci
npm run dev
```

The asset script downloads only the pinned simulator assets and checks their sizes and SHA-256 digests. Downloaded assets and build output are ignored by Git. `--check` verifies an existing download without network access.

Start the API in another terminal using the [backend setup](backend/README.md). Without workshop configuration, the app still loads its simulator and encounter catalog; live search reports that configuration is missing. Keep credentials on the workshop VM. For live development, run the backend on VM loopback, forward its port through the existing SSH connection, and point Vite at the forwarded port:

```bash
RANGER_BACKEND_URL=http://127.0.0.1:18001 npm run dev
```

The default backend target is `http://127.0.0.1:8000`. Open the Local URL printed by Vite. All browser requests remain on that page's origin, including video playback and session cookies.

## Demo flow

1. Wait for the simulator and backend catalog to load. Choose Feeding, Walking, or Standing.
2. Press Start. The scripted deer enters the marked zone and triggers a live search.
3. Select a reference. Play or seek its actual segment; the HUD shows segment-local and archive time.
4. Copy becomes available only for a current reviewed reference with a supported action. Completion follows controller state, not a decorative animation timer.
5. Reset clears the encounter and cancels outstanding requests and movements. Late responses cannot change the next encounter.

The shipped reference manifest is empty. To enable imitation, inspect real footage and use the [offline review workflow](backend/README.md#review-actual-evidence-before-enabling-copy). A complete feeding demo was verified against a private reviewed manifest on the workshop VM; see the [verification context](../../docs/RANGER_DUCK_CONTEXT.md#implementation-and-verification) for its temporary location. The three implemented movements are one ground-pick cycle, a short bounded walk, and a neutral stand. Unreviewed, stale, unsupported, and wrong-species results stay playable without authorizing a movement.

Replay explicitly reuses a previous live result from the current browser session and search scope; it is labeled and never replaces an error automatically. Video still streams from the archive, so replay is not an offline recording. Search broader category widens retrieval while preserving the reviewed-species requirement. The No match and Timeout rehearsal controls show labeled UI states without making a request or generating evidence.

## Build and serve one page

```bash
cd apps/ranger-duck/frontend
npm run build
```

Set `RANGER_STATIC_DIR` to the absolute path of `frontend/dist` when starting the backend. That process serves the compiled frontend and `/demo-api` on one origin. Use one backend worker because replay and clip capabilities are held in process memory. Restarting invalidates them. No change to the shared VSS ingest pipeline is required.

## Verify

```bash
cd apps/ranger-duck/backend
.venv/bin/python -m pytest -q
cd ../frontend
npm test
npm run build
```

See the [API contract](../../docs/RANGER_DUCK_API.md), [implementation plan](../../docs/RANGER_DUCK_PLAN.md), and simulator attribution under `frontend/src/simulator/` for integration details. Search latency is measured; the currently deployed VSS service requires one synthesis result even though this app discards that summary.
