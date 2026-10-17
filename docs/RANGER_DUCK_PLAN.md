# Ranger Duck demo implementation plan

Agreed scope as of 17 October 2026. The user owns frontend design and implementation; the backend is delegated separately. The shared integration contract is [RANGER_DUCK_API.md](RANGER_DUCK_API.md), with supporting implementation context in [RANGER_DUCK_CONTEXT.md](RANGER_DUCK_CONTEXT.md).

Build one browser page where a simulated duck encounters an animal, searches the existing wildlife video archive for a similar behavior, and imitates a selected reference using an existing movement policy. The encounter, search results, reference playback, and duck movement all remain on this page.

The first version uses a scripted animal encounter, live VSS retrieval, visually reviewed reference clips, and pretrained Microduck controllers. Its claim is retrieval-guided imitation of recognizable behavior. Animal recognition from camera images, new policy training, physical robot deployment, and animal response prediction are outside this scope.

## One page for the complete demonstration

Serve the app at a single URL. The workshop backend and VSS are services behind this page, not additional screens the presenter must open. Fork the simulator into the app so the page can control it directly; embedding the separately hosted simulator is not the integration strategy.

```text
+-----------------------------------------------------------------------+
| Ranger Duck                 Encounter: Feeding   [Start] [Reset]       |
+--------------------------------------+--------------------------------+
|                                      | Live archive search            |
|  ONE SHARED 3D SCENE                  | Query and measured search time |
|                                      |                                |
|  Scripted animal  <-->  Microduck     | Three ranked reference cards   |
|                                      |                                |
|  The duck encounters the animal      | Selected wildlife video        |
|  and performs the imitation here.    | Playback controls + timestamp  |
|                                      |                                |
|                                      | Reviewed behavior -> duck move |
|                                      | [Copy this behavior]           |
+--------------------------------------+--------------------------------+
| Encounter -> Searching -> Reference ready -> Imitating -> Complete     |
+-----------------------------------------------------------------------+
```

Use approximately two thirds of desktop width for the scene and one third for evidence. Stack these areas on narrow screens. Keep the key controls and current status visible at a normal laptop presentation size. Fullscreen is an optional convenience; the flow must work without it.

The page shows a short explanation that the animal encounter is scripted and the duck uses pretrained movements. Expanded evidence details retain the model caption, reviewed behavior, source, and timestamps. Do not present retrieval similarity as a confidence percentage.

## Runtime architecture

| Component | Runs on | Responsibility |
| --- | --- | --- |
| React and Three.js interface | Presentation laptop browser | Scene, animal animation, result selection, video playback, and demo state |
| MuJoCo and ONNX WebAssembly | Same browser | Microduck physics and existing pretrained movement policies |
| Small Python FastAPI backend | Workshop VM | VSS authentication, search, evidence eligibility, and video proxy |
| Existing VSS APIs | Existing workshop infrastructure | Archive search, indexed segment metadata, and video access |

The backend serves the built frontend and its API under one origin. Reach it through an SSH port forward for the presentation. The browser executes the simulator even when its assets are served from the VM. The dedicated NVIDIA machine is not required for this version.

Use a pinned simulator source revision and its matching assets. Fetch the real Git LFS meshes and policies before building. The official browser implementation uses MuJoCo and ONNX WebAssembly; its Docker build uses Node 22. Preserve its physics and movement controllers. [Simulator setup](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/README.md), [build configuration](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/Dockerfile).

Keep credentials and JWTs in the backend process, loaded from the configured VM environment or its absolute `/config/` directory. The browser receives same-origin playback URLs containing opaque clip IDs, not VSS tokens. Forward byte-range requests and relevant response headers through the video proxy so seeking works. Do not log credential-bearing upstream URLs.

## Inputs and outputs

| Stage | Input | Output | Decision rule |
| --- | --- | --- | --- |
| Encounter | Selected scenario and Start | Encounter ID, animal label, behavior hint, scene description | The simulation supplies these labels; they are not camera predictions |
| Search | Encounter description and verified wildlife scope | Ranked segment hits and measured request duration | Use existing live VSS search with its smallest supported synthesis setting |
| Normalize | Returned hits and segment metadata | Clip IDs, playback URLs, captions, parent identity, and timing | Group neighboring hits and retain traceable source identities |
| Select evidence | Returned hit plus reviewed reference manifest | Supported behavior and eligible movement, or no supported imitation | Only a reviewed reference returned in this search may enable imitation |
| Execute | Selected eligible reference and Copy command | One bounded simulator action and completion status | Use an existing controller primitive; execute one action at a time |

Example encounter event:

