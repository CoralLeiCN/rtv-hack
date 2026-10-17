# External video index

[`external-videos.json`](external-videos.json) records external videos introduced
into this project. Media files stay on the workshop VM. A matching index is kept
at `~/data/ceda/external-videos.json` on that VM; `~` means the SSH user's home.
While an ingest batch is processing, the VM copy is the live record and the
repository copy is a snapshot as of its `updated_at_utc` timestamp.

## Wildlife datasets

The repository index also includes wildlife records verified through the live,
database-backed VSS retrieval API on **17 October 2026**. These additions have
their own `verification` timestamps; the top-level `updated_at_utc` still dates
the original VM snapshot.

| Dataset | Location | Fully indexed uploads | Indexed segments | Approx. footage |
| --- | --- | ---: | ---: | ---: |
| MammAlps | Swiss National Park | 156 | 565 | 41.5 min |
| KABR | Mpala Research Centre | 57 | 316 | 25.7 min |

All 213 observed uploads are private and have stored AI-generated descriptions.
MammAlps includes forest and alpine camera footage, including nighttime scenes;
sample descriptions mention deer, marmots, grazing and animal movement. KABR
includes savanna and aerial footage, with descriptions of giraffes and zebras
grazing and walking; 40 uploads are tagged RGB and 17 thermal. These are summaries
of stored descriptions, not independently verified species identifications.

Counts include pilot and quality-test uploads and do not establish the number
of distinct original recordings or completeness of either source dataset.
Original download URLs, revisions, licences and citations remain unverified and
are explicitly left unknown in these records. The additions are local to this
repository; preserve them when refreshing from the VM snapshot.

## Meow-10k dataset tooling

The Meow entry has its own timestamped download, ingestion, and provenance
summaries. These are historical snapshots, not a live completion claim. Its
17 October 2026 snapshot records 16,870 verified files, including 6,735 MP4s;
the ingestion snapshot records 29 indexed videos and 200 awaiting indexing.
Preserve all CEDA, MammAlps, and KABR records when incorporating Meow updates.
The top-level index timestamp is retained from the existing snapshot; use the
Meow fields' timestamps for their observation times.

Meow tooling refreshes the existing VM indexes at `~/data/external-videos.json`
and `~/data/ceda/external-videos.json`, preserving each index's unrelated records.

The `videos` list contains individual video records. The `datasets` list records
collections containing multiple formats, including the source repository, pinned
revision, declared licence, destination, and separate download and ingestion
states. A dataset entry does not imply that every companion file is a video or
that downloading the dataset submits its contents to VSS.

For Meow-10k, the VM destination is `~/data/meow-10k` and its per-file manifest is
`~/data/meow-10k/manifest.json`. The manifest should retain each relative path,
source revision, expected size and publisher checksum where available, actual
checksum and size, and download status. Track video upload object keys and
indexing status separately from the audio, time-series arrays, annotations, and
documentation retained alongside the videos. Dataset-level totals must reflect
the manifest; do not mark the dataset verified until all requested files pass
verification.

Meow ingestion uses a separate `~/data/meow-10k/ingestion.json` journal, keyed by
the video's relative path. It is authoritative for upload object keys and
ingestion states; the downloader's manifest may still show `not_ingested` while
uploads are running. The approved settings are stored in
`~/data/meow-10k/meow-ingestion-v1.json`. The summary script
`scripts/data/summarize_meow.py` reads only metadata, aggregates download and
ingestion states, and atomically refreshes each existing VM index. Its manifest
SHA256 identifies the metadata snapshot used for that summary; downloading more
files changes the manifest and requires another summary. It never updates the
manifest or journal itself.

The approved private-upload prompt and metadata are recorded in
[`meow-ingestion-v1.json`](meow-ingestion-v1.json). Keep these settings unchanged
during the run: the journal binds every upload to their SHA256. A later prompt
change needs a new settings version and the
[`ingest-reingest-videos`](../.agents/skills/ingest-reingest-videos/SKILL.md)
workflow for videos that already have object keys.

