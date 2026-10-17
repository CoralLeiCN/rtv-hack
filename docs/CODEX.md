# Using the VSS skills with Codex

Open this repository in Codex. Project instructions live in
[`AGENTS.md`](../AGENTS.md), and each skill has a `SKILL.md` directly inside its
folder in [`.agents/skills/`](../.agents/skills/). These are the repository formats
described in the official [skills guide](https://learn.chatgpt.com/docs/build-skills)
and [AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Describe what you want, or mention a skill by its declared name:

```text
Use $build-day-quickstart to guide me through the workshop.
Use $retrieval-dashboard to check what is indexed.
Use $retrieval-search to find people near the entrance after 6pm.
Use $ingest-reingest-chunk to re-process one Explore card.
```

In Codex CLI or the IDE extension, `/skills` lists available skills and `$` lets
you mention one. Codex also selects matching skills from plain-language requests.
If the new skills do not appear, restart Codex with this repository open.

## Runtime configuration

Local editing works without workshop credentials. Live API, GPU, DB, and Kubernetes
operations need access to the configured workshop environment. You can keep Codex
on your laptop and run those operations through SSH on the VM. Follow
[Connect to the workshop services from Codex](SERVICE_CONNECTIONS.md) for
cloudflared setup, SSH keys, service authentication, and a read-only query example.
Alternatively, run Codex in the configured environment.

[`config.example`](../config.example) documents the exported variables. The skills
also use the VM's absolute `/config/` directory for team configuration and cluster
access. Keep those files outside the repository and do not paste credentials into
chat. Bash examples using `mapfile` need Bash 4 or newer; run them on the workshop
VM in one shell session so the configuration and JWT remain available.

The retrieval deployment skills reference a separate VSS Blueprint checkout with
`deployments/vss-k8s-application/`, `source-code/`, and `QUICK_DEPLOY.sh`. Those
application sources are not included in this skills repository. The shared
DataEngine ingest pipeline is already deployed.

## Skill catalog

The original 20 `SKILL.md` workflows are available under their declared names.
The GPU guide, previously stored as a README with skill metadata, is also
discoverable as `$gpu-models`.

| Skill | Purpose |
| --- | --- |
| [$build-day-quickstart](../.agents/skills/build-day-quickstart/SKILL.md) | Interactive workshop walkthrough |
| [$ask-cosmos](../.agents/skills/ask-cosmos/SKILL.md) | Health check and redacted support note; manual sharing |
| [$retrieval-login](../.agents/skills/retrieval-login/SKILL.md) | Backend JWT authentication |
| [$retrieval-search](../.agents/skills/retrieval-search/SKILL.md) | Semantic and hybrid video search |
| [$retrieval-list-metadata](../.agents/skills/retrieval-list-metadata/SKILL.md) | Valid search filters and ingest options |
| [$retrieval-dashboard](../.agents/skills/retrieval-dashboard/SKILL.md) | Archive statistics and indexing progress |
| [$retrieval-suggest-prompts](../.agents/skills/retrieval-suggest-prompts/SKILL.md) | Search suggestions and recent highlights |
| [$retrieval-videos](../.agents/skills/retrieval-videos/SKILL.md) | Browse, playback, detections, and summaries |
| [$retrieval-agent-qa](../.agents/skills/retrieval-agent-qa/SKILL.md) | Archive questions with video evidence |
| [$ingest-upload-video](../.agents/skills/ingest-upload-video/SKILL.md) | Upload a new video file |
| [$ingest-reingest-videos](../.agents/skills/ingest-reingest-videos/SKILL.md) | Re-process an indexed video or stream |
| [$ingest-reingest-chunk](../.agents/skills/ingest-reingest-chunk/SKILL.md) | Re-process one Explore card |
| [$gpu-models](../.agents/skills/gpu-models/SKILL.md) | Shared model APIs and integration guidance |
| [$gpu-model-health](../.agents/skills/gpu-model-health/SKILL.md) | Per-model liveness and readiness checks |
| [$gpu-model-smoke-test](../.agents/skills/gpu-model-smoke-test/SKILL.md) | Minimal inference checks |
| [$vast-database-vastdb-read](../.agents/skills/vast-database-vastdb-read/SKILL.md) | Direct SDK catalog and row inspection |
| [$vast-database-vastdb-write](../.agents/skills/vast-database-vastdb-write/SKILL.md) | Custom tables and row insertion |
| [$deploy-build-yamls](../.agents/skills/deploy-build-yamls/SKILL.md) | Retrieval manifest preparation |
| [$deploy-retrieval](../.agents/skills/deploy-retrieval/SKILL.md) | Retrieval stack deployment |
| [$deploy-health](../.agents/skills/deploy-health/SKILL.md) | Retrieval deployment health checks |
| [$deploy-app-no-registry](../.agents/skills/deploy-app-no-registry/SKILL.md) | Custom Kubernetes app at `/app` |

## Shared references and helpers

The [retrieval](../.agents/references/retrieval.md),
[ingest](../.agents/references/ingest.md),
[deployment](../.agents/references/deployment.md), and
[VastDB](../.agents/references/vast-database.md) guides provide shared context.
Each relevant skill links to its guide. The GPU model guide is the
[`gpu-models` skill](../.agents/skills/gpu-models/SKILL.md).

The existing Python helpers are included under their owning skills' `scripts/`
directories. Run commands from the repository root, for example:

```bash
python3 .agents/skills/vast-database-vastdb-read/scripts/list_catalog.py
python3 .agents/skills/vast-database-vastdb-read/scripts/query.py --limit 5
```

The original [`.cursor/`](../.cursor/) files remain available for Cursor. Codex
uses the converted files, including Codex question-tool guidance, updated local
links, and `$skill-name` references. No additional MCP server is required: these
skills describe existing HTTP APIs, Kubernetes commands, and Python SDK helpers.
