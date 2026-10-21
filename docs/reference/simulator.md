# Ranger Duck motion and animal rendering

The controller adapter exposes six bounded primitives; retrieval selects four active actions. It does not train a new policy or recover joint trajectories from video. The backend selects a bounded approximation from an existing caption; the browser observes the controller's execution before reporting completion. Navigation and the scripted cat/deer remain separate from imitation.

## Controller action contract

| Primitive | Motion window | Evidence and visible result | Completion check |
| --- | --- | --- | --- |
| `short_walk` | 2000 ms | Walking, approach, following or supported play movement → bounded walking/turning inside the arena | Observed translation or rotation, then upright settled walking mode |
| `ground_pick` | 8000 ms | Feeding/foraging → one beak-dip cycle | Entered ground-pick mode, observed phase progress, then settled standing |
| `head_nod` | 2400 ms | Explicit nodding or vertical head movement → pitch nod | Actual pitch range greater than 0.18 rad and return near the starting pitch |
| `head_scan` | 2400 ms | Head turn or attention → attentive yaw scan | Actual yaw range greater than 0.18 rad and return near the starting yaw |
| `sit_cycle` | 6000 ms | Explicit sitting/seated posture → sit briefly, then stand | Seated mode and trunk lowering greater than 0.025 m, followed by standing height and settled walking mode |
| `stand_hold` | 3000 ms | Standing/alert pause or stationary hissing posture → steady hold | Actual physics time advances while upright, then settling |

Every action requires an evidence ID. A motion window bounds the requested motion; it is not proof of execution or a promised wall-clock completion time. Non-pick actions have an additional bounded settling watchdog. A sit request shorter than 5500 ms and a pick request shorter than 3000 ms are rejected. The hissing approximation makes no hiss, and a walk does not reproduce facial contact or a cat's exact play pose. See [adapter implementation](../../apps/ranger-duck/frontend/src/simulator/adapter.ts) and [observed completion checks](../../apps/ranger-duck/frontend/src/simulator/adapter.ts).

Codex with `gpt-6-luna` chooses among the four active primitives using the complete
caption, current intent and actual outcomes. No fixed within-caption preference
or phrase classifier selects the command. The agent must distinguish ordinary
forward walking away from reverse walking, which this controller cannot reliably
perform. It must attribute motion to the selected animal, respect negation and
uncertainty, and retain exact human review constraints. The backend verifies exact
quotes, evidence identity and bounded command compatibility. Archive order remains
unchanged: the UI takes the first three agent-approved compatible references.

## Complete pinned-controller inventory

