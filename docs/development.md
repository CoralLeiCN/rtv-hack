# Development

This guide owns local setup and repository navigation. Read [AGENTS.md](../AGENTS.md)
for working rules and [status](status.md) before claiming deployment or model readiness.

## Prerequisites and installation

Use Python 3.11+, Node.js 22.12+, FFmpeg/FFprobe and Docker for Qdrant and the
disposable integration environment. Live Ranger Duck planning also needs the
existing Codex CLI authenticated on the backend host. Model services and immutable
revision pins are covered in [archive operations](guides/archive.md#model-services).

Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e './services/archive[test]' -e './apps/ranger-duck/backend[test]'
npm --prefix apps/ranger-duck/frontend ci
```

This installs development/test packages without downloading model weights.
For live inference, install model extras as described in
[archive setup](guides/archive.md#install-and-configure). `make setup` includes
those extras. The optional backend `capture` extra is needed for [W&B export](guides/captures.md).

## Configuration boundaries

| Process | Default private file | Explicit selection | Committed template |
| --- | --- | --- | --- |
| Archive API and worker | `.env` in the working directory | `ARCHIVE_ENV_FILE` | [config.example](../config.example) |
| Ranger Duck, simple search and capture exporter | `apps/ranger-duck/backend/.env` | Absolute existing `RANGER_ENV_FILE`; Ranger launcher also accepts `--env-file` | [backend/example.env](../apps/ranger-duck/backend/example.env) |

Exported variables override file values. These are separate service configurations:
the root archive file is not automatically the application file. Copy a template
only when creating a new file; preserve existing private configuration.
Never print its values or pass credentials to the browser or decision agent.
See [service connections](guides/archive.md#service-connections) for variable names.

## Run locally

1. Configure and start the archive API and worker using
   [archive operations](guides/archive.md). Import footage separately.
2. Configure the application file and authenticate the Codex CLI on the backend
   host with `codex login`, then check `codex login status`. The existing ChatGPT
   login is reused for decisions.
3. Follow [Ranger Duck startup](../apps/ranger-duck/README.md#run) for the API,
   pinned simulator assets and frontend. Alternatively, `make run` serves the
   simple search UI at `http://127.0.0.1:8000`.

The archive defaults to port 18001 and Ranger Duck to 18000. The frontend proxy
defaults to 8000 in code, so explicitly set `RANGER_BACKEND_URL` to port 18000
when running Ranger Duck. Browser API and playback calls stay on the frontend
origin. Use one Ranger backend worker: session capabilities and replay are in
memory and disappear on restart.

`make demo` starts the simple UI's synthetic fixture server without a live archive.
It is a UI rehearsal, not evidence of successful ingestion, inference or retrieval.

## Code map

| Area | Entry points and responsibilities |
| --- | --- |
| Archive | [api.py](../services/archive/video_archive/api.py), [cli.py](../services/archive/video_archive/cli.py), [ingest.py](../services/archive/video_archive/ingest.py), [repository.py](../services/archive/video_archive/repository.py), [index.py](../services/archive/video_archive/index.py), [media.py](../services/archive/video_archive/media.py), [models.py](../services/archive/video_archive/models.py) |
| Ranger backend | [app.py](../apps/ranger-duck/backend/ranger_duck/app.py) routes; [runs.py](../apps/ranger-duck/backend/ranger_duck/runs.py) unified state; [action_evidence.py](../apps/ranger-duck/backend/ranger_duck/action_evidence.py) provenance/review constraints; [loop_agent.py](../apps/ranger-duck/backend/ranger_duck/loop_agent.py) bounded decisions; [archive.py](../apps/ranger-duck/backend/ranger_duck/archive.py) retrieval |
| Ranger frontend | [App.tsx](../apps/ranger-duck/frontend/src/App.tsx) UI; [session.ts](../apps/ranger-duck/frontend/src/session.ts) execution/cancellation; [sessionApi.ts](../apps/ranger-duck/frontend/src/sessionApi.ts) run client |
| Simulation | [adapter.ts](../apps/ranger-duck/frontend/src/simulator/adapter.ts) physics completion; [MicroduckScene.tsx](../apps/ranger-duck/frontend/src/simulator/MicroduckScene.tsx) coordination; [animalMotor.ts](../apps/ranger-duck/frontend/src/simulator/animalMotor.ts) scripted animal motion |
| Simple search | [server.py](../server.py), [web/](../web/), [scripts/serve.py](../scripts/serve.py) |
| Tests | [tests/](../tests/), [backend tests](../apps/ranger-duck/backend/tests/), [archive tests](../services/archive/tests/), [frontend tests](../apps/ranger-duck/frontend/tests/) and colocated simulator tests |
| Historical tooling | [legacy/workshop/](../legacy/workshop/) is not the supported ingestion pipeline |

The application decision agent receives bounded structured requests with retrieved
captions and actual outcomes. Archive caption generation is a separate service.
Preserve source provenance without sending private storage identities or credentials
into agent context. API behavior belongs to the [API reference](reference/ranger-duck-api.md).

## Working with a coding agent

Give each task a concrete outcome, relevant files, constraints and acceptance
checks. Inspect the worktree and relevant source/tests before editing; preserve
unrelated changes. For small fixes, a brief working plan is sufficient.

For work spanning several components or sessions, create `docs/plans/<task>.md`
with: goal and scope; current evidence and affected contracts; ordered steps;
acceptance checks; decisions; progress and unresolved work. Keep results separate
from intended checks, and record skipped prerequisites honestly. Link the active
plan from [status](status.md); move it to history when finished and remove the
active link. Do not turn a completed plan into a second permanent specification.

Make focused changes, update the owning contract/guide, and run applicable
[checks](testing.md). Review the diff for evidence binding, session isolation,
cancellation, stream cleanup and documentation drift. Handoff should state the
result, verification performed, skips and any remaining live validation.
