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

A dedicated local Postgres deployment can exercise the development path. Report
that separately from Neon validation; it must never double as the disposable
integration-test database.

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

## Semantic action evaluation

The versioned [caption suite](../apps/ranger-duck/evaluation/caption-cases.json)
contains 34 supplied examples covering cat/deer, all four actions, paired actors,
negation, uncertainty, wrong species/actors and unsupported motion. It exercises
the production `EncounterService.actions` path, including quotation, provenance
and role checks. Expected labels are withheld from the model. It does not run
video understanding, retrieval or simulation.
Regression cases distinguish unspecified head motion from a vertical nod,
grooming from feeding, and an upright seated pose from lying down.

```bash
.venv/bin/python -m ranger_duck.evaluation validate --suite apps/ranger-duck/evaluation/caption-cases.json
.venv/bin/python -m ranger_duck.evaluation run --suite apps/ranger-duck/evaluation/caption-cases.json --repeats 2 --output /tmp/ranger-caption-evaluation.json
```

`run` requires the existing Codex CLI login and uses the production `gpt-6-luna`
planner and its deadline, without hidden retries. Reports are created exclusively
with owner-only permissions. They include suite/instruction hashes, model,
timestamp, case IDs and scores, without captions, source identities or private
paths. Nonzero exit means invalid inputs (1), failed cases or required coverage
missing (2). Repeated runs need a new output filename.

For real-video evaluation, prepare a **private** suite using the same case fields
and `evidence_kind: reviewed_video`. Each case additionally needs a `video` object:
absolute `path` to the exact evaluated clip, its `sha256`, exact `caption_sha256`,
source-relative `start_sec` and `end_sec`,
`source_url`, immutable `source_revision`, `licence`, actual `caption_model` and
`caption_revision`, `review_method` (`human_video` or `agent_sampled_frames`),
`reviewed_by`, `review_note`, and `confirmed_viewed: true`.
Use the actual Cosmos caption, never the dataset description or a rewritten
caption. Inspect the clip before assigning `expected_actions` (empty for rejection),
optional `expected_grounding`, `expected_companion` and `expected_duck_evidence`.
State who reviewed it and how; an agent's sampled-frame inspection is not a human
review or full temporal validation. The evaluator verifies file/caption hashes
and viewing confirmation, but cannot independently prove the review's truth or
the model provenance supplied by its operator. Evaluation labels are never loaded
as runtime human-review overrides.
The runner derives local evaluation identities from checksums and provenance;
they are never registered as public archive IDs or playback capabilities.

Run the private suite with `--require-video-coverage` to fail on incomplete video
coverage as well as incorrect decisions. Keep these clips separate from the real
archive unless ingestion is explicitly part of the evaluation. Store licences,
revisions, checksums and any derived-clip intervals beside them.

Reports separate `supplied_caption` and `reviewed_video`; absent groups say
`not_run`. Coverage lists missing species, actions and challenge categories.
Video groups also report counts by review method, keeping sampled-frame labels
distinct from human video review.
Both groups require both species and all four actions; video coverage requires
paired, supported, unsupported, uncertain and wrong-species cases. Negation is
additionally required for the supplied-caption language tests.
False-selection rate divides unsupported selections by all issued selections;
missed-action rate divides cases with no correct supported selection by cases
with expected active actions. A wrong action can count in both. Role mismatches
are counted separately. Agent errors fail affected cases, including expected
rejections, and count as misses for expected active cases. Zero denominators are
null. Coverage does not establish broad dataset accuracy; report fixture checks,
caption-only live evaluation, reviewed-video evaluation and actual simulator
execution separately in [status](status.md).
