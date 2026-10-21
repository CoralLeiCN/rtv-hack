# Implementation status

Documentation reconciled on 19 October 2026. This page separates implemented
behavior from validation still required; it is not a live service-health report.

## Implemented

- The independent archive provides ingestion, durable jobs, Qdrant retrieval,
  Neon/Postgres metadata and local ranged playback. Both applications use it.
- Ranger Duck uses unified runs for Encounter and Loop, caption/review-bound
  active actions selected by Codex `gpt-6-luna`, session-owned playback, actual
  outcome acknowledgements and replay.
- Retry handling preserves stable public IDs, isolates vector/media attempts,
  and keeps worker writes on the advisory-lock database session. Segmentation
  follows the video track and requires decodable frames.

Contracts live in [the archive specification](spec.md),
[runtime behavior](reference/behavior.md) and [API reference](reference/ranger-duck-api.md).

## Connected local validation

- [x] Configure a local Postgres, Qdrant and Cosmos deployment with immutable model revisions.
- [x] Ingest a real video without imported captions using actual Cosmos and EmbeddingGemma inference.
- [x] Verify real retrieval and browser playback/seeking through the simple search application.
- [x] Verify Ranger session isolation and a completed simulator imitation round.
- [x] Verify both Loop settings and adaptive follow-up rounds with continuous physics.

Use the [live smoke-test procedure](testing.md#live-model-and-deployment-smoke-test).
The [21 October live validation record](history/live-e2e-validation-2026-10-21.md)
connects real Cosmos/EmbeddingGemma ingestion and retrieval to browser playback,
six completed walking actions and two adaptive follow-up rounds. Codex with
`gpt-6-luna` now interprets captions and selects actions, replacing runtime phrase
rules. It reused the one random Meow sample with explicit reasons; broader video,
paired-role and motion coverage remain untested live. The local Postgres/Metal
setup does not establish Neon or remote Cosmos deployment readiness. A separate
disposable-DB run exposed an existing FFmpeg duration discrepancy, since fixed
and verified as recorded below.
The [development workflow](development.md#working-with-a-coding-agent) defines
the plan lifecycle.

## Recorded validation

On 21 October, follow-up fixes replaced the duration fallback with decoded frame
timing that includes the final frame, and updated the archive integration agent
fixture to the current action-selection contract. A synthetic two-second WebM
retains all 20 frames after segmentation. Single-frame, offset-timestamp and
variable frame spacing cases also pass. The full suite passed with a fresh,
disposable Postgres 17.6 database: 372 Python tests with no skips, 15 root
JavaScript tests, 107 frontend tests, production build and diff checks. The
repository's Linux integration image also passed all 372 Python tests with
FFmpeg 5.1.9 and disposable Postgres 15, using a source-only build context.
Model outputs were fixtures; no live model or real archive was used for these
checks. Both disposable test containers were removed afterward.

The [20 October search/cleanup record](history/archive-search-cleanup-2026-10-20.md)
records small search requests, explicit budget errors and obsolete vector cleanup
checks. Its original run skipped Postgres integration because Docker was
unavailable; the full disposable-database run above now covers those checks.

The [completed archive implementation record](history/archive-implementation.md)
reports 324 Python tests in an isolated integration container, 103 frontend tests
and a production build, plus root JavaScript checks. Its models were fixtures;
it did not establish live Neon, deployed Qdrant, Cosmos GPU or EmbeddingGemma inference.
Those counts are historical results, not checks rerun for this documentation change.

The [17 October simulator record](history/simulator-validation-2026-10-17.md)
contains earlier local browser/physics measurements and test counts. Those
measurements do not validate wildlife captions or the current archive deployment.

## Project decisions

- **21 October 2026 — CI deferred:** CI is not needed for this repository for
  now. Its absence is intentional, not outstanding implementation work. Continue
  running the applicable [testing and validation checks](testing.md) manually;
  revisit CI when the project needs it.

## Operating limits

The archive is a single trusted library with shared local media storage. Dataset
IDs are provenance, not access boundaries. Ranger sessions are in-process, so
use one application worker. Multi-host media and per-user archive access need
additional design. Direct multimodal embedding and physical robot control are
outside the current implementation. See [operations](guides/archive.md).
