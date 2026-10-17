# Microduck simulator source

Vendored from [pollen-robotics/microduck-simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator)
at revision `ad9d41a763f30dc770817c33d92dcfec0205db1e`.
Copyright belongs to the upstream contributors. Source is distributed under
Apache License 2.0; see [LICENSE](LICENSE). Models and policies are obtained
from the same pinned simulator distribution. Upstream attributes these to
[microduck](https://github.com/pollen-robotics/microduck) and
[microduck_rl](https://github.com/pollen-robotics/microduck_rl).

Ranger Duck retains upstream MuJoCo XML preparation, the 61-value observation,
14-joint policy output, 50 Hz inference, 200 Hz physics stepping, beak-dip
phase machine, standing/walking controllers, fall detection, and recovery.
Its React wrapper drives `gameApi.frame` and installs a single controller
source for evidence-selected actions and separately labelled navigation. One cat or deer is a scripted visual
actor in the same Three scene, with no MuJoCo collision body. Its root stays fixed at x=1.05, z=-0.05, outside the yellow robot area.
It may turn to face the duck and change its body pose, but never translates.
Its poses do not select duck movements.
The cat's `SCRIPTED HISS` cue is a visual label;
there is no recorded or learned hissing audio.

Local changes to the upstream source:

- Local `/simulator/` asset paths and no Hugging Face authentication forwarding.
- Camera remains on the shared clearing instead of chasing the robot.
- Manual keyboard/gamepad/waypoint movement and body grabbing are disabled.
- Multiplayer, alternate/custom policy loading, arcade props and audio are disabled.
- The ball stays parked out of sight. No additional model downloads occur at runtime.
- Explicit disposal stops inference and frees runtime resources on unmount.
- Actual MuJoCo head yaw/pitch are exposed for verified completion of bounded scans/nods.

The source deliberately preserves the established physics/controller logic.
Unused upstream action handlers remain private to the game; the public app
adapter allows `ground_pick`, `short_walk`, `stand_hold`, `head_scan`,
`head_nod`, and `sit_cycle`. Scans/nods use the existing policy's head targets
at ±0.3 radians and require observed joint travel and a neutral return.
A sit cycle uses the bundled sit/stand policy, requires an observed lowered
trunk and standing return, and has a 6000 ms motion window. Stop requests the
native two-second stand-up once; repeated cancellation preserves that hand-back.
Head nods require vertical head-motion evidence; sitting requires explicit
sitting evidence. Neither is inferred from the encounter hint. Reverse motion is unsupported: browser checks of
small reverse commands did not produce a usable retreat with this policy.

`prepareCycle()` waits for unlocked, upright, settled physics before the next
automatic sequence. It preserves the robot's position, physics time, animal
scene, and controller. Repeated walking uses the same velocity/turn commands
to follow a bounded path. Only an explicit Reset/new encounter resets the
robot; policy fall recovery retains its upstream emergency handling. Stop
cancels pending preparation, navigation or movement while balance physics continues.

`roam()` follows interior waypoints using upstream forward/turn commands.
`approach()` cancels roaming, drives toward the interaction point (MuJoCo
x=0.38, y=0), then resolves only after observed arrival, facing and balance.
It has a 25-second deadline; failure stops its command instead of teleporting.
`perform()` accepts only evidence-referenced primitives and rejects overlap with
navigation. The UI explicitly labels roaming, approaching and settling separately
from imitation. `onNavigation` reports these transitions. The command getter
checks conservative body margins inside the yellow box even if render frames
pause. Stop and tab visibility cancellation are owned by the parent React app.

Run `python3 apps/ranger-duck/scripts/simulator-assets.py` from the repository
root before starting/building the frontend. The 53 hash-checked public assets
total approximately 12.5 MB; downloaded files remain ignored. MuJoCo and ONNX
WebAssembly binaries come from the locked npm dependencies and Vite bundles.
