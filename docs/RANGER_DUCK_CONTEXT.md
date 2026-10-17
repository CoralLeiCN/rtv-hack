# Ranger Duck implementation context

The [project intent](intent.md), [behavior plan](RANGER_DUCK_PLAN.md) and
[API contract](RANGER_DUCK_API.md) describe the current product. This page records
implementation boundaries that apply across its services.

## Evidence and archive

Use the independent archive through ARCHIVE_URL and ARCHIVE_API_KEY. Setup,
model configuration and ingestion are documented in [ARCHIVE.md](ARCHIVE.md).
Cat queries use `meow-10k` and `cat-behavior` tags; deer queries use `wildlife`.
Requested scope does not establish source provenance. Preserve dataset IDs
returned by the archive and never infer them from search filters.

A successful ingestion or high similarity score does not verify species or
behavior. Exact-caption reviews, actor attribution, negation and uncertainty
checks constrain action selection. Caption-derived actions remain labeled as
inferred. Unsupported or changed evidence cannot authorize a movement.

## Runtime and simulation

The application backend runs the existing local Codex decision agent. It sends
bounded structured planning requests; credentials and private storage references
stay outside agent context. Archive retrieval and Cosmos ingestion are separate
from this action-planning runtime.

The browser runs the pinned MicroDuck simulator with MuJoCo and ONNX policies.
The backend returns primitive names, not joint commands. One controller coordinates
playback, companion animation and duck motion, and reports actual outcomes.
Keep physics continuous across clips and rounds. Pause, reset and new runs must
cancel pending work and reject late responses. Separate tabs retain independent
run and cancellation scopes.

Simulator attribution and asset instructions are in the
[upstream README](../apps/ranger-duck/frontend/src/simulator/upstream/README.md).
The [frontend guide](../apps/ranger-duck/frontend/README.md) covers execution and
replay. Current verification results and remaining live checks are in
[plan.md](../plan.md); fixture tests do not establish live model or deployment behavior.
