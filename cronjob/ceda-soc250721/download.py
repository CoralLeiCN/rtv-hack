#!/usr/bin/env python3
"""Download and verify the indexed CEDA source on Linux or macOS.

The index is read only. A failed or interrupted download leaves its .part file
for the next run. An invalid final file is never replaced automatically.
"""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SOURCE_ID = "ceda-soc250721-JC241_HDSCI_DIVE403_17"
FILENAME = "JC241_HDSCI_DIVE403_17.mp4"
SOURCE_URL = (
    "https://dap.ceda.ac.uk/bodc/deposits01/soc250721/"
    "JC241_HDSCI_DIVE403_17.mp4?download=1"
)
VM_INDEX = Path("~/data/ceda/external-videos.json").expanduser()
REPO_INDEX = Path(__file__).resolve().parents[2] / "data/external-videos.json"
BLOCK_SIZE = 1024 * 1024


class CedaRedirectHandler(HTTPRedirectHandler):
    """Keep redirects on the same official HTTPS source file."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urlsplit(newurl)
        source = urlsplit(SOURCE_URL)
        if (
            (destination.scheme, destination.netloc, destination.path)
            != (source.scheme, source.netloc, source.path)
            or destination.query not in ("", "download=1")
            or destination.fragment
        ):
            raise ValueError("Refusing a redirect away from the official CEDA source file")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_source(index_path):
    """Use publisher expectations, never a previously computed local checksum."""
    with index_path.open(encoding="utf-8") as stream:
        index = json.load(stream)
    videos = index.get("videos") if isinstance(index, dict) else None
    if not isinstance(videos, list):
        raise ValueError("Index must contain a videos list")
    matches = [v for v in videos if isinstance(v, dict) and v.get("id") == SOURCE_ID]
    if len(matches) != 1:
        raise ValueError(f"Index must contain exactly one source record: {SOURCE_ID}")
    source = matches[0]
    if source.get("filename") != FILENAME or source.get("source_url") != SOURCE_URL:
        raise ValueError("Source filename or URL does not match the fixed CEDA MP4")
    size = source.get("expected_size_bytes")
    checksum = source.get("checksum")
    if type(size) is not int or size <= 0:
        raise ValueError("Source expected_size_bytes must be a positive integer")
    if not isinstance(checksum, dict) or checksum.get("algorithm") != "md5":
        raise ValueError("Source must provide a publisher MD5 checksum")
    expected_md5 = checksum.get("expected")
    if not isinstance(expected_md5, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", expected_md5):
        raise ValueError("Source checksum.expected must contain 32 hexadecimal digits")
    return size, expected_md5.lower()


@contextmanager
def regular_file(path, flags):
    """Refuse symlinks and non-regular files at managed file paths."""
    descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"Not a regular file: {path}")
        mode = "r+b" if flags & os.O_RDWR else "rb"
        stream = os.fdopen(descriptor, mode)
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        yield stream


@contextmanager
def download_lock(path):
    # Keep the lock file: deleting it could allow callers to lock different inodes.
    with regular_file(path, os.O_CREAT | os.O_RDWR) as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"Another downloader holds {path}; retry after it exits") from None
        yield


def verify(stream, expected_size, expected_md5):
    actual_size = os.fstat(stream.fileno()).st_size
    if actual_size != expected_size:
        raise ValueError(f"Size mismatch: expected {expected_size}, found {actual_size} bytes")
    stream.seek(0)
    digest = hashlib.md5(usedforsecurity=False)
    for block in iter(lambda: stream.read(BLOCK_SIZE), b""):
        digest.update(block)
    if digest.hexdigest() != expected_md5:
        raise ValueError("Publisher MD5 mismatch; file preserved for inspection")


def validate_response(response, offset, expected_size):
    expected_status = 206 if offset else 200
    if response.status != expected_status:
        raise ValueError(f"Expected HTTP {expected_status}, received {response.status}")
    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise ValueError("Server returned an encoded body; refusing unsafe byte offsets")
    content_range = response.headers.get("Content-Range")
    if offset:
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range or "")
        expected_range = (offset, expected_size - 1, expected_size)
        if not match or tuple(map(int, match.groups())) != expected_range:
            raise ValueError("Content-Range does not match the requested offset, end and total")
    elif content_range is not None:
        raise ValueError("Unexpected Content-Range for a full download")
    length = response.headers.get("Content-Length", "")
    if not re.fullmatch(r"\d+", length) or int(length) != expected_size - offset:
        raise ValueError("Content-Length does not match the remaining expected bytes")


def fetch_remaining(stream, expected_size):
    offset = os.fstat(stream.fileno()).st_size
    if offset > expected_size:
        raise ValueError("Partial file exceeds the expected size; file preserved for inspection")
    if offset == expected_size:
        return
    headers = {"Accept-Encoding": "identity", "User-Agent": "ceda-source-downloader/1.0"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = Request(SOURCE_URL, headers=headers)
    print(f"Downloading {FILENAME} from byte {offset} of {expected_size}", flush=True)
    with build_opener(CedaRedirectHandler()).open(request, timeout=60) as response:
        validate_response(response, offset, expected_size)
        stream.seek(offset)
        remaining = expected_size - offset
        while remaining:
            block = response.read(min(BLOCK_SIZE, remaining))
            if not block:
                raise OSError("Download ended early; partial file preserved for resume")
            stream.write(block)
            remaining -= len(block)
        if response.read(1):
            raise ValueError("Response exceeded the expected byte count")
    stream.flush()
    os.fsync(stream.fileno())


def download(index_path, output_dir, verify_only=False):
    expected_size, expected_md5 = read_source(index_path)
    final = output_dir / FILENAME
    if verify_only:
        with regular_file(final, os.O_RDONLY) as stream:
            verify(stream, expected_size, expected_md5)
        print(f"Verified existing file; kept {final}")
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    partial = output_dir / (FILENAME + ".part")
    with download_lock(output_dir / (FILENAME + ".lock")):
        if os.path.lexists(final):
            with regular_file(final, os.O_RDONLY) as stream:
                verify(stream, expected_size, expected_md5)
            print(f"Already verified; kept {final}")
            return
        with regular_file(partial, os.O_CREAT | os.O_RDWR) as stream:
            fetch_remaining(stream, expected_size)
            verify(stream, expected_size, expected_md5)
        # Same-directory hard linking publishes atomically and fails if final exists.
        # Unlike rename/replace, it cannot overwrite a file created during the run.
        os.link(partial, final, follow_symlinks=False)
        partial.unlink()
        print(f"Verified size and publisher MD5; saved {final}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_index = VM_INDEX if VM_INDEX.exists() or not REPO_INDEX.exists() else REPO_INDEX
    parser.add_argument(
        "--index", type=Path, default=default_index,
        help=("Read-only video index (default: ~/data/ceda/external-videos.json; "
              "falls back to repository data/external-videos.json when present)"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("~/data/ceda/soc250721"),
        help="Download directory (default: ~/data/ceda/soc250721)",
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Require and verify the existing final file without downloads or writes",
    )
    args = parser.parse_args()
    try:
        download(args.index.expanduser(), args.output_dir.expanduser(), args.verify_only)
    except (OSError, ValueError, RuntimeError, HTTPException) as error:
        print(f"Download failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Download interrupted; partial file preserved for resume", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
