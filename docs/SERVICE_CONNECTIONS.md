# Service connections

[ARCHIVE.md](ARCHIVE.md) documents the Qdrant, Neon, local media and model-service
configuration. [The application setup guide](../apps/ranger-duck/README.md)
documents the browser and application backend.

| Connection | Configuration |
| --- | --- |
| Applications to archive API | ARCHIVE_URL and server-side ARCHIVE_API_KEY |
| Archive to Neon | DATABASE_URL; direct WORKER_DATABASE_URL for worker locks |
| Archive to Qdrant | QDRANT_URL, QDRANT_COLLECTION and optional QDRANT_API_KEY |
| Archive to local files | MEDIA_ROOT |
| Ingestion to Cosmos Reasoner | COSMOS_URL, COSMOS_MODEL, COSMOS_REVISION and optional COSMOS_API_KEY |
| Local embedding inference | EMBEDDING_MODEL, EMBEDDING_REVISION and EMBEDDING_DEVICE |

Use the example configuration files and keep real values outside version control.
The browser receives session-scoped playback URLs rather than service credentials.
