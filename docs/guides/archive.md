# Independent archive setup

The archive uses Qdrant, Neon Postgres, local media, EmbeddingGemma 2 and a
self-hosted Cosmos 3 Reasoner. The existing
Codex decision agent and optional W&B tracing remain separate application features.

## Service connections

| Connection | Configuration |
| --- | --- |
| Applications to archive API | ARCHIVE_URL and server-side ARCHIVE_API_KEY |
| Archive to Neon | DATABASE_URL; direct WORKER_DATABASE_URL for worker locks |
| Archive to Qdrant | QDRANT_URL, QDRANT_COLLECTION and optional QDRANT_API_KEY |
| Archive to local files | MEDIA_ROOT |
| Ingestion to Cosmos Reasoner | COSMOS_URL, COSMOS_MODEL, COSMOS_REVISION and optional COSMOS_API_KEY |
| Local embedding inference | EMBEDDING_MODEL, EMBEDDING_REVISION and EMBEDDING_DEVICE |

Use the [development configuration guide](../development.md#configuration-boundaries)
for file selection and precedence. Use committed examples for variable names;
keep real values private. Browsers receive session-scoped playback URLs.

## Install and configure

Use Python 3.11+, FFmpeg/FFprobe, Node for the frontend, and Docker for Qdrant.
From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e './services/archive[models,test]' -e './apps/ranger-duck/backend[test]'
test -e .env || cp config.example .env
```

Fill in `.env` privately. Generate a random ARCHIVE_API_KEY and use the same key
in the archive and application configs. Never pass keys in URLs. The archive
loads `.env` in the working directory, or the file selected by ARCHIVE_ENV_FILE.
Use an absolute MEDIA_ROOT for persistent deployments. Both API and worker must
see the same directory, writable only by the trusted service account.

Set DATABASE_URL to your Neon connection URL with TLS enabled (`sslmode=require`).
Set WORKER_DATABASE_URL to the **direct** Neon URL (hostname without `-pooler`):
the worker uses a session advisory lock, incompatible with transaction pooling.
The API can use the pooled URL. Standard Postgres also works for development.
Use a dedicated database; `init` creates only the archive_* tables and indexes.
After upgrading an existing archive, stop the worker and rerun `video-archive init`
before starting services. This adds the active vector ID column and preserves
existing vector mappings; the migration is repeatable.

```bash
docker compose -f compose.archive.yml up -d
.venv/bin/video-archive init
```

Qdrant binds to loopback and persists in a Docker volume. For a remote Qdrant,
configure QDRANT_URL and QDRANT_API_KEY and use TLS. Do not expose the unauthenticated
local Qdrant port publicly. Postgres and Qdrant are separate failure domains:
segments become searchable only after a successful Qdrant upsert. Back up Postgres
and MEDIA_ROOT; Qdrant can be rebuilt by retrying completed jobs with the same
model/revision. Keep old collections until a model migration is verified.

## Model services

EmbeddingGemma 2 (`google/embeddinggemma-2`, Apache-2.0) is loaded locally by the
archive and worker. Its query/document prefixes and normalized 768d output are
configured in the adapter. CPU inference uses float32; supported CUDA devices
use bfloat16. Set EMBEDDING_DEVICE=cuda to use a GPU. This implementation embeds
captions; direct video/audio embedding is not enabled yet.

Pin EMBEDDING_REVISION to an immutable model commit before importing real data.
The initial `main` value is convenient for setup but is not a reproducibility pin.
Changing embedding model/revision requires a new QDRANT_COLLECTION and re-ingestion.
Do not mix embeddings from different models even if their dimensions match.
The first request loads/downloads weights and may exceed the application's normal
search budget; warm the archive directly before opening the UI.

Deploy Cosmos 3 using NVIDIA's release-tested vLLM instructions:
https://github.com/NVIDIA/cosmos/blob/main/cookbooks/cosmos3/reasoner/README.md
The downloadable default checkpoint is https://huggingface.co/nvidia/Cosmos3-Nano
under OpenMDW-1.1. Run its **Reasoner** component, which accepts video and emits
text. Configure COSMOS_URL with the /v1 suffix, COSMOS_MODEL with the exact served
ID from /v1/models, and COSMOS_API_KEY if your endpoint requires authentication.
COSMOS_REVISION records the checkpoint you deployed; the client cannot prove the
remote server's revision. Pin the checkpoint in the serving process as well as
recording its revision in archive configuration.

The NVIDIA guide specifies versioned vLLM/CUDA packages and GPU requirements.
Use that model environment separately from this application's Python environment.
Video segments are sent as base64 video content (32 MiB maximum per segment), so
Cosmos does not need filesystem access. Reduce segment length for oversized clips.

## Ingest and run

```bash
.venv/bin/video-archive ingest /absolute/path/animal.mp4 --dataset my-animals --tag wildlife
.venv/bin/video-archive worker
```

Run `.venv/bin/video-archive serve` from the repository root in a second terminal. It binds to 127.0.0.1:18001.
Use `--tag meow-10k --tag cat-behavior` for the current cat encounter scope.
Tags use OR matching. The library is single-tenant: the configured applications
can search all indexed material in it. Dataset IDs record provenance, not access
permissions. The archive API is intended for trusted backend use only.

`--segment-seconds 10` controls segmentation. `--captions captions.json` imports
an ordered JSON list of exact captions, one per generated segment, and bypasses
Cosmos. Imported captions still require local EmbeddingGemma inference. Original
checksums plus ingestion settings deduplicate identical submissions. Changed
settings create a distinct job; old indexed segments remain until explicitly
migrated. The worker preserves an existing segment caption on retry and uses
stable public segment UUIDs. Every attempt uses separate vector point IDs, and
Postgres selects the active point for each segment. Worker writes share the
lock-owning database session; loss of that session requires restarting the
worker. Delayed writes from an obsolete worker cannot replace active vectors or
new media files. Interrupted attempts can leave unreferenced files and vector
points; they are excluded from search and should be retained until workers are
stopped before any offline cleanup.

Segment intervals follow the first video track, not the container's audio tail.
Containers without video duration metadata require an additional video decode
during ingestion. Each generated or reused clip must contain a decodable video
frame before it can be indexed. New submissions use pipeline version 2; existing
job IDs and captions remain unchanged when retrying older jobs.

```bash
.venv/bin/video-archive status
.venv/bin/video-archive retry JOB_UUID
.venv/bin/video-archive worker --once
```

Jobs retry at most three times, with a 30-second delay. `retry` explicitly resets
the retry budget, including for completed jobs when rebuilding an index. Stop the
continuous worker before retrying; the CLI takes the same database lock.
Errors expose fixed codes rather than upstream diagnostics or credentials.

`GET /health` is liveness only. Authenticated `GET /ready` checks schema, Qdrant
vector shape and local storage, and reports whether embeddings have been loaded.
A successful search validates the actual model path. It is not a Cosmos health
check; use a newly ingested video without imported captions to test that service.

## Connect the applications

If no application configuration exists, copy
[backend/example.env](../../apps/ranger-duck/backend/example.env) to `.env` beside it and privately set
ARCHIVE_URL and ARCHIVE_API_KEY. Both UIs use that application config, or an
absolute RANGER_ENV_FILE, with exported variables taking precedence.

- Ranger Duck: `.venv/bin/ranger-duck-serve`, then run the frontend as described
  in [the application guide](../../apps/ranger-duck/README.md#run). Keep one app worker for session state.
- Simple search: `make run` serves http://127.0.0.1:8000.

Local media uses media://UUID references. Historical S3 review manifests remain
parseable for offline review, but the new archive never resolves S3 URIs. Export
or reacquire videos from the old environment, ingest them, and review new evidence
references. Changing source IDs or caption text invalidates old review bindings.
No actual video files are included in the repository dataset inventories.

## Verification and deployment boundaries

Run the checks in [testing](../testing.md), including the disposable archive
integration image for storage, ingestion and media changes. Fixture tests and
live model validation must be reported separately.

The optional services/archive/Dockerfile packages the API and worker runtime.
Mount persistent media at /media and pass configuration privately. Cosmos runs
separately. For now the API and worker share one host/filesystem; multiple media
hosts or per-user archive permissions need an additional storage/access design.
