# Ranger Duck

One page for a scripted wildlife encounter, live archive retrieval, reference playback, and evidence-guided imitation by a physics-simulated Microduck. The interface follows the [design handoff](design/README.md); the scene uses the official Microduck MuJoCo/ONNX controller.

See the repository README for the [tech stack](../../README.md#ranger-duck-tech-stack)
and [agentic search architecture](../../README.md#how-agentic-search-works), including
Codex login, search tool calls, reranking, and the remaining frontend integration.
The current demo uses direct VSS search; the agent prototype is not connected yet.

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

1. Wait for the simulator and backend catalog. Choose Cat or Deer, then an interaction.
2. Press Start. One scripted animal enters, faces the duck, and triggers one live interaction search. The duck takes the partner role from the same-species reference footage.
3. The demo automatically visits original result ranks 1–3, plays each supported reference muted, and performs its video-induced movement. No Copy click is needed.
4. The same sequence repeats with the same duck body and pose continuing between clips and cycles; physics is not reset. Stop pauses it, Resume starts a fresh cycle, and Reset clears the encounter. Changing species or interaction cancels the previous sequence.

The backend derives actions from the returned clips' existing video-model captions and labels them as inferred. Each needs the correct species pair, a supported action in the caption and complete provenance. Shared or parallel activity is labeled separately from a direct social interaction. Unsupported ranks are visibly skipped; lower-ranked clips are not substituted. If none of the top three qualifies, the duck remains still.

Cat encounters cover hissing boundaries, greetings and social play; deer encounters cover co-foraging, following and group alert. A scripted hissing pose does not claim the retrieved clip contains a hiss. The movement explanation shows what the returned caption actually supports. See the [behavior research and limitations](../../docs/RANGER_DUCK_INTERACTIONS.md).

The committed visual-review manifest remains empty; real source identities stay private. A manifest is optional for caption-derived interaction actions. The old private solitary-feeding review does not by itself authorize a deer–deer interaction. The [review workflow](backend/README.md#interaction-evidence-and-optional-human-review) remains available for exact reviewed evidence.

Replay explicitly reuses a previous live result for the current session and search scope. Video still streams from VSS. Other interactions broadens the behavior query while retaining the species pair. No match and Timeout rehearsal controls remain labeled demonstrations without fabricated evidence.

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
