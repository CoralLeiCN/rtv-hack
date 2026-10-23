# Reliability and evaluation improvements — 21 October 2026

## Goal and scope

Address the four findings from the repository review: expired playback during
fixed-queue execution, limited semantic evaluation, opaque ingestion failures,
and mismatched frontend/backend development ports.

## Evidence and affected contracts

- A fixture reproduced a ready second pass whose expired clip returns 404.
  Run/session expiry belongs to the runtime and API references.
- Connected live validation covers one walking cat clip. Literal quote checks
  do not establish semantic correctness. Evaluation belongs to testing/status.
- Worker exceptions currently persist only `ingestion_failed`. Preserve private
  configuration, advisory-lock session ownership and retry/publication rules.
- Vite defaults to port 8000; Ranger defaults to 18000.

## Ordered work

1. Define and implement clean expiry handling before issuing further actions;
   cover queue boundaries, resume, replay and session isolation.
2. Add safe stage-specific ingestion diagnostics with identifiers and timings,
   without logging exception bodies or changing worker database ownership.
3. Align frontend defaults and the owning development guide.
4. Add repeatable action-selection evaluation and reviewed-video coverage
   accounting; run available live evaluation with explicitly selected settings.
5. Run applicable fixture, build and disposable integration checks, review the
   diff, and record live results separately from fixtures.

## Acceptance checks

- Expired playback cannot produce an executable next attempt; no hidden search
  or invented completion, and live session/cancellation invariants still hold.
- Failure stages distinguish configuration, media, captioning, embedding, index
  and database operations; errors/logs contain only safe diagnostic fields.
- Evaluation reports false selections, missed supported actions, role errors,
  failures and coverage, separating supplied captions from reviewed videos.
- Root tests, frontend tests/build, disposable archive integration, diff and
  documentation checks pass, or missing prerequisites are explicitly recorded.

## Decisions and progress

- Keep the existing single-worker and bounded-capability architecture.
- The user selected `.env` for live checks. Existing local archive, Cosmos and
  signed-in Codex services were available after allowing local network access.
- Expired rounds pause cleanly and advertise a reason; active run requests renew
  the session cookie without extending reference expiry. Resume explicitly plans
  fresh references. No simulation or playback outcome is fabricated.
- Added a production-path evaluator, a supplied-caption regression suite, and a
  separate private ten-video set with exact Cosmos captions and hash-bound,
  explicitly labeled agent sampled-frame reviews. No runtime human reviews were
  created, and no evaluation videos were imported into the live archive.
- The video evaluation exposed generic-head-motion and grooming mapping errors.
  Clarified the agent instructions and added supplied-caption regressions, while
  retaining semantic decisions in the agent and exact-evidence checks in code.

## Results

- Expired references now pause before the next attempt, with a visible explanation
  and an explicit Resume path. Browser cookie renewal matches server activity;
  reference capabilities keep their fixed lifetime and session ownership.
- Ingestion records safe configuration/media/captioning/embedding/indexing/database
  failure codes, plus structured stage timings and job/segment UUIDs. Exception
  bodies and private configuration never enter those diagnostics. Retry, index
  publication and advisory-lock behavior remain intact.
- Vite now uses port 18000 by default, matching Ranger. Updated owning guides.
- Added the production-path evaluator and 34 supplied-caption cases. Instructions
  clarify that unspecified head motion is not vertical nodding, body grooming is
  not feeding, and an explicitly seated pose supports sit/stand.

### Fixture checks

- `make test`: 15 root JavaScript tests and 372 Python tests passed locally; 17
  disposable-database checks skipped on the host.
- Source-only Linux integration image: 389 Python tests passed with no skips,
  disposable Postgres 15, local Qdrant and synthetic FFmpeg media. No private
  configuration or archive media was included. The container removed itself.
- Frontend: 108 tests and the TypeScript/Vite production build passed. Existing
  MuJoCo module-externalization and bundle-size warnings remain.
- Whitespace and changed-document link checks passed.

### Live planner and video evaluation

- Initial 28-caption suite: 56/56 decisions passed over two runs. After adding
  regression cases and clarifying instructions, all 68/68 decisions passed for
  the 34-case suite, with no false selections, missed actions or role errors.
- Downloaded ten samples at pinned revisions from
  [Meow-10k](https://huggingface.co/datasets/smgjch/meow-10k) and
  [Prompting-MammAlps](https://huggingface.co/datasets/amathislab/Prompting-MammAlps).
  All ten matched upstream SHA-256 values. Six cat-source and four wildlife-source
  samples remain in ignored private evaluation storage with licence/provenance
  records, source checksums, derived intervals and exact segment checksums.
- The configured local Cosmos service captioned every evaluated segment. The
  evaluation did not import dataset captions or index these clips into the live
  archive. Expected labels came from explicit agent inspection of ordered frames
  at two fps, with source-resolution checks for ambiguous distant subjects; they
  are **not human video reviews or full temporal validation**.
- The private suite contains expected cases for both species, all four actions,
  paired roles, uncertainty, unsupported motion and wrong species. Its source,
  clip and caption hashes are bound to the recorded review. Initial decisions
  passed 9/20 attempts; after instruction clarification, 14/20 passed across two
  runs, with two false selections, four missed actions and two role mismatches
  (these categories overlap). Both video runs correctly returned a failing exit
  status; coverage completion is not a claim that the model is accurate.
- The final failed cases are a pose disagreement in a grooming clip, missing
  selected-species evidence in a grazing caption, and a missing second actor in
  a paired-deer caption. The planner cannot recover observations absent from the
  caption. Human review is needed before treating these sampled-frame labels as
  a benchmark; further caption-model evaluation remains open.

### Browser expiry check

An isolated Ranger process used the selected `.env`, the existing real archive,
the new production frontend and a 30-second reference lifetime. The browser
completed three walking passes with real video ending, duck completion and a
completed stationary companion. Captures contain exactly one archive search,
two model decisions, three issued attempts and three acknowledged outcomes.
Simulation time advanced through 45.78, 62.44 and 79.56 seconds without reset.
The run then showed “Reference access expired. Resume searches for fresh
references.” No fourth action or hidden search was issued. The later Resume
after this deliberately short idle-session lifetime correctly required a new
run. Fixture checks separately verify immediate Resume retrieves fresh references.
The temporary browser tab and backend process were closed after verification.

## Handoff and remaining limits

All four requested improvements are implemented. Procedures and contracts live
in [testing](../testing.md), [runtime behavior](../reference/behavior.md),
[the API reference](../reference/ranger-duck-api.md), and
[archive operations](../guides/archive.md). Private suites, exact model outputs,
reports and the browser screenshot remain in ignored local research storage.
No new runtime human review was approved. The broader video check did not execute
all four simulator primitives or validate Neon/remote Cosmos deployment. The
small selected sample and two repetitions do not establish population accuracy.
