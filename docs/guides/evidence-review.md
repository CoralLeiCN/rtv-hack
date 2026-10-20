# Evidence and optional human review

Commands run from the repository root using the shared `.venv` from
[development setup](../development.md). Runtime selection rules belong to
[behavior](../reference/behavior.md); motion limits belong to
[the simulator reference](../reference/simulator.md).

The shipped [references.empty.json](../../apps/ranger-duck/backend/references.empty.json) contains zero human reviews. Live captions can enable bounded actions with `action_basis: "video_caption"`, `review_status: "unreviewed"`, and `eligibility_reason: "caption_behavior_match"`. `inferred_behavior`, `interaction_partner`, and `action_reason` explain what is copied and where the motion is approximate. `interaction_partner` is null for solitary footage; it is not inferred from the search query. The original hissing approximation is a standing hold, so a hiss-only clip no longer qualifies. A separately supported active behavior in the clip may qualify; the duck does not synthesize a hiss. A caption action's opaque evidence ID binds its exact source, parent, interval, and original caption hash. It does not expose source identities.

The classifier rejects incomplete provenance, absent or wrong species, unsupported behavior, and local negation or uncertainty. Single-animal feeding, walking, sitting and explicit vertical head motion can authorize retrieval-selected approximations. Standing, watching, head scanning and hiss-only poses are excluded from action selection. Pair-specific labels still require evidence of a pair. The underlying controller mapping for watching is `head_scan`, which is now excluded from retrieval selection; explicit shared-object attention and focal behavior receive their own labels. Parallel toy attention is never mislabeled as greeting or hissing. Unambiguous animal pronouns can resolve to a companion only when a pair is established and there is no competing object referent. Presence alone does not authorize a movement. Returned behavior can differ from the selected encounter; the UI displays the actual inference. These are caption-derived approximations, not learned imitation or a claim of visual review.

The controller inventory still contains six primitives. Retrieval selection in both modes excludes `head_scan` and `stand_hold`, including passive exact reviews. The active-only classifier prefers `short_walk`, `ground_pick`, `head_nod`, then `sit_cycle`, even when the active behavior appears later in the caption. A caption describing looking plus sitting can still supply `sit_cycle`; it is not discarded merely because looking appears first. Semantic specificity breaks ties within a primitive. It binds the predicate to the selected animal; a moving toy or a walking person cannot supply the animal's motion. An ambiguous pronoun stays conservative. This preference selects the action for one clip; it never reranks archive results or changes the first-three-compatible rule. An exact human review remains authoritative even when its caption also mentions a more active behavior.

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

Sitting does not imply lying down, and merely looking up remains a head-attention approximation unless vertical head movement is explicit. The tested policy cannot reliably walk backward: retreat itself never becomes a forward walk or a still pause. A clip containing retreat may still supply a separately described supported motion; otherwise it remains ineligible with reason `unsupported_retreat`. Unsupported jumping, lying, fighting, biting, and contact do not become motions. A ceiling is not evidence of completion. The frontend observes the controller's actual completion and recovery.
