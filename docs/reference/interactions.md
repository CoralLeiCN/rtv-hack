# Ranger Duck interaction reference

The scenario catalog covers same-species reference interactions: domestic cat–cat and deer–deer. The simulated duck copies a bounded approximation of a behavior described in each retrieved clip. One scripted animal patrols outside the arena and returns to face the duck for interactions; retrieved footage, its video-model caption, and the duck controller remain separate sources of information.

## Cat encounters

| Encounter | Search focus | Visible signals to look for | Duck approximation when the returned caption supports it |
| --- | --- | --- | --- |
| Hissing boundary | A cat hisses toward another approaching cat | Directed hiss, ears held back, tense posture; distinguish the hissing cat from the responding cat | Hiss-only and retreat-only clips are ineligible; a separately supported active motion may qualify |
| Friendly greeting | Two cats approach and greet one another | Tail-up approach, nose touching, sniffing or rubbing directed toward the other cat | A short approach when supported; head-turn-only clips are ineligible |
| Social play | Two cats engage with each other | Reciprocal movement, taking turns, pauses, and attention to the other cat | A short walk when supported; no jumping, biting, or pouncing controller |

Hissing is a vocal signal in an antagonistic context; holding still does not reproduce its sound. The scene can show a scripted hissing pose, but it cannot authorize a retrieved duck action without separate supported active evidence. An archive result must not be labeled as hissing merely because the user chose Hissing.

The behavior choices are grounded in [Merck Veterinary Manual's account of cat social behavior](https://www.merckvetmanual.com/behavior/behavior-of-cats/social-behavior-of-cats), [Cornell Feline Health Center's account of aggression and body signals](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-behavior-problems-aggression), and Cats Protection's descriptions of [social groups and greetings](https://www.cats.org.uk/cats-blog/where-is-the-love-cat-behaviour) and [play versus fighting](https://www.cats.org.uk/help-and-advice/cat-behaviour/cats-and-fighting). These sources support plausible scenarios, not claims about any particular archive clip.

## Deer encounters

| Encounter | Search focus | Duck approximation when the returned caption supports it |
| --- | --- | --- |
| Forage together | Two deer feed beside one another | One ground-pick cycle |
| Follow companion | One deer follows another along the same path | A short walk |
| Herd alert | A deer responds to another deer becoming alert | Alert-only clips are ineligible; a separately supported active motion may qualify |

These scenarios reflect social and alert contexts described by the [Missouri Department of Conservation](https://mdc.mo.gov/magazines/conservationist/2014-11/deer-dialogue) and the National Park Service's accounts of [white-tailed deer](https://www.nps.gov/jeca/learn/nature/white-tailed-deer-odocoileus-virginianus.htm) and [doe–fawn following and foraging](https://www.nps.gov/articles/000/the-mating-and-reproduction-of-white-tailed-deer-at-devils-tower.htm). The archive category remains “deer”; these references do not identify the species of an unverified clip.

## Evidence and automatic execution

Codex with `gpt-6-luna` interprets each segment's existing video-model caption to choose an action; the query and scripted encounter cannot supply missing evidence. It requires the selected species, an explicitly described supported behavior and complete source/timing metadata. Single-animal behavior is usable. The search query asks for an interaction, but a supported solitary or shared activity can still drive an honestly labeled action. Wrong species, negated or uncertain behavior, and unsupported movements remain ineligible.

Caption-derived actions are labeled `video_caption`, with the inferred behavior and its movement approximation shown. They are not visual reviews and do not turn `review_status` into `reviewed`. An exact current review of a solitary feeding deer can authorize a ground-pick action; it does not claim a deer–deer interaction occurred.

The unified backend selects the first three compatible active actions in retrieval order; the frontend also rejects passive actions from stale responses. It shows each action's position and original source rank. Unsupported results do not occupy a card or queue slot. If only one or two qualify, loop those available actions without inventing a third.

Within each caption, the agent chooses the supported motion and actor from context,
including negation and uncertainty. There is no fixed motion priority or phrase
veto. Retrieval allows walking, beak dipping, vertical head nodding and sitting then
standing; the [motion inventory](simulator.md) defines the available commands and
limits. The application enforces provenance, exact quotations and valid commands.
Semantic correctness belongs to the agent and requires model-backed validation.

The animal patrols outside the yellow box while the duck roams, then returns to its interaction mark and settles before duck approach. The duck executes the evidence action after arriving. Navigation is not presented as behavior copied from a clip. Stop or Reset cancels all movement, and ordinary video/cycle changes preserve the duck body and physics clock.

Earlier query observations are preserved in the
[17 October record](../history/interaction-observations-2026-10-17.md); they do not
establish current archive availability.
