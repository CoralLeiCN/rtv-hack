# Ranger Duck submission draft

[Submission form](https://tokensand.com/vastlondon/submit). Local draft; not
submitted. Fields and length limits await sign-in. Team and sponsor details: TBD.

## Project name

Ranger Duck

## Tagline

From wildlife video to robot action, with evidence you can inspect.

## Short description

Ranger Duck searches wildlife footage and lets a simulated Microduck imitate a
reviewed behavior. The encounter, reference clip, timestamps, and robot action
appear on one page.

## Project description

A scripted deer encounter triggers live VSS archive search. Users watch a
returned clip and select Copy this behavior to trigger a bounded robot movement.
Only an exact, visually reviewed reference enables Copy; captions and scenario
labels alone cannot authorize action.

The verified feeding demo turns a deer-feeding reference into one ground-pick
movement, with completion confirmed by the controller. Unreviewed, changed,
unsupported, or wrong-species clips remain playable without enabling imitation.

## How we built it

React, TypeScript, and Three.js provide the interface. The official Microduck
simulator runs MuJoCo physics and pretrained ONNX policies in the browser.
FastAPI connects to VSS search, metadata, and video APIs, keeps credentials
server-side, and supports seekable playback.

Reviews bind behavior to the exact source, interval, and caption hash. Only a
matching current search result enables action. Reset or reference changes cancel
movement; stale responses cannot affect new encounters. Labeled replay reuses a
prior live result and still streams archive footage.

## Verification

Recorded on 17 October 2026: 41 backend tests, 15 frontend/adapter tests, and the
production build passed. Live checks covered search, playback, seeking, session
isolation, replay, and blocked imitation for unreviewed clips.

The full feeding flow passed in the browser using a reviewed VM reference,
through retrieval, playback, Copy, and controller-confirmed completion. Ground
pick, bounded walking, and standing also passed individual controller checks.
These results have not been revalidated against the current deployment.

## Limitations

The encounter is scripted and the robot simulated. There is no live camera
recognition, new policy training, or joint-trajectory copying. Walking and
standing still need reviewed footage for full imitation demos.

The committed review manifest is empty to protect private source identities.
Reproduction requires workshop access and local footage review. Search includes
VSS synthesis; the UI displays measured latency.

## Sponsor tools — TBD

Confirm at least three eligible tools actually used. Integrations below do not
establish three-tool eligibility.

| Technology | Role | To confirm |
| --- | --- | --- |
| VAST / VSS | Archive search, metadata, playback | How the stack is counted |
| NVIDIA VSS Blueprint | Provided video search stack | Whether it counts separately from VAST |
| Pollen Robotics / Hugging Face Microduck | Browser physics and movement policies | Sponsor eligibility |
| Additional tool(s) | TBD | Actual use and eligibility |

Do not list Cursor, W&B, or CoreWeave solely because credits or infrastructure
were available.

## Team and links — TBD

| Detail | Value |
| --- | --- |
| Team name / number | TBD |
| All members | TBD |
| Submitter / contact | TBD |
| Repository accessible to judges | TBD |
| Demo URL / access instructions | TBD |
| Demo video, if requested | TBD |

## Supporting documentation

- [Demo script](DEMO_SCRIPT.md)
- [Submission requirements](SUBMISSION.md)
- [App setup](../apps/ranger-duck/README.md)
- [Verification record](RANGER_DUCK_CONTEXT.md#implementation-and-verification)
- [Reference review and backend setup](../apps/ranger-duck/backend/README.md)
- [API contract](RANGER_DUCK_API.md)
