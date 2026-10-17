# Ranger Duck motion and animal rendering

The demo exposes six evidence actions on the existing Microduck physics controller. It does not train a new policy or recover joint trajectories from video. The backend selects a bounded approximation from an existing caption; the browser observes the controller's execution before reporting completion. Navigation and the scripted cat/deer remain separate from imitation.

## Evidence action contract

| Primitive | Motion window | Evidence and visible result | Completion check |
| --- | --- | --- | --- |
| `short_walk` | 2000 ms | Walking, approach, following or supported play movement → bounded walking/turning inside the arena | Observed translation or rotation, then upright settled walking mode |
| `ground_pick` | 8000 ms | Feeding/foraging → one beak-dip cycle | Entered ground-pick mode, observed phase progress, then settled standing |
| `head_nod` | 2400 ms | Explicit nodding or vertical head movement → pitch nod | Actual pitch range greater than 0.18 rad and return near the starting pitch |
| `head_scan` | 2400 ms | Head turn or attention → attentive yaw scan | Actual yaw range greater than 0.18 rad and return near the starting yaw |
| `sit_cycle` | 6000 ms | Explicit sitting/seated posture → sit briefly, then stand | Seated mode and trunk lowering greater than 0.025 m, followed by standing height and settled walking mode |
| `stand_hold` | 3000 ms | Standing/alert pause or stationary hissing posture → steady hold | Actual physics time advances while upright, then settling |

Every action requires an evidence ID. A motion window bounds the requested motion; it is not proof of execution or a promised wall-clock completion time. Non-pick actions have an additional bounded settling watchdog. A sit request shorter than 5500 ms and a pick request shorter than 3000 ms are rejected. The hissing approximation makes no hiss, and a walk does not reproduce facial contact or a cat's exact play pose. See [adapter implementation](../apps/ranger-duck/frontend/src/simulator/adapter.ts#L179) and [observed completion checks](../apps/ranger-duck/frontend/src/simulator/adapter.ts#L287).

Within each caption, supported positive behaviors are considered in this order:

`short_walk → ground_pick → head_nod → head_scan → sit_cycle → stand_hold`

