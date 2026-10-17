# Intent: web frontend for video search

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
