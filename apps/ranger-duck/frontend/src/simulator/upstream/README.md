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
source for reviewed actions. The deer is a visual actor in the same Three
scene, with no MuJoCo collision body.

Local changes to the upstream source:

- Local `/simulator/` asset paths and no Hugging Face authentication forwarding.
- Camera remains on the shared clearing instead of chasing the robot.
- Manual keyboard/gamepad/waypoint movement and body grabbing are disabled.
- Multiplayer, alternate/custom policy loading, arcade props and audio are disabled.
- The ball stays parked out of sight. No additional model downloads occur at runtime.
- Explicit disposal stops inference and frees runtime resources on unmount.

The source deliberately preserves the established physics/controller logic.
Unused upstream action handlers remain private to the game; the public app
adapter allows only `ground_pick`, `short_walk`, and `stand_hold`.

Run `python3 apps/ranger-duck/scripts/simulator-assets.py` from the repository
root before starting/building the frontend. The 53 hash-checked public assets
total approximately 12.5 MB; downloaded files remain ignored. MuJoCo and ONNX
WebAssembly binaries come from the locked npm dependencies and Vite bundles.
