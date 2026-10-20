# MicroDuck repository instructions

## Start here

- Read [docs/README.md](docs/README.md) for document ownership and task routing.
- Use [development](docs/development.md) for setup and the code map,
  [testing](docs/testing.md) for checks, and [status](docs/status.md) for remaining
  work and validation limits.
- The active archive architecture is [docs/spec.md](docs/spec.md). Ranger Duck
  behavior and wire contracts live in [docs/reference/](docs/reference/).
- Read the references needed for the task. `docs/history/`, design mockups and
  `legacy/workshop/` are historical context, not current requirements.

## Services and invariants

- `services/archive/` is the supported ingestion, search and media service.
  Neon/Postgres is authoritative; Qdrant is a rebuildable index; media is local.
- `apps/ranger-duck/backend/` and `frontend/` implement Ranger Duck.
  `server.py` and `web/` implement the simple search UI.
- Embeddings use `google/embeddinggemma-2`: normalized 768 dimensions and
  query/document prefixes. Video understanding uses a configurable self-hosted
  Cosmos 3 Reasoner endpoint. Never invent captions or embeddings.
- Preserve stable public IDs and publish only successfully indexed segments.
  Worker advisory locks require the direct Neon connection and the same database
  session for all worker writes. Keep attempt-specific vector IDs and media paths.
- Preserve session ownership, exact-caption evidence hashes, cancellation,
  late-response rejection and streaming cleanup. The requested encounter is not
  action evidence. Retrieval selects walking, beak dip, vertical head nod and
  sit/stand; completion requires actual playback and motion outcomes.

## Configuration

Read private configuration only from the explicitly selected environment file or
exported variables. Never print or commit keys, connection strings or real
configuration values, or send them to a model or browser. Do not search other
repositories or unrelated configuration directories for credentials.
Use committed examples for variable names. Do not modify external infrastructure
unless the task authorizes it. Keep model revisions and package versions explicit
when deploying.

## Verification and handoff

Run applicable checks from [docs/testing.md](docs/testing.md), from the repo root:

```bash
make test
npm --prefix apps/ranger-duck/frontend test
npm --prefix apps/ranger-duck/frontend run build
git diff --check
```

Install prerequisites first; choose checks relevant to the changed area.
Documentation-only edits need link/path, command and diff checks, not model runs.
Use disposable databases and synthetic media for tests. `TEST_DATABASE_URL`
must never target a real archive: integration tests truncate its tables.
Report fixture checks, skipped checks and live validation separately; model-backed
checks require actual model services.

Keep the diff focused and preserve unrelated work. Update the owning document
when behavior, configuration or commands change; link to it instead of copying
its contract into another README. For substantial work, record scope, acceptance
checks, decisions and remaining work in a task plan as described in
[development](docs/development.md#working-with-a-coding-agent).
Review the diff before handoff and report what changed, checks run and limitations.
