# Ranger Duck

One page for a scripted wildlife encounter, live archive retrieval, reference playback, and evidence-guided imitation by a physics-simulated Microduck. The interface follows the [design handoff](design/README.md); the scene uses the official Microduck MuJoCo/ONNX controller.

See the repository README for the [tech stack](../../README.md#ranger-duck-tech-stack)
and [agent flow](../../README.md#how-agentic-search-works). Both Encounter and
Agent Loop modes use the local Codex CLI to generate queries and supported
responses from archive evidence.

## Start the local demo

Use Node.js 22.12 or newer and Python 3.11 or newer. Sign in to Codex on this
Mac with `codex login` and check `codex login status`. Your existing ChatGPT
OAuth login is reused; no OpenAI API key or SSH bridge is needed.

Configure VSS privately in `backend/.env` using `backend/example.env` as the
variable-name template. Live archive access needs `INGRESS_URL`, `USERNAME`
and `PASSWORD`. Without them the simulator loads, but live query/search requests report
missing configuration.

From the repository root, prepare the frontend:

```bash
python3 apps/ranger-duck/scripts/simulator-assets.py
cd apps/ranger-duck/frontend
npm ci
RANGER_BACKEND_URL=http://127.0.0.1:18000 npm run dev
```

Start the API in another terminal:

```bash
cd apps/ranger-duck/backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m uvicorn ranger_duck.app:app --host 127.0.0.1 --port 18000 --workers 1
```

Open the Local URL printed by Vite. Browser API calls and video playback use
that origin and its session cookies. The asset script checks pinned sizes and
SHA-256 digests; `--check` verifies an existing download without network access.
Assets, local `.env`, and build output are ignored by Git.

## Agent Loop mode

1. Install and sign in to Codex CLI on the backend host using the
   [backend instructions](backend/README.md#local-agent-decisions). Configure VSS as for
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

Queries cover selected-species interactions or similar individual behavior. The top 10 results reach
Codex in archive order even when they show only one animal or are weak matches.
Expand **Search results** to see those candidates and any execution limitations.
The duck approximates the counterpart animal’s caption-described behavior.
Single-animal clips can supply an active supported motion with the companion
standing as an unassigned scene animal. Clips supporting only `head_scan` or
`stand_hold` are excluded from selection. Loop mode performs a bounded new
search or reports no compatible active motion; it never substitutes a hold.
Caption interpretation remains labeled as inferred. No-match recovery is bounded,
failed movement pauses the loop, and no cached clip silently replaces a search.

## Encounter demo flow

1. Wait for the simulator and backend catalog. Choose Cat or Deer, then an interaction.
2. Press Start. One animal appears outside the box. The duck faces it and approaches if needed while the agent generates a fresh query covering interactions or similar individual behavior. The generated query and its reason appear before archive search.
3. The agent plans supported actions from the returned captions. The demo validates those decisions and chooses the first three compatible actions in retrieval order. The animal returns to its anchor and faces the duck; the duck then approaches, plays each reference muted and performs its video-induced movement. No Copy click is needed.
4. The sequence repeats with the duck attending to the animal between passes and the same body continuing throughout; physics is not reset. Stop pauses it, Resume starts a fresh cycle, and Reset clears the encounter. Changing species or interaction cancels the previous sequence.

The agent derives actions from the returned clips' existing video-model captions; the backend validates them and labels them as inferred. Each needs the selected species, a supported caption behavior and complete provenance. Both interaction clips and similar single-animal behaviors are usable. Incompatible clips are filtered out before selecting the top three actions, and original source ranks remain visible. If no action qualifies, the duck remains attentive without inventing an imitation.

The controller retains six motions, but reference selection in both modes allows only bounded walking/turning, beak dip, vertical head nod and sit-and-stand. Head scan and standing hold are excluded. Within each clip, eligible behavior is preferred in the order walk → pick → nod → sit; retrieval rank and exact current reviews remain authoritative. Sitting requires explicit sitting evidence, and a nod requires vertical head-motion evidence. Stop cancels the sequence while allowing a seated duck to stand safely. See the [complete motion inventory](../../docs/RANGER_DUCK_ANIMATION.md).

The animal motor improves patrol, gait and interaction settling while retaining the original articulated procedural cat/deer. The requested animal-model replacement was canceled; no generated model or external animal asset setup is required.

Cat searches use the `meow-10k` and `cat-behavior` tags in both modes. The configured dataset identity is `hf-smgjch-meow-10k`; the current archive exposes tag filtering but not a `dataset_id` filter.

Cat encounters cover hissing boundaries, greetings and social play; deer encounters cover co-foraging, following and group alert. A scripted hissing pose does not claim the retrieved clip contains a hiss. The movement explanation shows what the returned caption actually supports. See the [behavior research and limitations](../../docs/RANGER_DUCK_INTERACTIONS.md).

The committed visual-review manifest remains empty; real source identities stay private. A manifest is optional for caption-derived interaction actions. An exact current solitary-feeding review can authorize its behavior without claiming a deer–deer interaction. The [review workflow](backend/README.md#interaction-evidence-and-optional-human-review) remains available for exact reviewed evidence.

Replay explicitly reuses a previous live result for the current session and search scope. Video still streams from VSS. Broader search relaxes the behavior query while retaining the species. No match and Timeout rehearsal controls remain labeled demonstrations without fabricated evidence.

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
