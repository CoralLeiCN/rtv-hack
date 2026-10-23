# Original Ranger Duck design handoff

> Historical design export. Its Copy flow, reviewed-only gating, sample API fields
> and timing examples are superseded. For implementation use the current
> [behavior](../reference/behavior.md), [API](../reference/ranger-duck-api.md) and
> [visual guide](../../apps/ranger-duck/design/README.md). Assets remain in
> [apps/ranger-duck/design](../../apps/ranger-duck/design/). Relative paths and
> imperative prose in the preserved export below refer to that original folder
> and do not override current contracts.

Design export for the single-page demo described in
[`docs/RANGER_DUCK_PLAN.md`](../reference/behavior.md). This folder is
the visual and interaction spec. The implementation lives in `../frontend/`
(React + Three.js/MuJoCo) and `../backend/` (FastAPI). The current wire contract
is [`docs/RANGER_DUCK_API.md`](../reference/ranger-duck-api.md); the illustrative
field names below are adapted by the frontend.

| File | What it is |
| --- | --- |
| `ranger-duck-mockup.html` | Standalone, dependency-free mockup. Open it in a browser. Vanilla JS, mock data, full state machine, same CSS the real app should ship. |
| `ranger-duck.dc.html` | Source of the interactive artboard on the Claude Design canvas (https://claude.ai/artifact/JaHsTZCNDBN2sodjUEEt1y). Needs that canvas runtime; kept for reference only. |

The mockup is the reference for layout, tokens, copy, and behavior. Reuse its
CSS and markup structure directly; replace the SVG scene with the Three.js /
MuJoCo canvas, and replace the mock data with the `/demo-api` routes.

## Current interaction update

The current page combines Encounter and Loop with one Loop toggle and one agent pipeline. Off repeats the first three compatible active video actions; on generates a fresh query after those actions using actual outcomes. Both settings use the same query, search, batch action planner, and player. The page retains this export's visual design but supersedes its manual Copy flow and reviewed-only gating. One animal stays outside the box; the duck faces and approaches it before acting and keeps its physics state across videos and toggle changes. The original animal models remain in use. Single-animal footage is eligible; incompatible and passive results are filtered before selecting the three actions. The interface shows inferred versus reviewed action basis, query/retrieval/action timings, and Start, Pause/Resume, Reset, and saved-round replay controls. See the current plan and API contract linked above; the original HTML mockups and state machine below remain historical design references.

With Loop on, each new round after the first randomly selects a different interaction for the same animal. Show that round's actual interaction near the scene and query. Change the existing actor's behavior without replacing it or resetting the duck. The selected preset remains the first-round seed; Loop off retains its current encounter and queue.

## Design language

Borrowed from the Microduck product page (pollen-robotics.com/microduck) with a
ranger field-camera twist. Tokens are declared on `:root` in the mockup.

| Token | Value | Use |
| --- | --- | --- |
| `--ink` / `--ink-2` / `--ink-3` | `#08080c` / `#101018` / `#1c1c28` | Page ground, panels, hover |
| `--rule` | `#2a2a36` | Inactive borders |
| `--paper` / `--paper-2` | `#faf8f2` / `#f2ecdd` | Text, active borders, sticker fill |
| `--muted` / `--muted-2` / `--muted-3` | `#B8B2A4` / `#7a756b` / `#4a463f` | Secondary text, labels, disabled |
| `--orange` | `#FF7A2F` | Primary action, current stage, selected card, allowed primitive |
| `--yellow` | `#FFD23F` | Query text, duck, mode toggle, hard-shadow on primary |
| `--pink` | `#FF2FA8` | Failure, no-match, REC dot, ineligible badge |
| `--teal` | `#2FF0E6` | Reviewed badge, encounter zone, live status, action progress |
| `--moss*` / `--bark*` | greens / browns | Scene only (clearing, deer) |

- **Type**: Anton (uppercase, `letter-spacing: 0.02–0.04em`) for the title,
  buttons, section heads, and stage strip. DM Sans for body. DM Mono for every
  value that comes from a machine: query, timings, IDs, hashes, HUD text.
  Labels are 11px DM Sans 700, `letter-spacing: 0.14em`, uppercase, muted.
- **Shape**: no border radius anywhere. Borders 2px (passive) or 3px (active,
  panels). Hard offset shadows instead of blur: `6px 6px 0 <color>` on buttons
  and the selected card, `10px 10px 0` on the scene, `5px 5px 0` on the current
  stage pill. Buttons press by translating `4px 4px` and shrinking the shadow.
- **Disabled** controls switch to a dashed `#4a463f` border, no shadow, muted
  text. This is the visual for "Copy unavailable", so keep it distinct.
- **Trail-cam HUD**: mono 11px uppercase text pinned to the corners of the
  scene and of the video frame (CAM id + REC dot, timestamp, archive time,
  segment time). The infrared scanline fill is `.ir`.
- **Sticker**: paper fill, 3px ink border, orange hard shadow. Used once, for
  `duck.status()` over the scene.
- No gradients, no rounded pills, no emoji, no percentages for similarity.

## Layout

1440px reference width, fluid. Two columns `minmax(0,2fr) minmax(0,1fr)` with
24px gap; single column under 980px. Header, main, and stage strip are separated
by 3px paper rules. Everything the presenter needs (scenario tabs, Start, Reset,
query, time, results, Copy, stage strip) is visible at 1440×900 without
scrolling; the evidence details and the encounter JSON can push below.

```
Header   logo · RANGER DUCK · encounter tabs (Feeding/Walking/Standing) · encounter-id · [Start] [Reset]
Main     ┌ scene (3D canvas + HUD + duck.status sticker) ┐ ┌ ARCHIVE SEARCH · Live|Replay ┐
         │ encounter caption · encounter JSON             │ │ query box (status, query, route, time) │
         └────────────────────────────────────────────────┘ │ 3 reference cards                      │
                                                            │ selected reference: video, controls    │
                                                            │ reviewed behavior → primitive · [Copy] │
                                                            └ evidence details (toggle)              ┘
Footer   01 Encounter → 02 Searching → 03 Reference ready → 04 Imitating → 05 Complete · Rehearse: No match · Timeout
```

## State machine

```
idle ──Start──▶ encounter ──animal reaches zone──▶ searching ──▶ ready ──Copy──▶ imitating ──▶ complete
                                                      │  ├──▶ nomatch ──Search broader──▶ searching
                                                      │  └──▶ failed  ──Retry live / Use replay──▶ searching
Reset from anywhere ──▶ idle (encounter id + 1, timers cleared)
Selecting a different card while complete ──▶ ready (previous action invalidated)
```

| Stage | Scene | Evidence panel | Stage strip | Copy |
| --- | --- | --- | --- | --- |
| idle | deer off-screen right, duck still | query "—", empty hint | nothing lit | n/a |
| encounter | deer slides into the teal zone (1.8s) | status "waiting for encounter zone" | 01 current | n/a |
| searching | duck head scans, teal scanline, REC dot pulses | elapsed counts live, "Ranking archive segments…" | 02 current | n/a |
| ready | deer grazes / ambles / stands alert by scenario | 3 cards; selecting one shows player + mapping | 03 current | enabled only if reviewed |
| imitating | duck runs the primitive animation | button reads "Imitating · primitive", teal progress bar | 04 current | disabled |
| complete | duck returns to normal | "Imitation complete", status sticker "complete" | 05 current | disabled until another card is selected |
| nomatch | duck holds pose | pink alert, "Search broader category" | 02 pink | n/a |
| failed | duck holds pose | pink alert, "Retry live" / "Use replay" | 02 pink | n/a |

Rules the UI must enforce, straight from the plan:

- The scene's `behavior_hint` never triggers a move. Only `Copy` does, and only
  when the selected reference is reviewed **and** was returned by the current
  search.
- Measured request duration is shown, never a fixed speed claim. Similarity is
  shown as `sim 0.45`, never as a percentage.
- Replay is a visibly separate mode (yellow segment control + "replaying
  cached run" status). A failed live request never silently becomes a cached
  success; the user picks "Use replay" explicitly.
- Reset increments the encounter id; every async callback checks the id before
  touching state so stale responses are dropped.
- Playback shows segment-local time and source-relative archive time side by
  side (`SEG 00:04 / 00:15` and `ARCHIVE 00:16`). Never seek a cut segment to a
  parent-video offset.
- Evidence details always show the original model caption and its hash next to
  the reviewed label, so a corrected caption is visible as a correction.

## Data contracts the UI expects

These map onto the routes in the plan. Field names below are what the mockup
reads; the backend can rename them as long as the frontend adapter is updated.

**`GET /demo-api/encounters`** → `[{ id, label, animal, behavior_hint, description }]`
Drives the scenario tabs and the encounter caption.

**`POST /demo-api/search`** `{ encounter_id, scenario_id, mode: "live"|"replay", broaden?: bool }` →

```json
{
  "encounter_id": "encounter-003",
  "query": "deer feeding with its head lowered",
  "match_type": "species" | "broader_category",
  "duration_ms": 4310,
  "mode": "live",
  "candidates": [
    {
      "clip_id": "clp_4f0a21",
      "rank": 1,
      "similarity": 0.45,
      "caption": "A deer lowers its head to the grass…",
      "caption_hash": "sha256:…",
      "source": "20261017_102903_5e195e5b.mp4",
      "parent_video_id": "b6ed2e302d7112b0",
      "segment_start_s": 12, "segment_end_s": 27,
      "playback_url": "/demo-api/clips/clp_4f0a21/video",
      "provenance": "MammAlps S1/C1/E103",
      "review": null | {
        "animal": "Red deer",
        "behavior": "Feeding with head lowered",
        "primitive": "ground_pick",
        "bound": "One complete beak-dip cycle · about 2.8 s",
        "reason": "Head drops below the shoulder line…"
      },
      "review_note": "only when review is null: why Copy is unavailable"
    }
  ]
}
```

`review` present ⇒ card badge `Reviewed · <behavior>` (teal), Copy enabled.
`review` null ⇒ badge `Unreviewed` (dashed), Copy disabled with `review_note`.
Errors: a timeout/abort should surface as the `failed` state with the measured
elapsed time; an empty candidate list as `nomatch`.

**`GET /demo-api/clips/{clip_id}/video`** is loaded straight into a `<video>`
element in place of the mock SVG frame. Keep the HUD overlays on top of it.

## Simulator adapter (browser side)

The duck group in the mockup is a stand-in for the MuJoCo/Three.js body. The
real page should call the plan's wrapper and mirror its status in the sticker:

```ts
duck.perform({ primitive: "ground_pick", evidenceId: "clp_4f0a21" }); // on Copy
duck.stop(); duck.reset();                                              // on Reset
duck.status(); // "ready" | "busy" | "recovering" | "complete" | "failed"
```

Completion is reported when the controller is observed entering and leaving the
action, not on a timer. The teal action progress bar in the mockup is cosmetic
and should be driven by the controller's actual state if it is kept.

## What is mock in `ranger-duck-mockup.html`

- Scene is inline SVG with CSS classes (`deer in|out|amble`, `deerhead
  graze|alert`, `duck scan|dip|walk|hold`). Replace with the 3D canvas; the HUD
  and sticker overlays stay as absolutely positioned HTML.
- Search latency is random 2.3–3.9s live, 0.7s replay. The timeout rehearsal
  fires at 3s; the real deadline is 12s.
- Captions, source ids, and similarities are lifted from
  `experiments/wildlife/results/` so the cards look like real archive output, but
  the review annotations are illustrative. Build the real manifest from
  visually inspected clips as the plan requires.
- Video is a drawn frame with a 15s timer. Replace with `<video>` on the proxy
  URL; keep the archive-time readout as `segment_start_s + video.currentTime`.
- Deer enters from the right so it never crosses the duck's walk area.
