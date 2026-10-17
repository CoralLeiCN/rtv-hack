#!/usr/bin/env python3
"""Prepare CEDA clips without changing the provenance index or upload states."""

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SOURCE_ID = "ceda-soc250721-JC241_HDSCI_DIVE403_17"
FILENAME = "JC241_HDSCI_DIVE403_17.mp4"
MAX_BYTES = 100_000_000
PREPARATION_MANIFEST = "preparation-manifest.json"
DEFAULT_INDEX = Path(__file__).resolve().parents[2] / "data/external-videos.json"


def default_index():
    vm_index = Path.home() / "data/ceda/external-videos.json"
    return vm_index if vm_index.exists() or not DEFAULT_INDEX.exists() else DEFAULT_INDEX


def digest(path, algorithm):
    result = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def run_json(command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def probe(path):
    result = run_json([
        "ffprobe", "-v", "error", "-count_packets", "-show_entries",
        "stream=index,codec_name,codec_type,nb_read_packets:format=duration",
        "-of", "json", str(path),
    ])
    streams = sorted(result["streams"], key=lambda stream: stream["index"])
    counts = [int(stream["nb_read_packets"]) for stream in streams]
    if any(count <= 0 for count in counts):
        raise ValueError(f"A stream has no packets: {path.name}")
    duration = float(result["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Invalid duration: {path.name}")
    return streams, counts, duration


def begins_with_keyframe(path):
    result = run_json([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-read_intervals", "%+1", "-show_packets", "-show_entries",
        "packet=flags", "-of", "json", str(path),
    ])
    packets = result.get("packets", [])
    return bool(packets and "K" in packets[0].get("flags", ""))


def stream_signature(streams):
    return [(stream["codec_type"], stream["codec_name"]) for stream in streams]


def check_clip(path, source_streams):
    size = path.stat().st_size
    if not 0 < size < MAX_BYTES:
        raise ValueError(f"Clip must be strictly below {MAX_BYTES} bytes: {path.name}")
    streams, counts, duration = probe(path)
    if stream_signature(streams) != stream_signature(source_streams):
        raise ValueError(f"Clip does not preserve all source streams: {path.name}")
    if not begins_with_keyframe(path):
        raise ValueError(f"Clip does not begin with a video keyframe: {path.name}")
    return size, counts, duration, digest(path, "sha256")


def check_ranges(records):
    previous_end = 0.0
    for sequence, record in enumerate(records, 1):
        timing = record["source_time_range_seconds"]
        start, end = float(timing["start"]), float(timing["end"])
        if (record["sequence"] != sequence or not math.isfinite(start)
                or not math.isfinite(end) or end <= start
                or abs(start - previous_end) > 0.001):
            raise ValueError("Clip source ranges are not contiguous and ordered")
        previous_end = end


def validate_existing(output_dir, index, source_streams, source_counts, seconds):
    manifest_path = output_dir / PREPARATION_MANIFEST
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("source_video_id") != SOURCE_ID:
            raise ValueError("Existing preparation manifest belongs to another source")
        if manifest.get("target_segment_seconds") != seconds:
            raise ValueError("Existing clips use a different target segment duration")
        records = manifest["clips"]
    else:
        records = sorted(
            (video for video in index["videos"]
             if video.get("source_video_id") == SOURCE_ID),
            key=lambda video: video["sequence"],
        )
        if any(record["derivation"]["target_segment_seconds"] != seconds
               for record in records):
            raise ValueError("Indexed clip metadata uses a different target duration")
    if not records:
        raise ValueError("Existing clip directory has no matching preparation metadata")
    names = [record["filename"] for record in records]
    if (len(set(names)) != len(names)
            or set(names) != {path.name for path in output_dir.glob("*.mp4")}):
        raise ValueError("Existing clip files differ from the preparation metadata")
    check_ranges(records)
    sums = [0] * len(source_counts)
    for record in records:
        name = record["filename"]
        if Path(name).name != name:
            raise ValueError("Clip metadata contains a non-basename filename")
        size, counts, _, actual_hash = check_clip(output_dir / name, source_streams)
        checksum = record["checksum"]
        if (size != record["size_bytes"] or checksum["algorithm"] != "sha256"
                or actual_hash != checksum["actual"]):
            raise ValueError(f"Existing clip differs from its recorded checksum: {name}")
        sums = [left + right for left, right in zip(sums, counts)]
    if sums != source_counts:
        raise ValueError("Existing clips do not conserve source packet counts")
    return len(records)


def prepare(source_path, output_dir, source_streams, source_counts, source_md5, seconds):
    # mkdir is exclusive: an existing directory is never replaced or cleared.
    output_dir.mkdir()
    csv_path = output_dir / "segments.csv"
    pattern = output_dir / f"{source_path.stem}_clip_%03d.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
        "-i", str(source_path), "-map", "0", "-c", "copy", "-f", "segment",
        "-segment_time", str(seconds), "-reset_timestamps", "1",
        "-segment_format_options", "movflags=+faststart",
        "-segment_start_number", "1", "-segment_list_type", "csv",
        "-segment_list", str(csv_path), str(pattern),
    ], check=True)
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    records, sums = [], [0] * len(source_counts)
    with csv_path.open(newline="") as stream:
        for sequence, row in enumerate(csv.reader(stream), 1):
            filename, start, end = row
            name = Path(filename).name
            path = output_dir / name
            size, counts, duration, actual_hash = check_clip(path, source_streams)
            sums = [left + right for left, right in zip(sums, counts)]
            records.append({
                "id": f"{SOURCE_ID}-clip-{sequence:03d}",
                "filename": name, "source_video_id": SOURCE_ID, "sequence": sequence,
                "storage": {"path": str(path)}, "size_bytes": size,
                "duration_seconds": duration,
                "source_time_range_seconds": {
                    "start": float(start), "end": float(end),
                    "basis": "FFmpeg segment muxer CSV; cuts follow video keyframes",
                },
                "derivation": {
                    "method": "ffmpeg_stream_copy", "target_segment_seconds": seconds,
                    "preserved_streams": len(source_streams), "created_at_utc": created_at,
                },
                "checksum": {"algorithm": "sha256", "actual": actual_hash,
                             "origin": "locally computed for derived clip"},
                "validation": {"size_below_100000000_bytes": True,
                               "starts_with_video_keyframe": True,
                               "packet_counts_by_stream": counts},
            })
    if not records or sums != source_counts:
        raise ValueError("New clips do not conserve all source packet counts")
    check_ranges(records)
    manifest = {
        "schema_version": 1, "status": "prepared", "source_video_id": SOURCE_ID,
        "source_path": str(source_path), "source_md5": source_md5,
        "created_at_utc": created_at, "target_segment_seconds": seconds,
        "clip_count": len(records), "total_bytes": sum(r["size_bytes"] for r in records),
        "max_clip_bytes": max(r["size_bytes"] for r in records),
        "source_packet_counts_by_stream": source_counts,
        "derived_packet_counts_by_stream": sums, "packet_conservation_verified": True,
        "clips": records,
    }
    fd, temporary = tempfile.mkstemp(prefix=".preparation-", dir=output_dir)
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps(manifest, indent=2) + "\n")
    os.replace(temporary, output_dir / PREPARATION_MANIFEST)
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=default_index(),
                        help="Read-only provenance index (default: ~/data/ceda/external-videos.json, or repository index locally)")
    parser.add_argument("--source", type=Path,
                        help="Source MP4 (default: source storage path recorded in the index)")
    parser.add_argument("--output-dir", type=Path,
                        help="Clip directory (default: SOURCE_DIRECTORY/clips/JC241_HDSCI_DIVE403_17)")
    parser.add_argument("--segment-seconds", type=float, default=120,
                        help="Target duration; cuts follow keyframes (default: 120)")
    parser.add_argument("--verify-only", action="store_true",
                        help="Validate existing clips only; do not create files or split media")
    args = parser.parse_args()
    if not math.isfinite(args.segment_seconds) or args.segment_seconds <= 0:
        parser.error("--segment-seconds must be positive and finite")
    if not all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe")):
        raise ValueError("ffmpeg and ffprobe must already be installed and on PATH")
    index = json.loads(args.index.expanduser().read_text())
    source = next(video for video in index["videos"] if video["id"] == SOURCE_ID)
    if source["filename"] != FILENAME or source["checksum"]["algorithm"] != "md5":
        raise ValueError("Unexpected source provenance record")
    source_path = (args.source or Path(source["storage"]["path"])).expanduser().resolve()
    if source_path.name != FILENAME:
        raise ValueError(f"Only {FILENAME} is supported")
    if source_path.stat().st_size != source["expected_size_bytes"]:
        raise ValueError("Source file does not match CEDA's size")
    source_md5 = digest(source_path, "md5")
    if source_md5 != source["checksum"]["expected"]:
        raise ValueError("Source file does not match CEDA's size and MD5")
    source_streams, source_counts, _ = probe(source_path)
    if (len(source_streams) != 3
            or sorted(s["codec_type"] for s in source_streams) != ["audio", "audio", "video"]):
        raise ValueError("Expected the source's three streams: two audio and one video")
    output_dir = (args.output_dir or source_path.parent / "clips" / source_path.stem).expanduser().absolute()
    if args.verify_only:
        if not output_dir.is_dir():
            raise ValueError("Existing clip directory required for --verify-only")
        count = validate_existing(output_dir, index, source_streams, source_counts, args.segment_seconds)
        status = "existing_verified"
    else:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        with (output_dir.parent / f".{output_dir.name}.prepare.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if output_dir.exists():
                count = validate_existing(output_dir, index, source_streams, source_counts, args.segment_seconds)
                status = "existing_verified"
            else:
                count = prepare(source_path, output_dir, source_streams, source_counts, source_md5, args.segment_seconds)
                status = "prepared"
    print(json.dumps({"status": status, "clip_count": count, "output_dir": str(output_dir),
                      "preparation_manifest": str(output_dir / PREPARATION_MANIFEST)
                      if (output_dir / PREPARATION_MANIFEST).exists() else None,
                      "index_modified": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as exc:
        print(f"Preparation stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Existing clips and index states were not replaced; any newly created partial directory is retained.", file=sys.stderr)
        sys.exit(1)
