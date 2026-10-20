# Ranger Duck visual design

This guide owns visual tokens and layout. Current interaction rules belong to
[runtime behavior](../../../docs/reference/behavior.md) and payloads to
[the API reference](../../../docs/reference/ranger-duck-api.md).

| Asset | Purpose |
| --- | --- |
| [ranger-duck-mockup.html](ranger-duck-mockup.html) | Standalone historical mockup; reference for styling, not current execution rules |
| [ranger-duck.dc.html](ranger-duck.dc.html) | Original canvas export; needs its canvas runtime |
| [Original handoff](../../../docs/history/design-handoff.md) | Preserved manual Copy flow, sample contracts and mock state machine |

The production page uses Start/Pause/Resume/Reset, one Loop toggle and automatic
playback/action coordination. Do not reintroduce the mockup's Copy button or
reviewed-only gating. Its captions, source IDs, timing and annotations are
illustrative, not real evidence or live performance claims.

## Current layout

Keep a persistent duck and one cat/deer outside its arena. The simulation and
movement status sit on the left; the query, up to three active reference cards,
current playback and behavior mapping sit on the right. Show the current round's
interaction, inferred versus reviewed basis, original source ranks and separate
query/retrieval/action timings. Recent rounds expose actual outcomes and explicit
saved-round replay. Toggle changes take effect at queue boundaries.

Use the export's 1440px reference width, fluid two-column layout
`minmax(0,2fr) minmax(0,1fr)`, 24px gap and one column below 980px. Keep the scene,
controls and evidence legible together. Detailed behavior is maintained in the
linked runtime reference rather than the historical mock state machine.

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
  text. Keep disabled controls distinct from enabled actions.
- **Trail-cam HUD**: mono 11px uppercase text pinned to the corners of the
  scene and of the video frame (CAM id + REC dot, timestamp, archive time,
  segment time). The infrared scanline fill is `.ir`.
- **Sticker**: paper fill, 3px ink border, orange hard shadow. Used once, for
  `duck.status()` over the scene.
- No gradients, no rounded pills, no emoji, no percentages for similarity.
