# Implementation status

Documentation reconciled on 19 October 2026. This page separates implemented
behavior from validation still required; it is not a live service-health report.

## Implemented

- The independent archive provides ingestion, durable jobs, Qdrant retrieval,
  Neon/Postgres metadata and local ranged playback. Both applications use it.
- Ranger Duck uses unified runs for Encounter and Loop, caption/review-bound
  active actions, session-owned playback, actual outcome acknowledgements and replay.
- Retry handling preserves stable public IDs, isolates vector/media attempts,
  and keeps worker writes on the advisory-lock database session. Segmentation
  follows the video track and requires decodable frames.

Contracts live in [the archive specification](spec.md),
[runtime behavior](reference/behavior.md) and [API reference](reference/ranger-duck-api.md).

## Remaining live validation

- [ ] Configure the selected Neon, Qdrant and Cosmos deployment and immutable model revisions.
- [ ] Ingest a real video without imported captions using actual Cosmos and EmbeddingGemma inference.
- [ ] Verify search relevance, authorized playback/seeking and a simulator round.
- [ ] Verify both Loop settings and an adaptive follow-up round with continuous physics.

Use the [live smoke-test procedure](testing.md#live-model-and-deployment-smoke-test).
No active implementation plan is currently recorded. Add task-specific plans
here when substantial new work begins; the [development workflow](development.md#working-with-a-coding-agent)
defines their lifecycle.

## Recorded validation

The [completed archive implementation record](history/archive-implementation.md)
reports 324 Python tests in an isolated integration container, 103 frontend tests
and a production build, plus root JavaScript checks. Its models were fixtures;
it did not establish live Neon, deployed Qdrant, Cosmos GPU or EmbeddingGemma inference.
Those counts are historical results, not checks rerun for this documentation change.

The [17 October simulator record](history/simulator-validation-2026-10-17.md)
contains earlier local browser/physics measurements and test counts. Those
measurements do not validate wildlife captions or the current archive deployment.

## Operating limits

The archive is a single trusted library with shared local media storage. Dataset
IDs are provenance, not access boundaries. Ranger sessions are in-process, so
use one application worker. Multi-host media and per-user archive access need
additional design. Direct multimodal embedding and physical robot control are
outside the current implementation. See [operations](guides/archive.md).
