# Ranger Duck

Ranger Duck combines a persistent MicroDuck simulation, one scripted cat or deer,
archive playback and caption-grounded actions. Loop off repeats the current queue;
Loop on plans a fresh encounter after acknowledged outcomes.

Read [development setup](../../docs/development.md) first and configure the
[independent archive](../../docs/guides/archive.md). Product rules live in
[runtime behavior](../../docs/reference/behavior.md), wire formats in the
[API reference](../../docs/reference/ranger-duck-api.md), and visual tokens in the
[design guide](design/README.md).

## Run

These commands use the root `.venv` created by the development guide.
Configure `backend/.env` from [backend/example.env](backend/example.env) without
overwriting an existing file. Set archive credentials privately and authenticate
the Codex CLI on the backend host. Without archive configuration the simulator
can load, but live query/search requests report missing configuration.

From the repository root, start the backend:

```bash
.venv/bin/ranger-duck-serve --port 18000
```

In a separate terminal, also from the root:

```bash
python3 apps/ranger-duck/scripts/simulator-assets.py
cd apps/ranger-duck/frontend
RANGER_BACKEND_URL=http://127.0.0.1:18000 npm run dev
```

Open Vite's printed local URL. Browser API calls and playback use that origin
and its session cookie. Simulator assets are pinned and hash-checked; `--check`
verifies an existing download offline. Assets, private config and build output
are ignored by Git.

The launcher supports `--env-file /absolute/path/to/backend/.env` for an explicitly
selected configuration in another checkout. Optional W&B export needs the
`capture` dependency extra; follow [capture setup](../../docs/guides/captures.md).

## Build and serve one page

From the repository root:

```bash
npm --prefix apps/ranger-duck/frontend run build
```

Set `RANGER_STATIC_DIR` to the absolute path of `frontend/dist` when starting
the backend. It serves the build and `/demo-api` on one origin. Use one backend
worker because clip capabilities and replay are in memory; restarting invalidates
them. See [testing](../../docs/testing.md) for fixture, build and live checks.

## Implementation entry points

- [Backend](backend/README.md): runs, evidence, review and capture.
- [Frontend](frontend/README.md): session coordinator, playback and simulation.
- [Simulator reference](../../docs/reference/simulator.md): movement and cancellation.
- [Interaction reference](../../docs/reference/interactions.md): scenario rationale.
- [Status](../../docs/status.md): recorded verification and remaining live checks.