```json
{
  "encounter_id": "encounter-001",
  "scenario_id": "deer-feeding",
  "input_mode": "scripted_scene",
  "animal": "deer",
  "behavior_hint": "feeding",
  "description": "A deer lowers its head to feed in a clearing."
}
```

This event contains no duck action. It describes the encounter for retrieval. Choose the final animal and scenarios after checking the available footage; deer is the initial candidate.

## Simulated encounter

Add one simple low-poly animal to the Three.js scene. Its animation is separate from the duck's MuJoCo body. The animal is a visual actor without collision interaction or autonomous behavior.

Provide feeding, walking, and standing scenarios. Start resets the demo, brings the animal into a fixed encounter zone, and triggers the query once it reaches that zone. Microduck starts from a known pose and can orient toward the animal. Autonomous navigation is unnecessary for this encounter.

The same canvas remains visible during search, reference playback, and imitation. A small head scan can indicate that search is in progress, provided it is stable in the simulator.

## Fast search and playback

Use the existing `POST /api/v1/search` route. The deployed-compatible request is:

```json
{
  "query": "deer feeding with its head lowered",
  "tags": ["wildlife"],
  "top_k": 15,
  "llm_top_n": 1,
  "min_similarity": 0.3
}
```

Live verification on 17 October found that `llm_top_n: 0` returns HTTP 422: the deployed schema requires at least one. The deployed `/search` implementation always synthesizes a summary for nonempty chunk results, and `/tools/search` delegates to it. Use `llm_top_n: 1`, label the feature Live search, and include that synthesis time in the displayed duration. Discard the generated summary; it does not authorize imitation. This integrates the existing retrieval service without changing its deployment. Use the actual wildlife tag and authenticated scope. Resolve any additional metadata filters through the metadata API. [Search skill](../.agents/skills/retrieval-search/SKILL.md), [metadata skill](../.agents/skills/retrieval-list-metadata/SKILL.md).

Use `results[]` for exact segment evidence and `chunk_results[]` for grouping by parent video. Prefer three distinct reference videos instead of neighboring segments from one source. Retain `source`, `original_video`, `reasoning_content`, similarity, and available segment start/end fields. Fetch segment metadata if the search response omits required fields.

Play the selected segment through the backend proxy. Segment-local playback starts at zero; the displayed archive timestamp adds the segment's source-relative start. Do not seek to a parent-video offset inside an already-cut segment. [Playback skill](../.agents/skills/retrieval-videos/SKILL.md).

Start with a 12-second search deadline and an explicit retry state. Measure latency on three representative queries and adjust the deadline if required. Display actual request duration rather than a fixed speed claim. Saved wildlife-query runs took 2.72–7.91 seconds, but their request bodies were not recorded, so they do not establish synthesis-free performance. [Recorded context](RANGER_DUCK_CONTEXT.md).

Use cached real results only through an explicit Replay mode, visibly separate from Live search. A failed request must not silently become a cached success. A broader animal-category fallback may be offered if no species match is found, with the changed query and match type shown.

## Reviewed evidence determines imitation

During preparation, visually inspect 6–10 available reference segments and record their supported behaviors. Existing local evaluation reports species and behavior errors, so captions alone must not authorize movement. [Caption evaluation summary](RANGER_DUCK_CONTEXT.md).

Each manifest entry records:

- An opaque evidence ID, dataset provenance when available, parent video identity, segment interval, and current segment source.
- The original caption and its hash, plus a reviewed animal label and observable behavior.
- The allowed motion primitive and a concise reason for the match.

Match the manifest against the actual returned segment. A replaced source, changed caption, or unresolved identity requires renewed review. Preserve the original caption even when the review corrects it; show that distinction in evidence details.

The manifest annotates references; it does not replace live search. Unreviewed results remain playable, but Copy is unavailable for them. If no eligible reference appears, Microduck holds its pose and the page reports No supported imitation found. The scene's behavior hint must never directly trigger the imitation.

If an encounter later uses an actual video instead of the scripted avatar, exclude every indexed variant of that original source from the reference results to avoid self-retrieval.

## Movement mapping and simulator adapter

| Reviewed behavior | Primitive | Bound |
| --- | --- | --- |
| Feeding with head lowered | `ground_pick` | One complete existing beak-dip cycle |
| Walking | `short_walk` | Slow movement for at most two seconds, inside a marked area |
| Standing still | `stand_hold` | Three seconds in a neutral standing pose |
| Resting | `sit` | Optional, after footage and pose transitions are verified |
| Looking around | `head_scan` | Optional, small bounded head movements |

