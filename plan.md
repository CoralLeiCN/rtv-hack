# Independent archive implementation plan

Branch: feature/replace-vast-with-open-source
Specification: [docs/spec.md](docs/spec.md)

1. [x] Record the approved Qdrant, Neon, filesystem, EmbeddingGemma 2 and Cosmos architecture.
2. [x] Implement archive settings, Postgres schema/repository, Qdrant index and local media storage.
3. [x] Implement EmbeddingGemma 2 and Cosmos adapters, durable ingestion jobs and CLI.
4. [x] Implement authenticated archive search, metadata, readiness and ranged playback.
5. [x] Switch both application adapters and evidence references to the archive contract.
6. [x] Add deployment/configuration instructions; remove obsolete service integrations.
7. [x] Run archive integration tests, application regressions and frontend checks.
8. [x] Record live deployment prerequisites and any validation not possible here.

Keep each segment hidden until vector indexing succeeds. Retry using stable IDs;
never fabricate model outputs. Preserve session ownership and exact-caption review
checks. Use Neon in deployment and disposable Postgres for integration tests.

## Validation results

- 324 Python tests passed in the isolated integration container, including real
  Postgres, Qdrant local-mode retrieval, FFmpeg segmentation and both application
  adapters connected to the archive. Model outputs are explicit test fixtures.
- 103 frontend tests passed across 9 files; TypeScript/Vite production build passed.
- The static search JavaScript test suite passed; `git diff --check` passed.
- Inspected published sentence-transformers 5.7.0 and transformers 5.20.1 code:
  the selected APIs and EmbeddingGemma 2 architecture are available. Those versions
  establish the model dependency minimums. No model weights were downloaded.
- Qdrant deployment uses the official v1.19.2 image with the 1.19 Python client line.
- Existing build notices concern large simulator bundles and MuJoCo's externalized
  Node module. Python reports Starlette's HTTPX deprecation; Qdrant local mode
  notes that payload indexes require the server implementation.

## Live validation still to run

Configure the Neon URLs and private archive key, start Qdrant and the Cosmos
Reasoner service, pin/download EmbeddingGemma 2 weights, then ingest a real animal
video without imported captions. Verify relevance, seeking and a simulator round.
This implementation has not claimed a live Neon connection, production Qdrant
server test, Cosmos GPU run or real EmbeddingGemma inference.

## Code review fixes

- [x] Keep job updates on the advisory-lock session; never reconnect a stale worker.
- [x] Isolate attempt vector IDs and media writes, and migrate existing vector mappings.
- [x] Derive intervals from video duration and validate decoded frames before indexing.
- [x] Add regression coverage for lost sessions, delayed vector writes, audio tails,
  invalid generated clips, missing stream duration, and repeatable schema migration.

## Result

Both apps use the independent archive. Documentation covers the current product,
architecture and operations. Existing simulator behavior and caption review rules
are preserved. Setup and operational limits are documented in docs/ARCHIVE.md.
