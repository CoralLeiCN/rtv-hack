# Capture and optional W&B export

Commands run from the repository root using the shared `.venv` from
[development setup](../development.md). Configure real values privately in the
application environment selected by `RANGER_ENV_FILE`.

Normal backend startup records private JSONL events in `apps/ranger-duck/backend/.captures/`
(override with `RANGER_CAPTURE_DIR`). Files are owner-only and ignored by Git.
Each event has a timestamp, event ID and run ID linking:

- The complete archive search response, before filtering, normalization, deduplication
  or selection. This includes every returned hit and its original source, caption,
  score, segment times and other returned fields; it does not download video bytes.
- Codex instructions, context, output schema, raw final output, validated decision
  and returned explanation. Private internal reasoning is not available.
- Unified run action issuance and validated browser-reported outcomes, including
  round/attempt IDs, simulator state, playback and companion status. Fixed and
  adaptive runs share the same capture path; replay outcomes are labelled.
  Pausing an issued attempt without a report records an unknown outcome, not
  completion. Legacy encounter and loop endpoints retain their capture events.

Credentials, bearer tokens and signed URL query strings are stripped before
writing. Stable video source identities remain private training provenance. Capture
does not sample or truncate search hits/captions. `/demo-api/health` exposes
`capture_enabled` and `capture_write_failed`; a disk failure is also logged
without payloads. Unified runs stop issuing actions if capture storage fails;
outcomes must be saved before acknowledgement.

To send captures to W&B Weave, create a team-only project, set
`RANGER_WEAVE_PROJECT=ENTITY/PROJECT` and `WANDB_API_KEY` privately in `apps/ranger-duck/backend/.env` (or use an existing SDK login). Start the app and exporter together so both restart from the same saved configuration:

```bash
.venv/bin/python -m pip install -e './apps/ranger-duck/backend[capture]'
.venv/bin/ranger-duck-serve --port 18000
```

For another checkout, use `.venv/bin/ranger-duck-serve --env-file /absolute/path/to/backend/.env`. The startup log prints the selected file path, never its values. Secrets stay outside Git and are not copied into future worktrees. Install the backend `capture` extra in each checkout's Python environment. Captures remain local to the running checkout unless `RANGER_CAPTURE_DIR` is explicitly set.

For a separately managed backend, run `.venv/bin/ranger-duck-export-captures --follow` alongside it; do not also use the combined launcher. Omit `--follow` for a one-time export. The exporter reads the same `.env`, uploads
pending events, and verifies their event IDs by reading them back from Weave.
Private per-project acknowledgement files let subsequent runs skip confirmed
events. Stop the exporter before starting another against the same directory.
The continuous exporter also retries initialization failures after restart. An interrupted upload may create a duplicate remote call; `event_id` is the
deduplication key. Use `run_id` to group decisions, results and outcomes in Weave.
Original event time and elapsed duration are retained as attributes; the Weave
call itself is created at export time. Local files remain the durable copy when
W&B is unavailable. This adds capture only, with no labelling or training job.
