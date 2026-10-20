# Testing and validation

Commands below run from the repository root after [development installation](development.md).
Run checks appropriate to the changed component. Test success and live model
validation are different claims; recorded earlier results are in [status](status.md).

## Select checks

| Change | Relevant checks |
| --- | --- |
| Documentation only | Relative links, anchors, file paths and command definitions; `git diff --check` |
| Simple search UI or adapter | Root JavaScript tests and Python application tests |
| Ranger backend, evidence or run state | Python tests; frontend contract/session tests when the wire contract changes |
| Frontend or simulator | Frontend tests and production build; browser execution checks for motion/playback changes |
| Archive ingestion, schema, index or media | Python tests and disposable Postgres/Qdrant/FFmpeg integration image |
| Models or deployment | Relevant fixture checks plus the explicitly configured live smoke test below |

## Local fixture and application checks

```bash
.venv/bin/python -m pytest tests apps/ranger-duck/backend/tests services/archive/tests -q
node --test tests/*.test.mjs
npm --prefix apps/ranger-duck/frontend test
npm --prefix apps/ranger-duck/frontend run build
git diff --check
```

`make test` runs the root JavaScript and combined Python commands; it does not
run the Ranger frontend suite or build. The frontend build performs TypeScript
checking followed by Vite. There is no separate repository lint command.

Python tests use explicit model/agent fixtures. Archive database integration tests
skip when `TEST_DATABASE_URL` is absent. If selecting it locally, use only a
disposable database: the tests truncate `archive_*` tables. FFmpeg/FFprobe are
required for media integration. Success with skips does not establish full coverage.

## Disposable archive integration

```bash
docker build -f services/archive/Dockerfile.test -t rtv-hack-archive-test:local .
docker run --rm rtv-hack-archive-test:local
```

The image starts disposable Postgres, generates tiny synthetic videos with FFmpeg,
uses Qdrant local storage and runs all three Python test directories. Model outputs
are fixtures. It does not connect to Neon, download model weights or test
the deployed Qdrant server. Do not pass private environment files or mount real
media/database directories into this test container.

## Browser and simulator checks

Download the pinned public simulator assets for interactive checks:

```bash
python3 apps/ranger-duck/scripts/simulator-assets.py
python3 apps/ranger-duck/scripts/simulator-assets.py --check
```

The second command is an offline size/hash check of an existing download.
Start the app using the [startup guide](../apps/ranger-duck/README.md#run).
For execution changes, check Loop off queue repetition, a second Loop on round,
boundary-only toggling, video end plus actual motion completion, Pause/Resume,
Reset, hidden-tab pause, replay and stale-response rejection. Check that separate
tabs retain independent runs and physics stays continuous between references.
Test sitting cancellation through its native standing return. Observe browser
errors and report the environment/scenario used, rather than generalizing one
frame-rate or timing measurement. See [runtime behavior](reference/behavior.md).

## Live model and deployment smoke test

Requires an explicitly selected private configuration, configured Neon, a running
Qdrant server, pinned EmbeddingGemma weights, a pinned Cosmos Reasoner deployment
and a real video with known provenance. Follow [archive operations](guides/archive.md)
for initialization and ingestion commands.

1. Check process liveness and authenticated archive readiness. Readiness checks
   database/schema, vector dimensions and media storage, not Cosmos inference.
2. Ingest a new video without imported captions, then run the worker. Confirm
   successful indexing with stable segment IDs and recorded model revisions.
3. Perform an authenticated search to exercise real query embeddings; inspect
   relevance and exact returned captions. Failed segments must remain hidden.
4. Play and seek returned segments through the authorized application path.
5. Run a Ranger Duck encounter and an adaptive follow-up round. Confirm inferred
   versus reviewed labels, original ranks and observed simulator outcomes.

Record model/package revisions, checks, results and missing prerequisites without
publishing private configuration or source identities. Fixture captions, synthetic
embeddings and imported captions cannot establish live Cosmos validation.
