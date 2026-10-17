#!/usr/bin/env python3
"""Local browser QA with synthetic data only. Never connects to VSS."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


class FixtureHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path == "/config.js":
            config = {"apiBaseUrl": "", "resultTiming": {
                "startField": "fixture_start", "endField": "fixture_end", "unit": "seconds",
            }}
            body = ("window.VSS_CONFIG = " + json.dumps(config) + ";\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        pass

    def respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except (ValueError, TypeError):
            self.respond(400, {})
            return
        if self.path != "/api/v1/search":
            self.respond(404, {})
            return
        if not isinstance(body, dict) or set(body) != {"query"} or not isinstance(body["query"], str) or not body["query"].strip():
            self.respond(400, {})
            return
        query = body["query"]
        if query == "error":
            self.respond(500, {"detail": "Synthetic error; this detail must not reach the UI."})
        elif query == "malformed":
            self.respond(200, {"unexpected": []})
        elif query == "empty":
            self.respond(200, {"results": []})
        else:
            if query == "slow":
                time.sleep(3)
            description = (
                '<img src=x onerror="alert(1)"> Synthetic markup should appear as text.'
                if query == "markup" else
                "A forklift moves through a warehouse aisle while a person waits beside the shelving."
            )
            self.respond(200, {"results": [
                {"reasoning_content": description, "fixture_start": 0, "fixture_end": 12.5},
                {"reasoning_content": "A person walks past a parked forklift near the loading area.",
                 "fixture_start": 65, "fixture_end": 81},
            ]})


if __name__ == "__main__":
    handler = partial(FixtureHandler, directory=str(WEB_ROOT))
    with ThreadingHTTPServer(("127.0.0.1", 8001), handler) as server:
        print("SYNTHETIC TEST DATA ONLY: http://127.0.0.1:8001", flush=True)
        print("Search directly. Queries: empty, error, slow, malformed, markup.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