This makes a walking cat's movement take precedence over a simultaneous standing/looking description, and feeding take precedence over the head lowering involved in feeding. All matches still require the selected species, supported actor attribution, non-negated behavior and complete provenance. A dog's walk cannot become a cat action. Backward walking remains unsupported. Exact current human reviews retain their explicit behavior; inference does not override them. This priority does **not** reorder archive results: the UI still takes the first three compatible references in original retrieval order. See [caption priority and matching](../apps/ranger-duck/backend/ranger_duck/interaction.py#L19).

## Complete pinned-controller inventory

The source and seven bundled leg policies are pinned to upstream revision `ad9d41a763f30dc770817c33d92dcfec0205db1e` of [Pollen Robotics' Microduck simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/tree/ad9d41a763f30dc770817c33d92dcfec0205db1e). The policy observation has 61 values, the command has 13 values, and the network drives 14 actuated joints at 50 Hz over 200 Hz physics. Model and policy files are verified by the existing asset manifest; this update adds no model download. See [policy and joint definitions](../apps/ranger-duck/frontend/src/simulator/upstream/game/constants.js#L4).

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

Source details: [velocity and phase limits](../apps/ranger-duck/frontend/src/simulator/upstream/game/constants.js#L45), [head channels](../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js#L543), [sit/stand handover](../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js#L1963), [kick and roll completion](../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js#L1106), [fall recovery](../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js#L590), [lazy roller loading and model switch](../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js#L1255), [cosmetic jaw](../apps/ranger-duck/frontend/src/simulator/upstream/game/game.js#L1623), and [controller action interface](../apps/ranger-duck/frontend/src/simulator/upstream/game/controls/controller.js#L79).

There is no verified jump, strafe, reliable retreat, grooming, bite, pounce, hiss or animal-contact skill. An upstream handler existing in source does not make it a supported Ranger Duck evidence action.

## Continuous navigation and cancellation

The duck follows interior waypoints while waiting and between passes, then approaches its interaction point at MuJoCo `(0.38, 0)`. Arrival requires observed position, facing and balance. Navigation is labeled separately from the reference action. Its command getter also checks conservative margins inside the yellow box when render frames pause. `prepareCycle()` waits for balance and never recenters or resets the duck.

Stop cancels navigation and evidence promises, clears commands and lets the native controller balance. A seated duck completes its native stand-up instead of switching policies early. The adapter remembers that hand-back so repeated Stop/preparation calls cannot cancel the two-second timer and cause a fall. Only explicit Reset/new encounter resets the app-controlled body; upstream emergency recovery remains intact. See [navigation](../apps/ranger-duck/frontend/src/simulator/adapter.ts#L92) and [safe stop/settling](../apps/ranger-duck/frontend/src/simulator/adapter.ts#L331).

## One animal and its visual motor

The scene contains one visible cat or deer, not a second scripted companion. It has no MuJoCo collision body. The latest user request allows a small outside patrol, replacing the earlier fixed-position requirement.

During duck roaming, a walk-capable actor may patrol east of the yellow box: root X is 1.05–1.29 m, Three.js Z is -0.32–0.22 m, and speed is at most 0.18 m/s. Turn rate, acceleration and deceleration are bounded; gait advances with distance traveled. The original articulated procedural cat/deer geometry remains in use; this update does not replace the animal models.

Before duck approach, the animal returns to the interaction anchor `(1.05, -0.05)` and faces the duck. The wrapper waits for observed anchor position, facing and 180 ms of stability, with an 8 s deadline, before starting duck navigation. Stop, reset and unmount cancel this wait; a generation check prevents a late callback from restarting duck motion. Other phases hold position while pose animation may continue. See [animal motor](../apps/ranger-duck/frontend/src/simulator/animalMotor.ts), [interaction settling](../apps/ranger-duck/frontend/src/simulator/clearing.ts) and [wrapper coordination](../apps/ranger-duck/frontend/src/simulator/MicroduckScene.tsx).

## Browser cost

The user canceled the animal-model replacement. The demo retains its original
procedural cat/deer and improves their motor coordination. This update adds no generated
animal model, animal model-loading pipeline or external animal asset requirement.

Only the selected species is created when needed, and exactly one animal is
visible. Repeated tree geometry/materials are shared, gait is distance-driven,
and scene resources are disposed on teardown. These are implementation choices,
not an FPS guarantee. In a post-cleanup local headless Chrome sample, the
original cat used 23 meshes/1,356 triangles and returned to its anchor in
2.09 s; the deer used 24 meshes/1,320 triangles and returned in 2.01 s. The
full scene, including the upstream duck, ran at about 60 FPS with 133–137 draw
calls and approximately 200,500 rendered triangles. Both motor checks had no
page errors. These are isolated measurements, not a browser/device guarantee.

## Verification record, 17 October 2026

- The final six-action adapter sequence included roaming, approach before every primitive, `head_nod`, `sit_cycle`, `ground_pick`, `short_walk`, `head_scan`, `stand_hold`, and repeated-Stop cancellation during sitting and nodding.
- Physics time advanced continuously from 1.56 to 45.56 s. No reset or recovery occurred. Observed X stayed between -0.670 and 0.465 m; Y stayed between -0.278 and 0.047 m.
- The complete sit gesture took about 5.32 s without approach. Its trunk moved from roughly 0.116 m down to 0.059 m and returned. A nod took about 2.77 s including settling and covered approximately 0.52–0.53 rad of actual head pitch.
- Cancellation testing initially exposed a repeated-walk hand-back problem that triggered recovery; the adapter fix was retested successfully with Stop, Stop and immediate preparation. The failed intermediate run is not counted as a success.
- The isolated native-policy audit exercised both kicks and one roll without recovery/reset, but did not establish them as bounded evidence actions. They remain disabled.
- 21 adapter tests pass. The combined frontend suite, including animal motor changes, reports 45 tests and a successful production build; the backend suite reports 163 tests. Real-time measurements above came from the local Chrome/MuJoCo test session, not a physical robot or a latency benchmark.
- Earlier navigation checks covered fresh reset followed by 11.5 s and 30 s of search-time roaming, approach and actions without recovery/reset. The tightened interior route leaves room for the pretrained controller's turning radius.

Development-only adapter hooks were used for physics measurements. These checks validate execution and cancellation, not the correctness of wildlife captions or a human review of footage. Normal UI, animal-renderer and live archive verification remain separate checks.