The source and seven bundled leg policies are pinned to upstream revision `ad9d41a763f30dc770817c33d92dcfec0205db1e` of [Pollen Robotics' Microduck simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/tree/ad9d41a763f30dc770817c33d92dcfec0205db1e). The policy observation has 61 values, the command has 13 values, and the network drives 14 actuated joints at 50 Hz over 200 Hz physics. Model and policy files are verified by the existing asset manifest; this update adds no model download. See [policy and joint definitions](../../apps/ranger-duck/frontend/src/simulator/upstream/game/constants.js).

| Native capability | Available control and observed limits | Ranger Duck status |
| --- | --- | --- |
| Walking policy | Configured forward command `0.25`, reverse `-0.2`, yaw `±1`; lateral command is explicitly zero. These are command values, not measured travel speed. | Forward walking and curved turning enabled. Tests found `0.12` forward and `-0.2/-0.25/-0.3` reverse did not produce useful travel. Angular-only commands were ineffective; useful turns combine forward `0.25` with yaw commands. |
| Four head channels | Neck pitch, head pitch, head yaw and head roll. Native stick input permits up to 2.5 rad, with smoothing and per-channel signs. | Only bounded yaw scan and pitch nod are exposed, using ±0.3-rad command offsets. Neck pitch and head roll are available upstream but have no evidence primitive or validation here. |
| Sit/stand policy | 800 ms standing handover before sitting; returning to walking gives the sit/stand policy 2 s to stand up. | Enabled as one bounded `sit_cycle`; no indefinite sit state. |
| Ground-pick policy | Phase clock of 4 s, ending at phase 0.7: approximately 2.8 s for the native gesture. | Enabled as `ground_pick`. Body motion is physical; the simulated jaw opening is cosmetic. |
| Left and right kick policies | Blind 0.5 s one-shots, followed by a 0.4 s command lock. Neither sees a ball or animal in its observation. | Both executed in the audit, but remain disabled as evidence actions. They change heading and do not establish a reliable mapping from animal pawing/contact. |
| Roll policy | Returns after tipping and becoming upright, or a 3 s limit. A timeout while tipped calls reset. The native roll cannot be interrupted safely. | Executed once in the audit and displaced the duck about 0.53 m. Excluded from the bounded continuous demo because of travel, interruption and reset behavior. |
| Stand/get-up policy | Automatic fall recovery: 0.2 s fall debounce, 0.3 s settling, then get-up; requires 1 s upright, gives up after 6 s and can reset. | Maintenance only, never selected from a wildlife caption. Recovery is reported rather than counted as imitation success. |
| Roller drive policy | Lazy-loaded alternate physics/visual model; configured forward `0.6`, reverse `-0.5`, yaw `±0.3`. | Not bundled or enabled. Switching models resets physics and needs additional assets. |
| Roller crouch/glide policy | Roller-only, 5 s phase clock ending at 0.7: approximately 3.5 s. | Not available for the current legged duck; not a cat-crouch approximation. |
| Jaw/quack and voice effects | JavaScript-rendered jaw hinge, 480 ms quack flap and audio effects. The jaw is not a MuJoCo joint. | Cosmetic only; audio is stubbed in this fork. No learned hiss or other animal sound. |
| Custom policy/script slots | Upstream can replace policy slots or play a 13-value command timeline. | External/custom loading is disabled in this demo. No new training or arbitrary script is accepted from captions. |
| Reset, ball spawn, camera/skin controls | Simulator utilities rather than animal behaviors. | Not evidence actions; manual movement/arcade input sources remain disabled. |

Source details: [velocity and phase limits](../../apps/ranger-duck/frontend/src/simulator/upstream/game/constants.js), [head channels](../../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js), [sit/stand handover](../../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js), [kick and roll completion](../../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js), [fall recovery](../../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js), [lazy roller loading and model switch](../../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js), [cosmetic jaw](../../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js), and [controller action interface](../../apps/ranger-duck/frontend/src/simulator/upstream/game/controls/controller.js).

There is no verified jump, strafe, reliable retreat, grooming, bite, pounce, hiss or animal-contact skill. An upstream handler existing in source does not make it a supported Ranger Duck evidence action.

## Retrieval selection

The controller inventory above remains available internally. Both demo modes exclude
`head_scan` and `stand_hold` from reference selection. The active reference actions
are walking, beak dip, vertical head nod and sit/stand. Passive-only clips do not
fill top-three slots; mixed captions can supply a separate supported active
behavior. Neutral attention between clips remains navigation, not an evidence
action.

## Continuous navigation and cancellation

The duck faces and approaches a present animal immediately, including during query planning/search, then attends between clips and passes. Its arrival corridor is centered around MuJoCo `(0.12, 0)`, leaving space for the policy's forward-turning radius after a walking imitation. Returns first align through a consistent turning arc inside the arena when necessary, then aim toward the animal. Arrival requires observed position within the interior corridor, facing and balance; steering to one exact point could otherwise cause repeated orbiting. Approach has a 25-second deadline; failure stops commands instead of teleporting. Navigation is labeled separately from the reference action. Its command getter also checks conservative margins inside the yellow box when render frames pause. `prepareCycle()` waits for balance and never recenters or resets the duck.

Stop cancels queued encounters, navigation and evidence promises, clears commands and lets the native controller balance. A queued scene cannot restart movement after Stop. A seated duck completes its native stand-up instead of switching policies early. The adapter remembers that hand-back so repeated Stop/preparation calls cannot cancel the two-second timer and cause a fall. Only explicit Reset resets the app-controlled body; upstream emergency recovery remains intact. See [navigation](../../apps/ranger-duck/frontend/src/simulator/adapter.ts) and [safe stop/settling](../../apps/ranger-duck/frontend/src/simulator/adapter.ts).

## One animal and its visual motor

The scene contains one visible cat or deer, not a second scripted companion. It has no MuJoCo collision body. It may patrol outside the arena and must settle at the interaction anchor before duck approach.

During duck roaming, a walk-capable actor may patrol east of the yellow box: root X is 1.05–1.29 m, Three.js Z is -0.32–0.22 m, and speed is at most 0.18 m/s. Turn rate, acceleration and deceleration are bounded; gait advances with distance traveled. The original articulated procedural cat/deer geometry remains in use; no generated animal assets are required.

Before duck approach, the animal returns to the interaction anchor `(1.05, -0.05)` and faces the duck. The wrapper waits for observed anchor position, facing and 180 ms of stability, with an 8 s deadline, before starting duck navigation. Stop, reset and unmount cancel this wait; a generation check prevents a late callback from restarting duck motion. Other phases hold position while pose animation may continue. See [animal motor](../../apps/ranger-duck/frontend/src/simulator/animalMotor.ts), [interaction settling](../../apps/ranger-duck/frontend/src/simulator/clearing.ts) and [wrapper coordination](../../apps/ranger-duck/frontend/src/simulator/MicroduckScene.tsx).

## Verification

See [testing](../testing.md) for repeatable checks and the
[17 October validation record](../history/simulator-validation-2026-10-17.md) for
prior measurements. Exactly one selected-species actor is created; shared scene
resources are disposed on teardown. No generated animal assets are required.
