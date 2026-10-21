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

### Isolated local database services

For a local-only development archive, [compose.local.yml](../../compose.local.yml)
runs versioned Postgres and Qdrant in a separate Compose project. In the selected
root `.env`, generate `POSTGRES_PASSWORD`; configure both database URLs for user
and database `microduck` on `127.0.0.1:15432` with that password, and set
`QDRANT_URL=http://127.0.0.1:16333`. Use a dedicated absolute media directory.
Keep the file owner-readable only. Start Docker Desktop first on macOS, then:

```bash
docker compose -p microduck-local --env-file .env -f compose.local.yml up -d --wait
.venv/bin/video-archive init
```

Both service ports bind only to loopback. Named volumes survive shutdown:

```bash
docker compose -p microduck-local --env-file .env -f compose.local.yml stop
```

This verifies the Postgres development path; it does not validate a Neon deployment.
Never use this archive as `TEST_DATABASE_URL` for destructive integration tests.

## Model services

EmbeddingGemma 2 (`google/embeddinggemma-2`, Apache-2.0) is loaded locally by the
archive and worker. Its query/document prefixes and normalized 768d output are
configured in the adapter. CPU inference uses float32; supported CUDA devices
use bfloat16. Set EMBEDDING_DEVICE=cuda to use a GPU. This implementation embeds
captions; direct video/audio embedding is not enabled yet.

Current EmbeddingGemma 2 checkpoints use Sentence Transformers 6.1 pooling
configuration. Install the `models` extra with version 6.1 or newer; the former
5.x constraint cannot load that configuration.

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

### Local Transformers reasoner on Apple Silicon

An experimental loopback adapter is available for a Mac with enough unified
memory. It runs the official Cosmos 3 Reasoner with PyTorch Metal; NVIDIA's
release-tested CUDA deployment above remains a separate validation target.
Use the smaller `nvidia/Cosmos3-Edge` checkpoint for local setup. The adapter
accepts inline MP4 caption requests, samples at four frames per second, serializes
inference, and reports truncated generations as incomplete. It accepts neither
remote video URLs nor client-provided file paths.

```bash
.venv/bin/pip install -e './services/archive[models,local-cosmos]' 'sentence-transformers==6.1.0'
```

Set `COSMOS_URL=http://127.0.0.1:18002/v1`,
`COSMOS_MODEL=nvidia/Cosmos3-Edge`, and an immutable `COSMOS_REVISION` in the
selected archive file. The 21 October setup selected revision
`344d602b128d1bbdacb43b08d0a3626f46343e29`. For embeddings it selected
`google/embeddinggemma-2` revision `914f7f89142e33e77833254d9c9b90c3cef7303b`.
The optional `MODEL@REVISION` served ID is also accepted when both revisions match.
Keep the model cache inside ignored local storage; export its path for **each**
model-loading process (an `HF_HOME` line in `.env` alone does not export it):

```bash
export HF_HOME="$PWD/tmp/local-stack/huggingface"
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1
.venv/bin/python -m video_archive.local_cosmos --device mps
```

The first launch downloads weights before listening. `/health` and `/v1/models`
become available after loading; only a successful real caption establishes
inference. The `local-cosmos` extra pins the PyTorch, Transformers, torchvision,
Accelerate and PyAV runtime. Stop this foreground process with Ctrl-C.
The adapter is a single-user local development service, without public hosting
or authentication. Its host is fixed to loopback. Live results and remaining
limits are recorded in [status](../status.md).

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
new media files. Successful replacement publication deletes the preceding vector
point. A cleanup failure logs a fixed warning and leaves the published result
valid. Interrupted attempts and delayed writes can still leave orphaned vectors;
use the maintenance procedure below. Unreferenced media files remain untouched.

Segment intervals follow the first video track, not the container's audio tail.
Containers without video duration metadata require an additional video decode
during ingestion, including the final frame's duration. Each generated or reused
clip must contain a decodable video frame before it can be indexed. New submissions
use pipeline version 2; existing job IDs and captions remain unchanged when retrying
older jobs.
Re-ingest the original to correct an earlier import with a truncated final frame;
retry preserves its existing interval settings and media. As with other changed
ingestion settings, the corrected submission does not remove the old segments.

```bash
.venv/bin/video-archive status
.venv/bin/video-archive retry JOB_UUID
.venv/bin/video-archive worker --once
```

Jobs retry at most three times, with a 30-second delay. `retry` explicitly resets
the retry budget, including for completed jobs when rebuilding an index. Stop the
continuous worker before retrying; the CLI takes the same database lock.
Errors expose fixed codes rather than upstream diagnostics or credentials.

### Vector maintenance

Search requests `top_k` candidates first and fetches only the shortfall after
Postgres validation. Ten unsuccessful full pages produce `search_limit_reached`
(HTTP 503), which both applications display as an index-maintenance error instead
of a no-match result. Clean up obsolete points before retrying the search.

Stop the continuous worker and any obsolete worker processes, then use the
explicitly selected archive configuration for the matching Postgres database and
its dedicated Qdrant collection:

```bash
.venv/bin/video-archive cleanup-vectors
.venv/bin/video-archive cleanup-vectors --apply
```

The first command is a dry run. Both report `scanned`, `orphaned` and `deleted`
counts without printing source identities. The second deletes unreferenced
vectors in batches of at most 100, holding the same direct-connection advisory
lock as ingestion. Referenced points are retained even when unpublished or from
another model; no media or Postgres records are deleted. Restart the worker after
maintenance. Repeat cleanup after any previously in-flight obsolete writes have
finished; a delayed old write can recreate an orphan but cannot replace an active
point. Cleanup is safe to rerun after interruption.

### Readiness

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
