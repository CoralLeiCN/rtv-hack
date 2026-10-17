# Intent: web frontend for video search

## Ranger Duck interaction loop

Extend the search experience with a Loop mode that lets the simulated duck keep
interacting with new archive videos for as long as the user leaves it enabled.
The user supplies the initial prompt. An agent searches for two cats or two deer
interacting and returns the top 10 clips without rejecting single-animal or weak
matches. The simulated scene contains **one animal companion and the duck**.
The companion represents one video animal; the duck represents the other.
Codex identifies those two roles from the clip's caption, animates the companion
as the first animal, and translates the counterpart's observed behavior into
supported duck movements. Preserve the relationship and order between those
behaviors rather than choosing an unrelated reaction.

For example, if one deer approaches while another watches, the single deer model
approaches and the duck stands or turns its head to approximate the watching
animal. If the caption does not establish two supported roles, keep the clip
playable with a clearly labeled neutral pause instead of inventing a counterpart.
These are caption-inferred approximations, not motion capture or visual review.

Loop mode is additional to the existing encounter mode. Both scenes use one
animal model plus the duck; encounter mode retains its direct search and
fixed-sequence imitation controls.

The duck's actual reaction becomes input to the agent's next search. The agent
selects a new video, the duck reacts again, and the cycle repeats. Each search
should follow from the interaction that just happened while retaining the
user's original intent. The experience should feel like an evolving sequence
of interactions, rather than repeated playback of a fixed result list.

The user controls whether the loop continues and can see how each clip, duck
reaction, and subsequent search connect. The detailed
flow and acceptance criteria are in the
[Ranger Duck loop specification](spec.md#ranger-duck-loop-mode-additional-mode).

## Original search experience

Build a web frontend that lets users search the existing VSS video archive from
their browser. The goal is to make the archive's search capabilities accessible
through a simple web interface.

The core experience is to enter a natural-language query, submit it, and review
the matching video segments. Results should let users play each available
segment inline and show its description and timestamps so they can understand
which moments match their query.

Users can search immediately, without signing in. A small Python FastAPI server
will connect to the existing VSS APIs using the configured workshop account.
It will keep credentials and session tokens on the server and refresh the VSS
session when needed. Everyone using this frontend searches the data available
to that configured account.

Search requests will use the existing `POST /api/v1/search` API and its defaults.
The existing VSS services remain responsible for search and indexing. Keep the
initial interface limited to the query, results with segment playback, and
necessary status messages.

The [specification](spec.md) defines the initial implementation scope and
acceptance criteria.

See the [retrieval API guide](../.agents/references/retrieval.md),
[search skill](../.agents/skills/retrieval-search/SKILL.md), and
[video skill](../.agents/skills/retrieval-videos/SKILL.md) for integration details.