The first three form the required demo. Standing still and resting are distinct labels; stationary footage does not automatically justify a sit. These movements approximate recognizable behavior rather than reproducing the animal's joint trajectories.

The upstream controller accepts a custom input source through `controller.addSource`. Discrete actions can reach its existing guarded handlers, while velocity commands drive the walking policy. Head targets and motion state are exposed in the game code. Add a narrow adapter in the fork, using these interfaces rather than synthetic keypresses. [Controller contract](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/app/src/game/controls/controller.js), [game control code](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/app/src/game/game.js).

Proposed app interface:

```ts
duck.perform({ primitive: "ground_pick", evidenceId: "reference-03" });
duck.stop();
duck.reset();
duck.status(); // ready, busy, recovering, complete, failed
```

These methods are wrappers to implement. Keep existing balance, recovery, and action guards intact. Observe entry into the requested action and its return to the normal mode before reporting completion. Ground pick currently lasts about 2.8 seconds; verify this against the pinned runtime. A timer alone is not proof that the move succeeded.

Clear motion commands when the action ends. Stop movement at the stage boundary. Reset cancels outstanding requests, playback, and action timers, and increments the encounter ID so stale responses cannot affect the next run. A pause clears translation while keeping balance active; it must not freeze the physical body midair. Disable unrelated multiplayer ghosts and avoid competing manual inputs during an imitation.

## Application routes and files

These are new app routes, separate from existing VSS endpoints:

| Route | Input | Output |
| --- | --- | --- |
| `GET /demo-api/encounters` | None | Available scenario IDs, labels, and descriptions |
| `POST /demo-api/search` | Encounter ID and scenario ID | Same encounter ID, query, duration, normalized candidates, and eligible reference actions |
| `GET /demo-api/clips/{clip_id}/video` | Opaque clip ID and optional Range header | Proxied video bytes for a known authorized result |

The server constructs the query from its scenario manifest. Clip IDs resolve only to results or prepared references authorized for this local demo session; the proxy must not accept arbitrary upstream URLs. Simulation commands remain in the browser.

Create the app under `apps/ranger-duck/`, with frontend, backend, scenario/reference manifests, startup instructions, and upstream attribution. Keep credentials, downloaded private media, and runtime caches outside tracked source. Preserve existing wildlife experiments. The shared ingest pipeline requires no changes.

## Demo sequence

1. Open the single forwarded URL. Wait for simulator and backend readiness on the same page.
2. Choose Feeding and press Start. The animal enters the clearing and lowers its head.
3. Show the query and live search status while Microduck observes.
4. Select an eligible returned reference. Play its matching segment and point out the reviewed behavior and source timestamp.
5. Press Copy this behavior. The same simulated duck performs a beak dip while the evidence remains visible.
6. Reset and repeat with Walking to show a different retrieved reference producing a different motion.
7. Select an unsupported result or run the no-match case. Show the neutral outcome and disabled Copy control.

The complete flow requires no tab changes, terminal use, or separate simulator page during the presentation. The reference video remains under ordinary playback controls; Copy starts a single bounded imitation. Changing the reference invalidates the previous action selection.

## Four hour implementation budget

| Time | Deliverable |
| --- | --- |
| 0–45 minutes | Simulator boots; verify fast-search contract, authentication, and one playable wildlife segment |
| 45–105 minutes | Build the encounter and read-only backend in parallel; review reference clips |
| 105–165 minutes | Connect evidence selection and three duck actions on the single page |
| 165–210 minutes | Verify cancellation, reset, playback, boundaries, error states, and laptop layout |
| 210–240 minutes | Rehearse, record a backup, and document one-command startup |

If simulator setup is blocked after 45 minutes, present a concrete fallback for review before replacing the agreed physics simulation. If footage does not support a proposed behavior, narrow the scenarios to verified examples. Keep voice, camera recognition, additional gestures, realistic animal animation, and new training outside the initial build.

## Acceptance checks

- One URL supports encounter selection, live search, video playback, imitation, and reset.
- Each new encounter issues a live VSS search; request duration and failures are visible.
- Every executed movement references an eligible result from the current search.
- Selecting another supported reference changes the movement, and unreviewed evidence cannot trigger it.
- The required feeding, walking, and standing scenarios each complete end to end with reviewed footage.
- Microduck's movement uses the existing physics/controller loop and stays within the demonstration area.
- Reset and changed references invalidate old requests and actions. Recovery and action timeouts have visible outcomes.
- Playback, seeking, and displayed source timestamps agree.
- VSS credentials remain server-side; cached playback is explicitly labeled.
- Startup instructions and a backup recording reproduce the single-page demonstration.
