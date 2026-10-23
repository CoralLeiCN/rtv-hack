# Microduck simulator source

Vendored from [pollen-robotics/microduck-simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator)
at revision `ad9d41a763f30dc770817c33d92dcfec0205db1e`.
Copyright belongs to the upstream contributors. Source is distributed under
Apache License 2.0; see [LICENSE](LICENSE). Models and policies are obtained
from the same pinned simulator distribution. Upstream attributes these to
[microduck](https://github.com/pollen-robotics/microduck) and
[microduck_rl](https://github.com/pollen-robotics/microduck_rl).

Ranger Duck retains upstream MuJoCo XML preparation, the 61-value observation,
14-joint policy output, 50 Hz inference, 200 Hz physics stepping, beak-dip phase
machine, standing/walking controllers, fall detection and recovery.
The React wrapper installs one controller source for bounded evidence actions
and separately labeled navigation. The procedural cat/deer has no MuJoCo collision
body and its scripted pose cannot select a duck movement. Its hissing cue is
visual; no recorded or learned hissing audio is provided.

## Local changes


- Local `/simulator/` asset paths and no Hugging Face authentication forwarding.
- Camera remains on the shared clearing instead of chasing the robot.
- Manual keyboard/gamepad/waypoint movement and body grabbing are disabled.
- Multiplayer, alternate/custom policy loading, arcade props and audio are disabled.
- The ball stays parked out of sight. No additional model downloads occur at runtime.
- Explicit disposal stops inference and frees runtime resources on unmount.
- Actual MuJoCo head yaw/pitch are exposed for verified completion of bounded scans/nods.

## Integration references

Maintained motion, navigation, cancellation and animal-patrol details live in the
[simulator reference](../../../../../../docs/reference/simulator.md). The adapter
supports six bounded primitives internally; retrieved evidence selects four active
ones. The [runtime behavior](../../../../../../docs/reference/behavior.md) owns
queue progression and physics continuity. Preserve this attribution and license
when changing the vendored source.

Download the pinned assets from the repository root:

```bash
python3 apps/ranger-duck/scripts/simulator-assets.py
```

The 53 hash-checked public assets total approximately 12.5 MB and remain ignored
by Git. Use `--check` for an offline size/hash check. MuJoCo and ONNX WebAssembly
binaries come from locked npm dependencies and Vite bundles. See
[asset instructions](../../../public/simulator/README.md).
