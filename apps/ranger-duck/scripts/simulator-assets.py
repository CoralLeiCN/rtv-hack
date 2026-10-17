#!/usr/bin/env python3
"""Fetch only pinned Microduck assets, verifying every size and SHA-256 digest."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without downloading")
    args = parser.parse_args()
    app = Path(__file__).resolve().parent.parent
    manifest = json.loads((app / "frontend/src/simulator/assets-manifest.json").read_text())
    target = app / "frontend/public/simulator"

    def valid(path, item):
        return path.is_file() and path.stat().st_size == item["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

    def fetch(item):
        path = target / item["path"]
        if valid(path, item):
            return
        if args.check:
            raise RuntimeError(f"Missing or changed asset: {item['path']}")
        url = f"{manifest['repository']}/resolve/{manifest['revision']}/app/public/{item['path']}"
        request = urllib.request.Request(url, headers={"User-Agent": "RangerDuckAssetSetup/1"})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(item["bytes"] + 1)
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Asset integrity check failed: {item['path']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".download")
        temporary.write_bytes(data)
        temporary.replace(path)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(fetch, manifest["files"]))
    print(f"Verified {len(manifest['files'])} simulator assets at revision {manifest['revision'][:12]}.")


if __name__ == "__main__":
    main()
