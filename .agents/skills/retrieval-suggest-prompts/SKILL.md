---
name: retrieval-suggest-prompts
description: Fetch generated search suggestions and notable events from the VSS enrichment pipeline. Use to seed archive search or show recent highlights.
---

# Retrieval: suggest prompts (vss2)

Read the [retrieval guide](../../references/retrieval.md) when you need shared API or configuration context.

Returns the latest batch of **search prompt suggestions** + **key events** the enrichment `prompt-suggester` computed from recent segments and wrote to VastDB (`vss-prompts-events`). Requires a JWT (`$retrieval-login`).

## Request — `GET /api/v1/suggestions`

```bash
curl -s "$BACKEND/api/v1/suggestions" -H "Authorization: Bearer $TOKEN"
```

Content is ACL-filtered to the caller. Use the returned prompts as ready-to-run `query` strings for `$retrieval-search`, and key events as highlights.

## Depends on the enrichment pipeline

These come from the scheduled `prompt-suggester` enrichment job writing to `vss-prompts-events`. If empty:
- The enrichment job may not have run yet.
- Lookback window found no new segments — logs show `[SUGGEST] No new videos in lookback window`.
- Check `$retrieval-dashboard` that segments are actually being indexed.

## Agent instructions

1. Ensure a JWT.
2. Treat items as suggestions, not guarantees — feed prompts into `$retrieval-search`.
3. If empty, check recent ingest (`$retrieval-dashboard`) before assuming a bug.
