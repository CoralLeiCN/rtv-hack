# Archive search and obsolete vector cleanup

## Goal and scope

Request only the desired number of Qdrant matches, refill rejected matches, and
avoid silent empty results when validation exhausts its search budget. Remove
superseded vectors after successful publication and provide explicit maintenance
for existing orphans. No live archive cleanup or infrastructure changes are in scope.

## Evidence and contracts

Search currently requests 100 candidates per page, at most ten times. Postgres
validates the current vector ID, publication flag, model identity and tags.
Retry-specific vector IDs prevent delayed old workers from overwriting new work,
but obsolete points are never deleted. Preserve these publication and lock rules.

## Steps

1. Request `top_k`, then only the shortfall, with at most ten requests; distinguish
   budget exhaustion from an exhausted index and propagate a safe application error.
2. Delete the previous point only after successful replacement publication.
3. Add bounded orphan scanning with dry-run and apply modes under the worker lock;
   retain every referenced point, including unpublished points and other models.
4. Update the owning specification/operations guide and add regression checks.

## Acceptance checks

- A clean search uses one request for `top_k`; rejected matches trigger shortfall
  requests while preserving order, filters and publication checks.
- True index exhaustion returns fewer results; request-budget exhaustion is an
  explicit error, including through both application adapters.
- Successful retries remove previous points without changing public IDs/captions.
- Cleanup failure cannot invalidate a successfully published replacement.
- Orphan cleanup retains referenced unpublished points, takes the worker lock,
  stops on lock loss, and deletes only explicit unreferenced IDs.
- Run Python/root JavaScript tests, disposable integration if available, and diff
  and documentation checks. Model inference is outside this change.

## Decisions and results

- Keep the existing ten-request bound; small `top_k` no longer means fetching
  100 candidates per call. Return an error when a full last page leaves a deficit.
- Cleanup never deletes media and never uses tag/model filters to infer orphans.
- Implemented small search/refill requests, explicit maintenance errors through
  both application adapters, deletion after publication and lock-protected orphan
  cleanup with dry-run and apply modes.
- `make test VENV=/tmp/rtv-review-venv` passed: 335 Python checks and 15 root
  JavaScript checks, with 17 database integration checks skipped. Tests selected
  an empty environment file and explicitly unset `TEST_DATABASE_URL`.
- All 19 focused search/maintenance checks passed. The recovery reproduction
  uses real in-memory Qdrant plus fixture metadata, proves a
  capped search fails explicitly, and verifies cleanup restores the valid match.
- CLI help, documentation links/anchors and `git diff --check` passed.
- Docker is installed but its daemon is unavailable, so disposable Postgres
  integration was not run. Added integration cases cover repeated retries,
  cleanup failure after publication, and retaining unpublished/other-model points.
- Model inference, deployed Qdrant and Neon were not exercised. No live cleanup
  was performed. Ranger frontend source and response shapes are unchanged.
  The simple UI adapter adds an error code for the capped search; browser tests
  verify its fixed maintenance message, redaction and timeout handling.
