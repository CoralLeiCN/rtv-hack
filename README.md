# MicroDuck: An Interactive Robotic Companion for Animals

MicroDuck uses animal videos to guide a simulated robot's responses. It combines
video retrieval, caption-grounded agent decisions, playback and physics simulation.
Encounter mode repeats selected references; Loop mode uses actual execution
outcomes to plan the next encounter.

## Architecture

| Layer | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Simulation | Pollen Robotics MicroDuck, Three.js, MuJoCo WebAssembly, ONNX Runtime Web |
| Application | FastAPI; existing Codex CLI decision agent; optional W&B tracing |
| Search | Self-hosted Qdrant with 768-dimensional EmbeddingGemma 2 vectors |
| Metadata and jobs | Neon Postgres |
| Media | Local filesystem with ranged, session-authorized playback |
| Captioning | Self-hosted Cosmos 3 Reasoner through vLLM |
| Ingestion | Python worker and FFmpeg with durable retry state |

The archive, Codex decision agent and optional W&B exporter run as separate
services. Cosmos creates captions during ingestion; Codex selects bounded
simulator actions from those captions.

Follow [the archive setup guide](docs/ARCHIVE.md), then the
[Ranger Duck guide](apps/ranger-duck/README.md). The simple search-only UI is also
available through `make run`. The [specification](docs/spec.md) and
[implementation plan](plan.md) describe the architecture and validation status.

The archive keeps videos, segment timestamps, dataset provenance and exact
captions in Postgres, and vectors in Qdrant. Both applications use the same
archive API. Media is addressed by internal IDs rather than paths or S3 URLs.
The [data guide](data/README.md) describes source provenance and local imports.
Source videos must be supplied separately.

## Evidence and simulation

The requested encounter cannot supply missing evidence. Actions must be grounded
in a retrieved caption or a current human review. Supported retrieval-selected
movements include walking, beak dip, vertical head nod and sit/stand. Model
interpretations are labelled as inferred; simulator outcomes are reported
separately. The first three compatible references retain archive order.

See [the API contract](docs/RANGER_DUCK_API.md) for session ownership, replay,
loop controls and action outcomes. Simulator source attribution is preserved in
apps/ranger-duck/frontend/src/simulator/upstream/README.md.

## Documentation

- [Project intent](docs/intent.md) and [archive specification](docs/spec.md)
- [Setup and operations](docs/ARCHIVE.md)
- [Encounter and Loop behavior](docs/RANGER_DUCK_PLAN.md)
- [API contract](docs/RANGER_DUCK_API.md)
- [Animal interactions](docs/RANGER_DUCK_INTERACTIONS.md) and [supported movements](docs/RANGER_DUCK_ANIMATION.md)
- [Implementation and validation status](plan.md)
