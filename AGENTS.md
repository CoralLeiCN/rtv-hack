# MicroDuck

The active architecture is specified in docs/spec.md; implementation status is
in plan.md and setup is in docs/ARCHIVE.md.

## Services

- Ranger Duck: apps/ranger-duck/backend and frontend.
- Simple search UI: server.py and web/.
- Independent archive: services/archive, using Qdrant, Neon/Postgres and local media.
- Embeddings: google/embeddinggemma-2, 768 dimensions, query/document prefixes.
- Video understanding: configurable self-hosted Cosmos 3 Reasoner endpoint.

Neon is authoritative; Qdrant is a rebuildable index. Preserve stable IDs and
publish only successfully indexed segments. Never invent captions or embeddings.
Preserve session ownership, evidence hashes, cancellation and streaming cleanup.
Use the direct Neon connection for worker advisory locks.

## Configuration and verification

Read private configuration from the explicitly selected environment file or
exported variables. Never print or commit keys, connection strings or real
configuration values. Never send these to the agent or browser. Do not search
other repositories or unrelated configuration directories for credentials.

Run the checks documented in docs/ARCHIVE.md. Use disposable databases and
synthetic media for tests. Model-backed checks require actual model services;
report fixture and live validation separately. Keep model revisions and package
versions explicit when deploying.

The independent archive is the supported ingestion, search and media service.
Do not modify external infrastructure unless the task authorizes it.
