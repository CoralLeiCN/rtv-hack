# Ranger Duck

One page for a scripted wildlife encounter, live archive retrieval, reference playback, and evidence-guided imitation by a physics-simulated Microduck. The interface follows the [design handoff](design/README.md); the scene uses the official Microduck MuJoCo/ONNX controller.

See the repository README for the [tech stack](../../README.md#ranger-duck-tech-stack)
and [agentic search architecture](../../README.md#how-agentic-search-works), including
Codex login, search tool calls, reranking, and the remaining frontend integration.
Encounter mode uses direct VSS search. The additional Agent Loop mode connects
Codex query and response decisions to archive search and actual simulator outcomes.

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

## Agent Loop mode

1. Install and sign in to Codex CLI on the backend host using the
   [backend instructions](backend/README.md#agent-loop-mode). Configure VSS as for
   the existing demo.
2. Select **Agent Loop mode**, enter an initial prompt, and choose Cat or Deer.
   The visible species selector determines archive scope and shows the matching
   single animal companion beside the duck. The animal and duck represent the
   two video roles; the companion remains visible while paused.
3. Turn the loop on. Codex generates a query, selects a real eligible clip and a
   two-role plan. Playback runs the companion animation and the duck action in
   the chosen order, with caption excerpts explaining each role.
4. Playback, companion animation, and actual duck controller completion must finish. The outcome feeds
   the next query automatically. The panel shows the query, evidence, chosen
   response, and measured outcome.
5. Turn the loop off to stop. Resume uses preserved context with a fresh search;
   Reset or a changed prompt/species starts a new session. Hidden tabs pause and
   require explicit resume. Switching modes stops the active controller.

Queries still ask for two cats or two deer interacting. The top 10 results reach
Codex in archive order even when they show only one animal or are weak matches.
Expand **Search results** to see those candidates and any execution limitations.
The duck approximates the counterpart animal’s caption-described behavior.
Sparse clips stay playable with a labeled neutral pause when two roles cannot
be assigned.
Caption interpretation remains labeled as inferred. No-match recovery is bounded,
failed movement pauses the loop, and no cached clip silently replaces a search.

## Existing encounter demo flow

1. Wait for the simulator and backend catalog. Choose Cat or Deer, then an interaction.
2. Press Start. One animal appears outside the box and triggers one live interaction search. The duck roams while waiting; the animal can patrol outside the east side of the box.
3. The demo filters all returned clips and chooses the first three compatible actions in retrieval order. The animal returns to its anchor and faces the duck; the duck then approaches, plays each reference muted and performs its video-induced movement. No Copy click is needed.
4. The sequence repeats, with roaming between passes and the same duck body continuing throughout; physics is not reset. Stop pauses it, Resume starts a fresh cycle, and Reset clears the encounter. Changing species or interaction cancels the previous sequence.

The backend derives actions from the returned clips' existing video-model captions and labels them as inferred. Each needs the selected species, a supported caption behavior and complete provenance. Single-animal clips are usable; only the search query requires interaction wording. Incompatible clips are filtered out before selecting the top three actions, and original source ranks remain visible. If no action qualifies, the duck continues roaming without inventing an imitation.

The six supported motions are bounded walking/turning, beak dip, head scan, vertical head nod, sit-and-stand, and standing hold. Within each clip, the classifier prefers supported active behavior in the order walk → pick → nod → scan → sit → hold; it preserves retrieval rank and exact current reviews. Sitting requires explicit sitting evidence, and a nod requires vertical head-motion evidence. Stop cancels the sequence while allowing a seated duck to stand safely. See the [complete motion inventory](../../docs/RANGER_DUCK_ANIMATION.md).

The animal motor improves patrol, gait and interaction settling while retaining the original articulated procedural cat/deer. The requested animal-model replacement was canceled; no generated model or external animal asset setup is required.

Cat encounters cover hissing boundaries, greetings and social play; deer encounters cover co-foraging, following and group alert. A scripted hissing pose does not claim the retrieved clip contains a hiss. The movement explanation shows what the returned caption actually supports. See the [behavior research and limitations](../../docs/RANGER_DUCK_INTERACTIONS.md).

The committed visual-review manifest remains empty; real source identities stay private. A manifest is optional for caption-derived interaction actions. An exact current solitary-feeding review can authorize its behavior without claiming a deer–deer interaction. The [review workflow](backend/README.md#interaction-evidence-and-optional-human-review) remains available for exact reviewed evidence.

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
