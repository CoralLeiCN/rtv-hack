# Evidence and optional human review

Commands run from the repository root using the shared `.venv` from
[development setup](../development.md). Runtime selection rules belong to
[behavior](../reference/behavior.md); motion limits belong to
[the simulator reference](../reference/simulator.md).

The shipped [references.empty.json](../../apps/ranger-duck/backend/references.empty.json) contains zero human reviews. Live captions can enable bounded actions with `action_basis: "video_caption"`, `review_status: "unreviewed"`, and `eligibility_reason: "caption_behavior_match"`. `inferred_behavior`, `interaction_partner`, and `action_reason` explain what is copied and where the motion is approximate. `interaction_partner` is null for solitary footage; it is not inferred from the search query. The original hissing approximation is a standing hold, so a hiss-only clip no longer qualifies. A separately supported active behavior in the clip may qualify; the duck does not synthesize a hiss. A caption action's opaque evidence ID binds its exact source, parent, interval, and original caption hash. It does not expose source identities.

The Codex decision agent (`gpt-6-luna`) interprets selected-species behavior,
actor attribution, negation, uncertainty and paired roles from complete captions.
It chooses walking, beak dipping, vertical head nodding or sitting/standing, or
skips with an explanation. The backend does not preselect a motion with phrase
rules or impose a fixed motion preference. It enforces source/parent/interval
provenance, current exact reviews, literal evidence quotes and bounded commands.
An exact review remains authoritative; passive exact reviews do not authorize
retrieval-driven actions. Model interpretation is inferred evidence, not a visual
review or proof that the action happened. See [runtime behavior](../reference/behavior.md#evidence-and-action-selection).

An optional exact human review authorizes its supported behavior without requiring a partner. Previously reviewed solitary feeding footage is valid again when its source, parent, interval, caption hash, species, and behavior still match. Optional `interaction_partner` and `interaction_evidence` can describe a reviewed interaction but are not needed for a solitary pose. A stale, invalid, unsupported, or wrong-species review blocks action instead of silently falling back to inference. No downloaded/private footage or real source identities belong in Git.

Store a raw archive search JSON response in a private file **outside the repo**, then prepare a draft:

```bash
.venv/bin/python -m ranger_duck.review draft --input /tmp/ranger-search.json --output /tmp/ranger-references.json
```

The input must contain `results[]` with exact segment fields `source`, `original_video`, `reasoning_content`, `segment_start_sec`, and `segment_end_sec`. The local experiment query summaries and browser API responses are not raw archive response files. Drafts are unreviewed and written with owner-only permissions; the command prints only counts.

Watch the corresponding actual segment through the authorized application playback. Only after verifying its animal and visible behavior:

```bash
.venv/bin/python -m ranger_duck.review approve \
  --manifest /tmp/ranger-references.json --index 0 \
  --evidence-id reference-01 --animal deer --behavior feeding \
  --interaction-partner deer \
  --interaction-evidence 'Two deer graze together side by side.' \
  --source-label 'Reviewed feeding example' --confirm-viewed
.venv/bin/python -m ranger_duck.review validate --manifest /tmp/ranger-references.json
export RANGER_REFERENCE_MANIFEST=/tmp/ranger-references.json
```

Restart the service to load the manifest. The CLI does not watch clips or infer labels. `--confirm-viewed` records the operator's explicit confirmation; it is not machine verification.

Each review binds the **exact** segment source, parent identity, start/end, and SHA-256 of the original caption. A replaced source, changed caption, incomplete timing, duplicate match, unsupported behavior, or species mismatch disables imitation. A review cannot add a result absent from the current live search. The explicit review evidence is interpreted independently of the scenario's behavior hint. Write the review description only after verifying the actual footage; the sample text above is a format example.

The review CLI retains these pose labels:

| Reviewed behavior | Primitive | Cancellation ceiling |
| --- | --- | --- |
| `feeding` | `ground_pick` | 8000 ms |
| `walking` | `short_walk` | 2000 ms |
| `standing` | `stand_hold` | 3000 ms |

The [controller inventory](../reference/simulator.md#controller-action-contract)
lists six internal primitives and their motion windows. Retrieval uses only four
active primitives; scan/hold cannot occupy queue slots.

Sitting does not imply lying down, and merely looking up remains a head-attention approximation unless vertical head movement is explicit. The tested policy cannot reliably walk backward: reverse steps cannot be reproduced by a forward walk. The agent interprets direction in context: walking away does not necessarily mean walking backward. A clip with no supported motion receives an agent skip explanation. Unsupported jumping, lying, fighting, biting, and contact do not become motions. A ceiling is not evidence of completion. The frontend observes the controller's actual completion and recovery.
