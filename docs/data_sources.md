# Animal video sources

Ranger Duck currently supports cat and deer encounters. Local videos can come
from any suitable source with recorded provenance; dataset membership alone does
not establish species or behavior in an individual clip.

The [source catalog](../data/external-videos.json) includes Meow-10k cat-video
records and MammAlps wildlife records. These are source references and timestamped
observations, not a statement that those videos are present in the independent
archive. Obtain the media separately and confirm its revision, licence and
attribution before importing it. Missing source fields remain unknown.

Use a dataset ID when ingesting and preserve it in returned segment provenance.
Cat searches apply `meow-10k` and `cat-behavior` tags with OR semantics; deer
searches apply `wildlife`. The requested cat dataset ID `hf-smgjch-meow-10k` is
scope metadata, not a dataset filter or a substitute for returned provenance.

See the [data guide](../data/README.md) for record conventions and the
[archive setup](ARCHIVE.md#ingest-and-run) for ingestion commands. Current job
state and search results establish availability; prior download or upload
snapshots do not.
