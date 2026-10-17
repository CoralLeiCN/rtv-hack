# VAST Builders Challenge

This repository contains instructions and skills for building video agents on an
already deployed VSS stack. Build on its search, metadata, detections, and video
APIs. Do not rebuild or redeploy the shared DataEngine ingest pipeline.

### Subagent delegation

If at any point you can parallelize work by delegating tasks to another agent
(no matter if you are the root or subagent), you should do so using collaboration
tools if it could save time or improve quality.

## Writing style

Use plain language over jargon, and reference technical details only to the
degree that it helps illustrate an idea or your work to the user. Communicate
complex concepts in a clear and cohesive manner, and calibrate your writing to
the level of background knowledge assumed from the user's prompt and context.

## Test and verification

Do not write tests for reversible, low-impact changes that mirror the
implementation. If you do choose to verify your work with tests, make sure that
the tests are meaningful and necessary to verify implementation.

Run tests appropriate to the change and complete required checks. Once those
pass, broaden or repeat testing only when new changes, failures, or unresolved
concerns justify it; otherwise, continue toward completing the task.

## Codex skills

- Use the matching skill in `.agents/skills/` before writing raw REST calls.
  Each folder name matches its `SKILL.md` name; invoke it as `$skill-name` or
  describe the task. See `docs/CODEX.md` for the catalog.
- Use `retrieval-*` for backend authentication, search, playback, and health;
  `ingest-*` for upload or re-ingest; `gpu-*` for model endpoints; and
  `vast-database-*` for direct SDK access.
- The `deploy-*` skills concern retrieval apps and custom apps only. Use them
  when deployment work is requested; ordinary API use needs no redeployment.
- Read the relevant `.agents/references/` guide when broader API context is
  needed. The original `.cursor/` files support Cursor; Codex uses `.agents/`.

## Environment and credentials

- Live services are configured on the workshop VM. Local documentation and code
  edits do not require VM access. Run live operations where the team's network
  access and configuration are available.
- Read configuration from existing environment variables and the VM's absolute
  `/config/` directory. `config.example` documents the variable names. Do not
  search `team-configs/`, invent credentials or endpoints, or edit `/etc/hosts`.
- If a live workflow lacks configuration, report the missing variable or file
  and request access to the configured environment. Do not ask for secrets to be
  pasted into chat.
- To inspect available variables, list names only:
  `env | cut -d= -f1 | sort`. Never run bare `env` or `printenv`.
- Never print, log, or commit passwords, keys, JWTs, bearer tokens, or real
  configuration values. Keep credentials and generated secrets outside Git.
- Shell examples are Bash. Examples using `mapfile` require Bash 4 or newer on
  the workshop VM. Do not source team config into zsh, where `USERNAME` is
  reserved. Keep configuration, login, and dependent calls in the same shell
  session, or load configuration again without printing it.

## Working with the stack

- Prefer re-ingest for existing archive content; upload is for new files.
- Resolve filter keys and values with `$retrieval-list-metadata`. If search is
  empty, check filters and indexing progress with `$retrieval-dashboard` before
  assuming a bug.
- Keep direct DB operations in the team's bucket. Use the data VIP for writes;
  the Query Engine VIP is an optional read endpoint. Embeddings use 256 dimensions.
- For workshop deliverables, build a web app, CLI, or script that can be demoed
  from the VM. Use `README.md` for the workshop flow and
  `ARCHITECTURE_REFERENCE.md` for stack boundaries and project ideas.
- Collect missing choices and confirmations with `request_user_input_async`
  when available, or a concise chat question. Respect choices and authorization
  already supplied in the conversation.
- When blocked on the live stack, use `$ask-cosmos` to check health and prepare
  a redacted support note. That skill never posts or sends the note.
- There is no submission skill; follow the organizers' submission instructions.
