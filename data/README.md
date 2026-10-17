# Video sources and provenance

This directory stores source records, not playable media. Supply local videos to
the independent archive using [the ingestion guide](../docs/ARCHIVE.md).
The [source guide](../docs/data_sources.md) relates dataset records to the current
cat and deer features.

[external-videos.json](external-videos.json) retains source identities, checksums,
citations and timestamped observations from earlier imports. Its download and
indexing counts are not the current archive inventory. The stored
[Meow settings](meow-ingestion-v1.json) preserve prior analysis metadata; current
worker configuration is defined by the archive service and its CLI.

For new imports, retain the source URL, dataset revision, licence, citation and
checksum where available. Use a consistent dataset ID and tags: cat retrieval
uses `meow-10k` or `cat-behavior`, and deer retrieval uses `wildlife`. A dataset
label or caption is not proof that a clip depicts a particular animal or behavior.

The worker copies originals beneath MEDIA_ROOT, creates playable segments, and
records captions, source intervals and indexing state in Postgres. Downloaded
files and queued jobs do not establish that a segment is searchable. Check job
status and authenticated search before reporting successful ingestion.

Keep media, private manifests and credentials outside version control. Preserve
source attribution when using derived footage. Human-review manifests belong to
the current segment identity, interval and exact caption; old reviews must not
be carried onto different evidence.
