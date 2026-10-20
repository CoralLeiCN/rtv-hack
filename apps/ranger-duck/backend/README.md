# Ranger Duck backend

FastAPI connects to the independent archive for retrieval/playback and the locally
authenticated Codex CLI for bounded decisions. Start it using the shared root
environment in the [application guide](../README.md#run).

Use relative `/demo-api` URLs through the frontend origin. Forward cookies,
`Range` and `If-Range` through the development proxy. Use one backend worker;
session capabilities and replay live in memory and disappear on restart.
Health and encounter metadata work without archive configuration; live search
reports missing configuration explicitly.

## Code map

| File | Responsibility |
| --- | --- |
| [app.py](ranger_duck/app.py) | Routes, request validation and public responses |
| [runs.py](ranger_duck/runs.py) | Unified run, round, queue, attempt, replay and cancellation state |
| [archive.py](ranger_duck/archive.py), [stream.py](ranger_duck/stream.py) | Archive requests and bounded playback proxy |
| [interaction.py](ranger_duck/interaction.py), [evidence.py](ranger_duck/evidence.py) | Caption eligibility, provenance and exact reviews |
| [loop_agent.py](ranger_duck/loop_agent.py), [encounter_agent.py](ranger_duck/encounter_agent.py) | Structured Codex decisions |
| [session.py](ranger_duck/session.py) | Cookie-scoped clip capabilities |
| [review.py](ranger_duck/review.py) | Private human-review manifests |
| [capture.py](ranger_duck/capture.py), [serve.py](ranger_duck/serve.py) | Durable captures, optional exporter and startup |
| [encounter.py](ranger_duck/encounter.py), [loop.py](ranger_duck/loop.py) | Compatibility flows retained alongside unified runs |

## Contracts and operations

- [API reference](../../../docs/reference/ranger-duck-api.md) owns route tables,
  payloads, deadlines, session limits and compatibility behavior.
- [Runtime behavior](../../../docs/reference/behavior.md) owns queue selection,
  Loop boundaries, grounded roles, cancellation and actual outcomes.
- [Evidence review](../../../docs/guides/evidence-review.md) owns draft/approve/validate
  commands and exact-caption binding rules.
- [Capture operations](../../../docs/guides/captures.md) owns private JSONL storage
  and optional W&B export.
- [Development](../../../docs/development.md#configuration-boundaries) owns environment
  selection. [Testing](../../../docs/testing.md) owns checks and live-validation limits.
