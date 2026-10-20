# Project intent

MicroDuck turns animal-video evidence into inspectable, bounded behavior in a
browser simulation. Users can search for a moment, watch its source clip, and
see how its caption supports a simulated duck action.

## Search and evidence

The search interface accepts natural-language queries and returns matching video
segments with captions and source-relative timestamps. Each segment plays inline.
An independent archive stores media on the local filesystem, metadata and jobs
in Neon Postgres, and caption embeddings in Qdrant. EmbeddingGemma 2 embeds queries and captions;
self-hosted Cosmos 3 Reasoner produces captions during ingestion.

The applications keep archive credentials on the server. The configured library
is shared by its users; Ranger Duck grants session-scoped playback capabilities.
Source identity, intervals and exact captions remain attached to every action.

## Encounter and Loop behavior

One page contains a persistent simulated MicroDuck and one scripted cat or deer.
The user selects an animal, encounter preset and optional intent. An agent plans
a query, retrieves up to 15 clips, and proposes actions grounded in their captions.
The first three compatible active references retain archive order.

With Loop off, the current queue repeats without new searches. With Loop on,
completed outcomes guide the next query for a different interaction of the same
species. Toggle changes take effect at queue boundaries. Start, Pause, Resume
and Reset remain under user control; replay is explicitly labeled and uses saved
decisions while streaming the original clips.

Supported reference-derived actions are walking, beak dipping, head nodding and
sitting then standing. A solitary animal can supply supported motion evidence.
Two-role plans need evidence for both animals; the requested encounter cannot
supply missing behavior. Caption inference stays visibly distinct from human
review. Actual playback, companion animation and duck physics must finish before
the queue advances.

## Boundaries and implementation

These movements are caption-grounded approximations, not motion capture. The
project does not control physical robots or interact with live animals. Navigation
and search animations remain distinct from evidence-derived imitation.

See the [archive specification](spec.md), [runtime behavior](reference/behavior.md),
[API contract](reference/ranger-duck-api.md), and [implementation status](status.md).
