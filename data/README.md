# Video sources and provenance

This directory stores source records, not playable media. Supply local videos to
the independent archive using [the ingestion guide](../docs/guides/archive.md#ingest-and-run).

## Source catalog

[external-videos.json](external-videos.json) retains source identities, checksums,
citations and timestamped observations from earlier Meow-10k cat-video and
MammAlps wildlife imports. Download/indexing counts are historical, not the
current archive inventory. The [Meow settings](meow-ingestion-v1.json) preserve
prior analysis metadata; current worker configuration belongs to the archive CLI.

Obtain media separately and confirm its dataset revision, licence and attribution
before importing. Retain source URL, dataset ID, revision, citation and checksum
where available. Missing source fields remain unknown. A dataset label or caption
does not prove that a clip depicts a particular animal or behavior.

## Retrieval scope

Cat searches apply `meow-10k` and `cat-behavior` tags with OR semantics; deer
searches apply `wildlife`. The requested cat dataset ID `hf-smgjch-meow-10k`
is scope metadata, not a dataset filter or a substitute for returned provenance.
Preserve the dataset IDs actually returned by the archive.

The worker copies originals beneath `MEDIA_ROOT`, creates playable segments,
and records exact captions, source intervals and indexing state in Postgres.
Downloaded files and queued jobs do not establish search availability. Check
job status and authenticated search before reporting successful ingestion.

Keep media, private manifests and credentials outside version control. Preserve
source attribution when using derived footage. Human reviews bind the current
segment identity, interval and exact caption; old reviews cannot be carried onto
different evidence. See [evidence review](../docs/guides/evidence-review.md).
