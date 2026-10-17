#!/usr/bin/env python3
"""Summarize Meow metadata and refresh existing provenance indexes, without media I/O.

Both index paths must already exist. Each replacement is atomic; replacing the
two indexes is not a filesystem transaction. Rerunning repairs an interrupted
mirror update while preserving each index's unrelated records.
"""
import argparse
from collections import defaultdict
import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from build_meow_metadata import refresh as refresh_dataset_metadata

REPO = "smgjch/meow-10k"
REVISION = "41e4014ef226bd822dec22be61cf5eee7f12088a"
DATASET_ID = "hf-smgjch-meow-10k"


def atomic(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def summarize(manifest):
    if manifest.get("dataset") != REPO or manifest.get("revision") != REVISION:
        raise ValueError("Unexpected dataset or revision in manifest")
    files = manifest["files"]
    if not files:
        raise ValueError("Manifest has no files")
    groups = defaultdict(lambda: {"files": 0, "expected_size_bytes": 0,
                                  "verified_size_bytes": 0})
    statuses = defaultdict(int)
    seen = set()
    for record in files:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts or str(relative) in seen:
            raise ValueError("Unsafe or repeated manifest path")
        seen.add(str(relative))
        status = record["download_status"]
        expected = record["expected_size_bytes"]
        if not isinstance(expected, int) or expected < 0:
            raise ValueError("Invalid expected file size")
        group = groups[(relative.suffix.lower() or "[no extension]", status)]
        group["files"] += 1
        group["expected_size_bytes"] += expected
        statuses[status] += 1
        if status == "verified":
            if record.get("actual_size_bytes") != expected or not record.get("sha256"):
                raise ValueError("Verified record lacks matching size or SHA256")
            group["verified_size_bytes"] += expected
    state = manifest.get("download_status", "in_progress")
    if state == "verified" and statuses.get("verified", 0) != len(files):
        raise ValueError("Dataset marked verified while files are incomplete")
    return {
        "status": state,
        "total_files": len(files),
        "file_counts_by_status": dict(sorted(statuses.items())),
        "expected_size_bytes": sum(row["expected_size_bytes"] for row in groups.values()),
        "verified_size_bytes": sum(row["verified_size_bytes"] for row in groups.values()),
        "by_extension_and_status": [
            {"extension": extension, "status": status, **groups[(extension, status)]}
            for extension, status in sorted(groups)
        ],
    }


def summarize_ingestion(data_root, manifest):
    journal_path = data_root / "meow-10k/ingestion.json"
    if not journal_path.exists():
        return None
    raw = journal_path.read_bytes()
    journal = json.loads(raw)
    settings_raw = (data_root / "meow-10k/meow-ingestion-v1.json").read_bytes()
    settings = json.loads(settings_raw)
    settings_sha256 = hashlib.sha256(settings_raw).hexdigest()
    if (journal["settings_sha256"] != settings_sha256
            or journal["settings_version"] != settings["settings_version"]
            or settings.get("dataset") != REPO
            or settings.get("revision") != REVISION):
        raise ValueError("Ingestion journal settings do not match approved snapshot")
    video_paths = {record["path"] for record in manifest["files"]
                   if Path(record["path"]).suffix.lower() == ".mp4"}
    entries = journal["videos"]
    if not set(entries).issubset(video_paths):
        raise ValueError("Ingestion journal references videos absent from manifest")
    counts = defaultdict(int)
    for entry in entries.values():
        counts[entry["status"]] += 1
    counts["not_submitted"] = len(video_paths) - len(entries)
    all_indexed = bool(video_paths) and counts.get("indexed", 0) == len(video_paths)
    return {
        "status": "indexed" if all_indexed else ("in_progress" if entries else "not_ingested"),
        "worker_status": journal.get("worker_status"),
        "pipeline_status_path": "~/data/meow-10k/pipeline-status.json",
        "visibility": "public" if settings["is_public"] else "private",
        "total_videos": len(video_paths),
        "video_counts_by_status": dict(sorted(counts.items())),
        "journal_path": "~/data/meow-10k/ingestion.json",
        "journal_sha256": hashlib.sha256(raw).hexdigest(),
        "journal_updated_at_utc": journal.get("updated_at_utc"),
        "settings_path": "~/data/meow-10k/meow-ingestion-v1.json",
        "settings_version": journal["settings_version"],
        "settings_sha256": settings_sha256,
        "indexed_at_utc": journal.get("updated_at_utc") if all_indexed else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path.home() / "data")
    args = parser.parse_args()
    manifest_path = args.data_root / "meow-10k/manifest.json"
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    summary = summarize(manifest)
    ingestion = summarize_ingestion(args.data_root, manifest)
    dataset_metadata = refresh_dataset_metadata(args.data_root / "meow-10k")
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest_reference = {
        "relative_path": "meow-10k/manifest.json",
        "relative_to": "data_directory",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "snapshot_at_utc": timestamp,
        "manifest_updated_at_utc": manifest.get("updated_at_utc"),
    }
    # Validate both existing indexes before replacing either; never create an
    # empty index when the expected provenance record is missing.
    updates = []
    for path in (args.data_root / "external-videos.json",
                 args.data_root / "ceda/external-videos.json"):
        index = json.loads(path.read_text(encoding="utf-8"))
        matches = [entry for entry in index.get("datasets", [])
                   if entry.get("id") == DATASET_ID]
        if len(matches) != 1 or matches[0].get("revision") != REVISION:
            raise ValueError("Index requires exactly one matching pinned Meow dataset")
        entry = matches[0]
        entry["manifest"] = manifest_reference
        entry.setdefault("storage", {})["dataset_metadata_path"] = "~/data/meow-10k/dataset-metadata.json"
        entry["dataset_metadata"] = {
            "storage_kind": "linked_provenance_index",
            "dataset": "meow-10k",
            "native_search_filter": {"tags": ["meow-10k"]},
            "relative_path": "meow-10k/dataset-metadata.json",
            **dataset_metadata,
        }
        if ingestion is not None:
            entry.setdefault("ingestion", {}).update(ingestion)
        entry["download"].update(
            status=summary["status"],
            expected_size_bytes=summary["expected_size_bytes"],
            verified_size_bytes=summary["verified_size_bytes"],
            actual_size_bytes=(summary["verified_size_bytes"]
                               if summary["status"] == "verified" else None),
            total_files=summary["total_files"],
            file_counts_by_status=summary["file_counts_by_status"],
            by_extension_and_status=summary["by_extension_and_status"],
            completed_at_utc=(manifest.get("completed_at_utc")
                              if summary["status"] == "verified" else None),
            summary_updated_at_utc=timestamp,
        )
        index["updated_at_utc"] = timestamp
        updates.append((path, index))
    for path, index in updates:
        atomic(path, index)
    print(json.dumps({"dataset": REPO, "revision": REVISION,
                      "manifest": manifest_reference, "ingestion": ingestion,
                      "dataset_metadata": dataset_metadata,
                      **summary}, indent=2))


if __name__ == "__main__":
    main()
