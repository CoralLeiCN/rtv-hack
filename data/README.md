# External video index

[`external-videos.json`](external-videos.json) records external videos introduced
into this project. Media files stay on the workshop VM. A matching index is kept
at `~/data/ceda/external-videos.json` on that VM; `~` means the SSH user's home.
While an ingest batch is processing, the VM copy is the live record and the
repository copy is a snapshot as of its `updated_at_utc` timestamp.

Source records include the original download URL, dataset catalogue and DOI,
licence and citation, destination, expected size, checksum, and separate download
and VSS ingestion states. Derived clips link to that source and record their
time ranges, file sizes, local checksums, validation and ingestion results.
Only selected files belong in this index; a source
folder containing more files does not mean they have all been downloaded.

When adding another video, preserve existing records and add a stable ID and
source details. Record a download as `in_progress` while transferring. Set it to
`verified` only after the completed file matches the expected size and the
publisher's checksum, when available. Record failures explicitly rather than
leaving a completed-looking entry. Keep the repository and VM copies in sync.

`not_ingested` means the file has not been submitted to VSS. After a confirmed
upload, save the returned object key and chosen visibility, then track indexing
separately. Mark it `indexed` only after the archive confirms searchable clips.
Record derived clips separately and link them to the source video's ID.
An original can remain `not_ingested` while its derived clips are `indexed`;
the source's `derivatives.status` tracks that separate result. Each ingest batch
records the confirmed settings, returned object keys through its clip records,
and verification progress. A local checksum does not establish a server-side
checksum match.

Dataset scripts are kept in [`cronjob/ceda-soc250721`](../cronjob/ceda-soc250721/README.md).
The CEDA batch has a background monitor on the VM at
`~/cronjob/ceda-soc250721/monitor.py`. It checks Explore every 60 seconds, matches
the exact upload object keys, verifies complete segment numbering and private
visibility, and atomically updates the VM index. It never uploads or re-ingests
files. It stops on completion, an unexpected visibility result, an hour of
failed checks, or 24 hours without indexing progress. The batch's `monitor`
record contains its process ID, status and log path. A VM shutdown stops this
process; it is not installed as a startup service.

Dataset descriptions describe the collection unless a record explicitly states
that the individual video has been reviewed. Public download access does not
choose VSS visibility; `visibility: null` means that choice has not been made.

Keep authentication details and token-bearing URLs out of the index. Preserve
the dataset citation when sharing or publishing material derived from it.
