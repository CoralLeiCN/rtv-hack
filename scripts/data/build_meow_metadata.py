#!/usr/bin/env python3
"""Build VM-only provenance links for Meow videos and observed indexed clips.

This index enriches application results; it does not change VSS filter columns.
Source manifests, ingestion settings, upload receipts and media stay untouched.
Only aggregate counts and the output checksum are printed, never storage URIs.
"""
import argparse
from collections import Counter
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.parse

REPO = "smgjch/meow-10k"
REVISION = "41e4014ef226bd822dec22be61cf5eee7f12088a"
DATASET_ID = "hf-smgjch-meow-10k"
DATASET_URL = "https://huggingface.co/datasets/" + REPO
EXPECTED_VIDEOS = 6735


def atomic(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def object_key_from_uri(uri):
    parsed = urllib.parse.urlsplit(uri)
    if (parsed.scheme != "s3" or not parsed.netloc or not parsed.path.startswith("/")
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("Invalid clip storage reference")
    return parsed.path[1:]


def build_document(manifest, journal, links, expected_videos=EXPECTED_VIDEOS):
    if manifest.get("dataset") != REPO or manifest.get("revision") != REVISION:
        raise ValueError("Unexpected source dataset or revision")
    files = manifest["files"]
    seen = set()
    source_videos = {}
    for record in files:
        path = record["path"]
        relative = PurePosixPath(path)
        if (relative.is_absolute() or ".." in relative.parts or str(relative) != path
                or not path or path in seen):
            raise ValueError("Unsafe or repeated source path")
        seen.add(path)
        if relative.suffix.lower() == ".mp4":
            source_videos[path] = record
    if len(source_videos) != expected_videos:
        raise ValueError("Unexpected number of source videos")
    entries = journal["videos"]
    if not set(entries).issubset(source_videos):
        raise ValueError("Upload journal references an unknown video")
    version = journal["settings_version"]
    if not isinstance(version, str) or not version:
        raise ValueError("Missing ingestion settings version")
    shared = {
        "dataset": "meow-10k", "dataset_id": DATASET_ID,
        "dataset_name": "Meow-10k", "dataset_source_url": DATASET_URL,
        "dataset_revision": REVISION,
    }
    videos = {}
    object_keys = set()
    for path, source in sorted(source_videos.items()):
        source_url = DATASET_URL + "/resolve/" + REVISION + "/" + urllib.parse.quote(path)
        if source.get("source_url") != source_url:
            raise ValueError("Source URL does not match pinned source path")
        checksum = source.get("sha256")
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("Source video has no verified SHA256")
        if (source.get("download_status") != "verified"
                or source.get("actual_size_bytes") != source.get("expected_size_bytes")):
            raise ValueError("Source video is not verified")
        entry = entries.get(path)
        key = entry.get("object_key") if entry else None
        status = entry["status"] if entry else "not_submitted"
        if entry:
            if (entry.get("source_path") != path or entry.get("source_sha256") != checksum
                    or entry.get("settings_version") != version):
                raise ValueError("Upload receipt does not match source or settings")
            if status in ("uploaded", "indexed") and not key:
                raise ValueError("Acknowledged upload has no object key")
        if key:
            if not isinstance(key, str) or key.startswith("/") or key in object_keys:
                raise ValueError("Invalid or repeated upload object key")
            object_keys.add(key)
        videos[path] = {
            **shared, "source_path": path, "source_url": source_url,
            "source_sha256": checksum, "object_key": key,
            "ingestion_status": status, "settings_version": version,
        }
    clips = {}
    for source_uri, link in sorted(links.get("clips", {}).items()):
        object_key_from_uri(source_uri)
        path = link["source_path"]
        video = videos.get(path)
        if video is None or not video["object_key"]:
            raise ValueError("Clip references an unknown or unuploaded parent")
        if (link["object_key"] != video["object_key"]
                or object_key_from_uri(link["original_video_uri"]) != video["object_key"]):
            raise ValueError("Clip parent does not match upload receipt")
        segment = link.get("segment_number")
        if not isinstance(segment, int) or isinstance(segment, bool) or segment < 1:
            raise ValueError("Invalid clip segment number")
        start, end = link.get("start_seconds"), link.get("end_seconds")
        if start is not None or end is not None:
            if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                    or not 0 <= start <= end):
                raise ValueError("Invalid clip timing")
        observed = link.get("observed_at_utc")
        if not isinstance(observed, str) or not observed:
            raise ValueError("Clip lacks observation timestamp")
        clips[source_uri] = {
            **video, "source_uri": source_uri,
            "original_video_uri": link["original_video_uri"],
            "segment_number": segment, "start_seconds": start,
            "end_seconds": end, "observed_at_utc": observed,
            "dataset_tag_present": link.get("dataset_tag_present"),
        }
    return {
        "schema_version": 1,
        "updated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dataset": {
            "dataset": "meow-10k", "dataset_id": DATASET_ID, "name": "Meow-10k",
            "repository": REPO, "source_url": DATASET_URL, "revision": REVISION,
            "licence": "Apache-2.0", "licence_scope": "declared by dataset card",
        },
        "metadata_scope": "Linked provenance; native VSS dataset filter uses the meow-10k tag",
        "video_count": len(videos), "clip_count": len(clips),
        "videos": videos, "clips": clips,
    }


def refresh(root):
    root = Path(root)
    with (root / ".dataset-metadata.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Uploader and verifier hold this lock exclusively. Read their journal
        # and clip links as one snapshot, then release before serialization.
        with (root / ".ingest.lock").open("a") as ingest_lock:
            fcntl.flock(ingest_lock, fcntl.LOCK_SH)
            manifest_raw = (root / "manifest.json").read_bytes()
            journal_raw = (root / "ingestion.json").read_bytes()
            links_path = root / "clip-links.json"
            has_links = links_path.exists()
            links_raw = links_path.read_bytes() if has_links else b'{"clips":{}}'
        document = build_document(json.loads(manifest_raw), json.loads(journal_raw), json.loads(links_raw))
        document["input_sha256"] = {
            "manifest": hashlib.sha256(manifest_raw).hexdigest(),
            "ingestion": hashlib.sha256(journal_raw).hexdigest(),
            "clip_links": hashlib.sha256(links_raw).hexdigest() if has_links else None,
        }
        output = root / "dataset-metadata.json"
        atomic(output, document)
        return {
            "video_count": document["video_count"], "clip_count": document["clip_count"],
            "video_counts_by_ingestion_status": dict(sorted(Counter(
                row["ingestion_status"] for row in document["videos"].values()).items())),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "updated_at_utc": document["updated_at_utc"],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "data/meow-10k")
    args = parser.parse_args()
    print(json.dumps(refresh(args.root)))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Storage references may contain private infrastructure names. Never log
        # exception text, input records or traceback content.
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1)
