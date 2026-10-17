# CEDA soc250721 video jobs

Scripts for the first CEDA source video, `JC241_HDSCI_DIVE403_17.mp4`, and its
54 derived clips. They are collected from the download and ingestion work for
this dataset. The download and split steps, originally run inline, are now
saved as reusable scripts.

The VM copy of this folder is `~/cronjob/ceda-soc250721`. Media and runtime state
stay in `~/data/ceda`; moving these scripts does not move or duplicate videos.
The live provenance index is `~/data/ceda/external-videos.json`. The repository's
[`data/external-videos.json`](../../data/external-videos.json) is a local snapshot.

| Script | Purpose | Run on |
| --- | --- | --- |
| `download.py` | Download or verify the selected source using its publisher MD5 and byte count | VM |
| `split.py` | Prepare or validate clips below 100 MB using FFmpeg stream copy | VM |
| `upload.py` | Upload the confirmed batch sequentially and save returned object keys | VM |
| `monitor.py`, `monitor.sh` | Verify complete indexing and private visibility; update the live index | VM |
| `status.py` | Read the VSS dashboard and report batch matches | VM |
| `verify_uploads.py` | Check stored sizes, private access and ingest metadata | VM |
| `with_config.sh` | Load the single `/config/*.config` file without printing credentials | VM |
| `sync_index.py` | Copy the live VM index into this repository | Laptop |

## Current batch

All 54 uploads were accepted with private visibility, the confirmed seabed
prompt, and the metadata recorded in the index. Upload receipts and indexing
are separate states. The background monitor checks every 60 seconds. Its PID,
status and last successful check are in `ingest_batches[].monitor`; its log is
`~/data/ceda/ceda-ingest-monitor.log`.

The uploader skips clips with saved object keys and refuses uncertain upload
states. Upload and monitoring use the same lock to prevent concurrent index
writers. Do not start an uploader while the monitor holds that lock. Restarting
the monitor does not upload or re-ingest videos.

## Commands

Connect using the configured SSH alias, then run commands in the VM folder:

```bash
ssh bc-iverson930g
cd ~/cronjob/ceda-soc250721
python3 download.py --help
python3 split.py --help
python3 download.py --verify-only
python3 split.py --verify-only
./with_config.sh python3 status.py
./with_config.sh python3 verify_uploads.py
```

Without `--verify-only`, the download and split scripts prepare missing media;
they validate and keep matching existing files. They leave the live index and
its upload states unchanged. New splits produce a `preparation-manifest.json`
for review before those files are registered for upload. Both scripts support
`--index` and output-path overrides; run `--help` for the options.

The saved uploader requires `--confirmed`, representing the user's approval of
the paths and settings in the index. The current batch is already uploaded.
For a reviewed batch that still needs uploading, use:

```bash
./with_config.sh python3 upload.py --confirmed
```

To run the monitor in the foreground after any existing monitor has stopped:

```bash
./monitor.sh
```

The monitor ends when all 54 files are fully indexed and private. It records
`needs_attention` if visibility differs, checks fail for an hour, or indexing
makes no progress for 24 hours. A VM shutdown stops the background process;
it is not a startup service.

Refresh the repository index from the laptop, from the repository root:

```bash
python3 cronjob/ceda-soc250721/sync_index.py
```

Use `--host` for another configured SSH alias or `--output` for a different
snapshot path. Runtime configuration and credentials stay on the VM. Python 3
is required; splitting also needs FFmpeg/ffprobe, and storage verification uses
the VM's existing boto3 installation. The workshop S3 verification script uses
the internal endpoint's existing certificate handling.
