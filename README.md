# MicroDuck

MicroDuck turns animal-video evidence into inspectable behavior in a browser
simulation. Search for a moment, watch its source clip, and see how its caption
supports a bounded simulated duck action. Ranger Duck repeats a chosen encounter
or uses actual execution outcomes to plan the next round with Loop enabled.

## Start here

- [Development setup](docs/development.md): prerequisites, local startup and code map.
- [Documentation index](docs/README.md): current contracts, operations and history.
- [Implementation status](docs/status.md): what is implemented and still unverified.
- [Agent instructions](AGENTS.md): repository rules and verification expectations.

For a live demo, configure [the independent archive](docs/guides/archive.md),
then follow [Ranger Duck startup](apps/ranger-duck/README.md). `make run` serves
the simple search UI once the same archive is configured. Source videos must be
supplied separately; the [data guide](data/README.md) describes provenance.

## Architecture

| Layer | Implementation |
| --- | --- |
| Browser | React, TypeScript and Vite; Three.js, MuJoCo WebAssembly and ONNX Runtime Web |
| Ranger Duck backend | FastAPI, local Codex CLI decision agent, optional W&B capture export |
| Independent archive | FastAPI and a durable Python/FFmpeg ingestion worker |
| Metadata and jobs | Neon Postgres, the authoritative store |
| Retrieval | Self-hosted Qdrant with 768-dimensional EmbeddingGemma 2 caption vectors |
| Media | Local filesystem, streamed through session-authorized application routes |
| Caption generation | Self-hosted Cosmos 3 Reasoner through vLLM |

Both applications use the archive API. Cosmos creates captions during ingestion;
the decision agent selects bounded simulator actions from retrieved evidence.
Credentials stay server-side. See the [archive specification](docs/spec.md) for
storage, indexing and access contracts.

## Evidence and simulation

The requested encounter cannot supply missing evidence. Actions require a
retrieved caption or an exact current human review. Caption interpretations are
labeled as inferred, and simulator outcomes are reported separately. This project
does not control physical robots or interact with live animals.

See [product intent](docs/intent.md), [runtime behavior](docs/reference/behavior.md),
and [the simulator reference](docs/reference/simulator.md). Upstream revision and
licensing remain beside the [vendored simulator source](apps/ranger-duck/frontend/src/simulator/upstream/README.md).
