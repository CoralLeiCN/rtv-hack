# Ranger Duck

One page for a scripted wildlife encounter, live archive retrieval, reference playback, and evidence-guided imitation by a physics-simulated Microduck. The interface follows the [design handoff](design/README.md); the scene uses the official Microduck MuJoCo/ONNX controller.

See the repository README for the [tech stack](../../README.md#ranger-duck-tech-stack)
and [agent flow](../../README.md#how-agentic-search-works). The unified page uses the local Codex CLI to generate queries and supported
responses from archive evidence, with one Loop toggle controlling new searches.

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
.venv/bin/python -m pip install -e '.[test,capture]'
.venv/bin/ranger-duck-serve --port 18000
```

When `RANGER_WEAVE_PROJECT` is configured, this starts the W&B exporter with the API and resumes pending captures after every restart. Save `WANDB_API_KEY` privately in the backend `.env`. Use `--env-file /absolute/path/to/backend/.env` to reuse that saved configuration from another worktree; secrets are never committed or copied by Git. See [capture setup](backend/README.md#capture-search-codex-decisions-and-action-outcomes).

Open the Local URL printed by Vite. Browser API calls and video playback use
that origin and its session cookies. The asset script checks pinned sizes and
SHA-256 digests; `--check` verifies an existing download without network access.
Assets, local `.env`, and build output are ignored by Git.

## Unified encounter and Loop flow

1. Wait for the simulator and backend catalog. Choose Cat or Deer, then an encounter preset. The preset seeds an editable intent.
2. Leave **Loop off** for Encounter behavior, or switch **Loop on** for adaptive searches. Press Start. One animal appears outside the box; query planning runs alongside the duck's facing and approach.
3. The generated query includes both same-species interaction and similar individual behavior. It appears before retrieval starts. The same VSS request retrieves up to 15 candidates for either toggle setting.
4. One batch agent call proposes grounded actions and companion roles. Validation excludes passive or unsupported results before choosing the first three compatible actions in original archive order.
5. Each reference plays automatically. The duck and, where grounded, the single animal perform their supported roles. Playback and observed motion completion must finish before the next action. No Copy click is needed.
6. **Loop off:** repeat this encounter and queue without another search. **Loop on:** after the queue completes, randomly choose a different interaction for the same animal and generate a fresh query using that interaction, the original intent and actual outcomes. The first round uses the selected preset. The toggle is read at the round boundary; changing it never reloads the duck or interrupts an action.
7. Pause stops pending work and movement; Resume retries an interrupted action from its beginning while preserving completed entries. Reset clears the run and resets the duck. A changed intent or species starts a new run while preserving the existing physics body.

The page keeps the simulation, agent query, three active cards, current reference,
behavior mapping and actual movement controls together. Recent rounds retain
queries, source ranks and outcomes. Query generation, VSS retrieval and action
planning have separate measured timings. Both toggle positions share those
operations, deadlines and batch sizes; neither waits for navigation before
starting search and neither makes an agent call for each clip.

Each Loop turn is one round of up to three actions. Cat rounds rotate among
hissing, greeting and social play; deer rounds rotate among foraging together,
following and herd alert. The same animal changes its scripted interaction
without being replaced or teleported. The page shows the current round's
interaction, while replay retains its recorded interaction.

A visibility pause resumes on return only when hiding the tab caused the pause;
manual Pause and reference inspection stay paused. Playback failures, movement
failures and no-match states remain explicit. A seated duck completes its native
standing transition when paused.

The agent derives actions from the returned clips' existing video-model captions; the backend validates them and labels them as inferred. Each needs the selected species, a supported caption behavior and complete provenance. Both interaction clips and similar single-animal behaviors are usable. Incompatible clips are filtered out before selecting the top three actions, and original source ranks remain visible. If no action qualifies, the duck remains attentive without inventing an imitation.

The controller retains six motions, but reference selection allows only bounded walking/turning, beak dip, vertical head nod and sit-and-stand. Head scan and standing hold are excluded. Within each clip, eligible behavior is preferred in the order walk → pick → nod → sit; retrieval rank and exact current reviews remain authoritative. Sitting requires explicit sitting evidence, and a nod requires vertical head-motion evidence. Pause cancels the sequence while allowing a seated duck to stand safely. See the [complete motion inventory](../../docs/RANGER_DUCK_ANIMATION.md).

The animal motor improves patrol, gait and interaction settling while retaining the original articulated procedural cat/deer. The requested animal-model replacement was canceled; no generated model or external animal asset setup is required.

Cat searches use the `meow-10k` and `cat-behavior` tags for every live round. The configured dataset identity is `hf-smgjch-meow-10k`; the current archive exposes tag filtering but not a `dataset_id` filter.

Cat encounters cover hissing boundaries, greetings and social play; deer encounters cover co-foraging, following and group alert. A scripted hissing pose does not claim the retrieved clip contains a hiss. The movement explanation shows what the returned caption actually supports. See the [behavior research and limitations](../../docs/RANGER_DUCK_INTERACTIONS.md).

The committed visual-review manifest remains empty; real source identities stay private. A manifest is optional for caption-derived interaction actions. An exact current solitary-feeding review can authorize its behavior without claiming a deer–deer interaction. The [review workflow](backend/README.md#interaction-evidence-and-optional-human-review) remains available for exact reviewed evidence.

Replay saved round explicitly reuses recorded decisions through the same player and controller. It makes no agent/search call, remains labeled as recorded, and ends paused after that queue. Replay outcomes do not inform live planning; video still streams from VSS. An empty result offers an explicit broader search that relaxes the behavior query while retaining the species.

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
