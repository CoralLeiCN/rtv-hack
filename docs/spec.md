# Independent video archive specification

The archive supports the [project intent](intent.md). Encounter and Loop behavior
is defined in the [API contract](reference/ranger-duck-api.md) and
[runtime behavior](reference/behavior.md).

## Components

| Component | Implementation | Responsibility |
| --- | --- | --- |
| Vector database | Self-hosted Qdrant | 768-dimensional cosine search and tag filters |
| Relational database | Neon Postgres | Videos, segments, exact captions, provenance, jobs and indexing state |
| Media | Local filesystem | Originals and MP4 segments beneath MEDIA_ROOT |
| Embeddings | google/embeddinggemma-2 | Local text query/caption embeddings; Apache-2.0 weights |
| Video understanding | Cosmos 3 Reasoner through vLLM | Captions grounded in each video segment |
| Ingestion | Python worker and FFmpeg | Durable, retryable segmentation, captioning and indexing |
| Archive API | FastAPI | Authenticated search, metadata, readiness and ranged playback |

Model references: https://huggingface.co/google/embeddinggemma-2 and
https://huggingface.co/nvidia/Cosmos3-Nano (OpenMDW-1.1). Default to
Cosmos3-Nano's Reasoner, with configurable served model ID and endpoint. Persist
model/revision identifiers with each ingestion job. Use the release-tested NVIDIA
vLLM deployment and pin the checkpoint used by the serving process.

## Data and indexing

Existing human-review manifests remain local JSON files with exact-caption hashes.
Use UUIDs for videos, segments and jobs. Media URIs are media://UUID and resolve
through database records; no request may specify a disk path or remote URL.
Neon owns captions, dataset IDs, tags, checksums, relative storage keys and
segment timestamps and the active vector point ID. Qdrant holds vectors under
attempt-specific point IDs, with tags and dataset IDs.
Search rechecks readiness and filters against Postgres before returning evidence.
Only publish a segment after its Qdrant upsert succeeds; partial failures remain
retryable and hidden. Deterministic segment IDs and an ingestion settings hash
make retries idempotent. A completed job can be explicitly requeued to rebuild
its vector index. The worker serializes processing with a Postgres advisory lock.
All worker database operations use that same session and never reconnect after
lock loss. Each attempt uses separate vector IDs and new media paths, so delayed
external writes from an obsolete worker cannot replace its successor's output.
Search resolves only the active point ID recorded in Postgres; public segment
IDs and existing captions remain stable across retries.

Load EmbeddingGemma 2 with query/document task prefixes, normalized 768d output,
and float32 on CPU or bfloat16 on supported GPUs. Never use float16. Reject
nonfinite, empty or wrong-dimensional embeddings. Changing model revision or
vector dimensions requires a new collection and full reindex. Direct multimodal
embedding is a later extension; the initial searchable evidence is caption text.

Ingestion accepts a local video, dataset ID, tags, segment length, and optionally
an ordered JSON caption list. Store the original before queueing. FFprobe checks
the first video track's duration, excluding audio-only tails. If the container
omits that duration, decode the video track to measure its timeline. FFmpeg
creates seekable H.264 MP4 segments with timestamps relative to
the parent. Imported captions must exactly cover generated intervals. Otherwise
send each segment to Cosmos and preserve its returned final caption. Never
substitute invented captions or synthetic embeddings on model failure.
Require at least one decodable video frame in every new or reused segment before
indexing it. A successful FFmpeg exit alone does not establish valid video.

## API and access

Both applications connect using ARCHIVE_URL and server-side ARCHIVE_API_KEY.
The archive accepts a server-side Bearer token; no login endpoint or token in a
playback URL. The service is initially a single trusted library shared by the
configured application. Bind locally; external multi-tenant hosting is out of scope.
Ranger Duck retains its session-scoped opaque clip registry and exact evidence
hashes. The simple search UI retains its search-result playback allowlist.

POST /api/v1/search accepts query, tags and top_k and returns ranked results with
source, original_video, reasoning_content, segment_start_sec, segment_end_sec,
similarity_score, dataset and dataset_id. Tags have OR semantics. Only indexed
segments appear. GET /api/v1/metadata returns indexed tags and datasets.
GET /health is process liveness; authenticated GET /ready checks configured
Postgres, Qdrant collection dimensions and writable media storage.
GET/HEAD /api/v1/videos/stream?source=media://UUID supports single byte ranges,
If-Range, ETag and 416. Stream in bounded chunks. Reject traversal and symlink
escapes even for malformed database records. Never expose storage paths, database
connection strings, model credentials or private upstream errors.

## Acceptance

Both UIs search and play through the independent archive. Existing encounter,
loop, provenance and cancellation tests pass after adapting their archive fixtures.
Tests exercise actual local Qdrant, Postgres job/index state, retry/reindex behavior,
local range playback, path containment, authentication and service failure handling.
A model-backed smoke test requires configured Neon, downloaded model weights,
Cosmos GPU serving and a real video. Record this separately from fixture tests.
