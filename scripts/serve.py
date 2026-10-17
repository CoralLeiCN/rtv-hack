#!/usr/bin/env python3
"""Launch the local frontend and its minimal FastAPI adapter."""

import argparse
import os
from pathlib import Path
import sys


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    sys.path.insert(0, str(WEB_ROOT.parent))
    import uvicorn
    from server import app

    missing = [name for name in ("ARCHIVE_URL", "ARCHIVE_API_KEY") if not os.environ.get(name)]
    if missing:
        print("Missing archive configuration: " + ", ".join(missing) + ". Load it before searching.", flush=True)
    print(f"Video search: http://{args.bind}:{args.port}", flush=True)
    uvicorn.run(app, host=args.bind, port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
