# Documentation map

Start with the repository [README](../README.md) and [agent instructions](../AGENTS.md).
Each topic below has one maintained home. Read the relevant rows for a task;
there is no need to load the entire documentation tree.

## Current documents

| Need | Owning document |
| --- | --- |
| Understand the product and boundaries | [Product intent](intent.md) |
| Set up development or find implementation files | [Development](development.md) |
| Choose and run checks | [Testing and validation](testing.md) |
| Find remaining work and validation limits | [Status](status.md) |
| Change archive storage, indexing, models or access | [Archive specification](spec.md) |
| Configure, ingest, operate or deploy the archive | [Archive operations](guides/archive.md) |
| Change Encounter, Loop, evidence selection or replay | [Runtime behavior](reference/behavior.md) |
| Change browser/backend contracts | [Ranger Duck API](reference/ranger-duck-api.md) |
| Change movement, navigation or animal rendering | [Simulator reference](reference/simulator.md) |
| Understand animal scenarios and limitations | [Interaction reference](reference/interactions.md) |
| Prepare and approve exact-caption reviews | [Evidence review](guides/evidence-review.md) |
| Capture decisions/outcomes or export to W&B | [Capture operations](guides/captures.md) |
| Import footage with provenance | [Data guide](../data/README.md) |
| Change visual layout or styling | [Design guide](../apps/ranger-duck/design/README.md) |

Component READMEs provide local entry points and code maps:
[Ranger Duck](../apps/ranger-duck/README.md),
[backend](../apps/ranger-duck/backend/README.md),
[frontend](../apps/ranger-duck/frontend/README.md).
Simulator attribution stays [beside the source](../apps/ranger-duck/frontend/src/simulator/upstream/README.md),
and download instructions stay [beside the assets](../apps/ranger-duck/frontend/public/simulator/README.md).

## Authority and maintenance

`AGENTS.md` contains durable working rules. Specifications and references define
intended contracts; source and tests establish what is currently implemented.
When these disagree, identify the discrepancy and reconcile it in the authorized
task rather than silently treating an old example as a requirement.

Guides own procedures. Status owns open work and links to validation records.
History preserves completed plans, past measurements and superseded designs;
it does not establish current deployment health or permission to restore old flows.
Keep commands executable from their stated directory, use relative Markdown links,
and update links when moving files. Do not copy contract tables between READMEs.
Keep real configuration, private evidence and source media outside committed docs.

For substantial new work, use one task plan under `docs/plans/` and move it to
`docs/history/` when complete. The plan format is in
[development](development.md#working-with-a-coding-agent). Avoid parallel root
and docs-level plan files describing the same work.

## History and former locations

| Former document | Current home |
| --- | --- |
| `plan.md`, `docs/plan.md` | [Status](status.md) and [completed archive plan](history/archive-implementation.md) |
| `docs/ARCHIVE.md`, `docs/SERVICE_CONNECTIONS.md` | [Archive operations](guides/archive.md) and [testing](testing.md) |
| `docs/CODEX.md`, `docs/RANGER_DUCK_CONTEXT.md` | [Development](development.md), [behavior](reference/behavior.md) and [agent instructions](../AGENTS.md) |
| `docs/RANGER_DUCK_PLAN.md` | [Runtime behavior](reference/behavior.md) |
| `docs/RANGER_DUCK_API.md` | [API reference](reference/ranger-duck-api.md) |
| `docs/RANGER_DUCK_ANIMATION.md` | [Simulator reference](reference/simulator.md) and [past validation](history/simulator-validation-2026-10-17.md) |
| `docs/RANGER_DUCK_INTERACTIONS.md` | [Interaction reference](reference/interactions.md) |
| `docs/data_sources.md` | [Data guide](../data/README.md) |
| Original design handoff | [Historical export](history/design-handoff.md); current [visual guide](../apps/ranger-duck/design/README.md) |

## Basis for this structure

Reviewed on 19 October 2026. OpenAI recommends concise, practical repository
instructions with layout, commands, constraints and completion checks, linking
out to details as needed: [coding-agent best practices](https://learn.chatgpt.com/guides/best-practices).
Its [AGENTS.md documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
describes directory-scoped instruction discovery. This repository keeps one small
root instruction file; add scoped instructions only when a component needs
distinct working rules. Topic ownership and the history split are local
choices to prevent duplicated and contradictory guidance.
