# Agent development

Follow [AGENTS.md](../AGENTS.md), the [project intent](intent.md), the
[archive specification](spec.md) and the [setup guide](ARCHIVE.md).
The action-planning integration is in
[loop_agent.py](../apps/ranger-duck/backend/ranger_duck/loop_agent.py).

The agent plans queries and bounded actions from retrieved captions and actual
simulator outcomes. Archive ingestion and caption generation are separate
services. Preserve evidence checks, session ownership, cancellation and structured
outputs when changing the agent integration. See the
[API contract](RANGER_DUCK_API.md) for the browser-facing behavior.