### Dataset metadata for videos and clips

Every Meow upload uses the native VSS tag `meow-10k`, which can be passed in the
search API's `tags` filter. The current VSS API does not provide arbitrary
`dataset_*` fields or an in-place metadata update endpoint.

The VM-only `~/data/meow-10k/dataset-metadata.json` supplies linked provenance for
all 6,735 source videos: dataset ID and name, public source URL, pinned revision,
source path and checksum, upload object key when available, ingestion state,
and settings version. Indexed clips receive the same dataset metadata through
their exact parent upload object key. The verifier records observed clip links
in `~/data/meow-10k/clip-links.json`; subsequent verification and summary cycles
refresh the metadata index so newly indexed clips inherit the provenance.

These are application-side links, not new columns in the VSS search database.
An application can enrich search results by matching their clip `source` or
parent `original_video` to the index; native filtering continues to use the
`meow-10k` tag. Building the metadata index does not re-ingest media or change
the saved prompt, visibility, settings hash, or shared pipeline.

Run `scripts/data/build_meow_metadata.py` on the VM to refresh the index manually.
It validates the pinned revision, video count, source checksums, and parent
upload matches before atomically replacing its output. It prints only counts,
the output checksum, and refresh time. Keep the full metadata and clip-link
files on the VM because their storage references identify private infrastructure;
only their aggregate summary and portable path belong in the repository index.

Check these VM files for progress:

- `~/data/meow-10k/pipeline-status.json`: current batch or waiting phase, indexed
  count, and uploads awaiting indexing.
- `~/data/meow-10k/ingestion.json`: each video's upload receipt and confirmed
  indexing state, including any request needing reconciliation.
- `~/data/meow-10k/manifest.json`: download and checksum-verification state for
  every source file, including non-video companions.

The detached background jobs on the VM continue when the laptop's SSH connection
closes. A queued or uploaded video is not yet confirmed searchable; check the
journal's `indexed` state and the pipeline's completion state before reporting
completion.

The coordinator uploads at most 25 files per batch. Its `--max-pending` option
limits acknowledged uploads awaiting indexing (default 100). It stops after
30 minutes without newly confirmed indexed videos.
This queue setting does not change the approved prompt or video visibility.

### Scripts and VM setup

The six scripts are in [`scripts/data/`](../scripts/data/):

| Script | Purpose |
| --- | --- |
| `download_meow.py` | Download and checksum-verify the pinned source snapshot. |
| `ingest_meow.py` | Upload verified videos with fixed settings and a durable journal. |
| `verify_meow.py` | Reconcile upload receipts with fully indexed Explore records. |
| `run_meow_pipeline.py` | Coordinate bounded upload batches and indexing checks. |
| `build_meow_metadata.py` | Link source-video provenance to uploaded videos and clips. |
| `summarize_meow.py` | Refresh aggregate metadata in both existing indexes. |

Run these scripts on the configured workshop VM with Python 3.10 or newer.
They use the Python standard library and Unix file locks. The coordinator
expects its helper scripts alongside the data in `~/data/meow-10k/`; copy all
six scripts there before using it. Keep the settings file there with its exact
bytes, since the journal binds its SHA256. Do not overwrite existing settings
or private state when installing the scripts.

The downloader creates the manifest. An initial bounded upload with
`ingest_meow.py --limit 1` creates the ingestion journal. The coordinator and
summary scripts expect that journal, verified source videos, and both existing
indexes containing the pinned Meow dataset entry. They are continuation tools,
not a replacement for initial setup. Load the existing workshop configuration
in the same Bash session; `INGRESS_URL`, `USERNAME`, and `PASSWORD` are required
for authenticated operations. Never commit their values.

Keep downloaded media, manifests, upload journals, clip links, and the full
provenance index outside Git. Diagnostic reports are not part of this tooling.
Adding these scripts does not run ingestion or change the shared pipeline.

## Index conventions

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
