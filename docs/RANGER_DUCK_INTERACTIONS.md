# Ranger Duck interaction reference

The user selected same-species reference interactions: domestic cat–cat and deer–deer. The simulated duck copies a bounded approximation of a behavior described in each retrieved clip. One scripted animal patrols outside the arena and returns to face the duck for interactions; retrieved footage, its video-model caption, and the duck controller remain separate sources of information.

## Cat encounters

| Encounter | Search focus | Visible signals to look for | Duck approximation when the returned caption supports it |
| --- | --- | --- | --- |
| Hissing boundary | A cat hisses toward another approaching cat | Directed hiss, ears held back, tense posture; distinguish the hissing cat from the responding cat | A pause for a described stationary boundary display; retreat-only evidence is unsupported |
| Friendly greeting | Two cats approach and greet one another | Tail-up approach, nose touching, sniffing or rubbing directed toward the other cat | A short approach, or a head turn toward the partner |
| Social play | Two cats engage with each other | Reciprocal movement, taking turns, pauses, and attention to the other cat | A short walk or attentive head turn; no jumping, biting, or pouncing controller |

Hissing is a vocal signal in an antagonistic context; holding still does not reproduce its sound. The scene can show a scripted hissing pose, but the duck's pause is a movement approximation. An archive result must not be labeled as hissing merely because the user chose Hissing.

The behavior choices are grounded in [Merck Veterinary Manual's account of cat social behavior](https://www.merckvetmanual.com/behavior/behavior-of-cats/social-behavior-of-cats), [Cornell Feline Health Center's account of aggression and body signals](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-behavior-problems-aggression), and Cats Protection's descriptions of [social groups and greetings](https://www.cats.org.uk/cats-blog/where-is-the-love-cat-behaviour) and [play versus fighting](https://www.cats.org.uk/help-and-advice/cat-behaviour/cats-and-fighting). These sources support plausible scenarios, not claims about any particular archive clip.

## Deer encounters

| Encounter | Search focus | Duck approximation when the returned caption supports it |
| --- | --- | --- |
| Forage together | Two deer feed beside one another | One ground-pick cycle |
| Follow companion | One deer follows another along the same path | A short walk |
| Herd alert | A deer responds to another deer becoming alert | A stationary pause or directed head turn |

These scenarios reflect social and alert contexts described by the [Missouri Department of Conservation](https://mdc.mo.gov/magazines/conservationist/2014-11/deer-dialogue) and the National Park Service's accounts of [white-tailed deer](https://www.nps.gov/jeca/learn/nature/white-tailed-deer-odocoileus-virginianus.htm) and [doe–fawn following and foraging](https://www.nps.gov/articles/000/the-mating-and-reproduction-of-white-tailed-deer-at-devils-tower.htm). The archive category remains “deer”; these references do not identify the species of an unverified clip.

## Evidence and automatic execution

The backend derives each action from that segment's existing video-model caption, not the query or scripted encounter. It requires the selected species, an explicitly described supported behavior and complete source/timing metadata. Single-animal behavior is usable. The search query asks for an interaction, but a supported solitary or shared activity can still drive an honestly labeled action. Wrong species, negated or uncertain behavior, and unsupported movements remain ineligible.

Caption-derived actions are labeled `video_caption`, with the inferred behavior and its movement approximation shown. They are not visual reviews and do not turn `review_status` into `reviewed`. An exact current review of a solitary feeding deer can authorize a ground-pick action; it does not claim a deer–deer interaction occurred.

The frontend filters all retrieved candidates for compatible actions and takes the first three in retrieval order. It shows each action's position and original source rank. Unsupported results do not occupy a card or queue slot. If only one or two qualify, loop those available actions without inventing a third.

Within each caption, supported active behavior takes precedence over stillness, while matching the selected animal and retaining negation checks. Walking, beak dipping, head nodding, head scanning, sitting then standing, and a standing hold are available. The [motion inventory](RANGER_DUCK_ANIMATION.md) lists the precise priority, tested limits and other native capabilities that remain disabled.

The animal patrols outside the yellow box while the duck roams, then returns to its interaction mark and settles before duck approach. The duck executes the evidence action after arriving. Navigation is not presented as behavior copied from a clip. Stop or Reset cancels all movement, and ordinary video/cycle changes preserve the duck body and physics clock.

## Archive observations, 17 October

Live cat interaction queries returned real clips with two cats observing one another, turning toward one another, and playing around a toy. The initial top-three Hissing results did not explicitly describe a hiss. An explicit head turn or an attentive head-turn approximation can still be derived from those captions, with its actual label shown. The latter represents the watching animal and is not a claim that the footage contains that exact duck motion.

The initial deer co-foraging query returned solitary-deer captions in its top three. Under the current policy, those can supply solitary feeding actions without establishing a deer–deer interaction. A query is not evidence that the requested event occurred.
