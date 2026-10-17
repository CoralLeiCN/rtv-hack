"""Verify authenticated video playback without exposing the workshop session."""

import asyncio
import json
import unittest
from urllib.parse import urlencode

from fastapi.testclient import TestClient
import httpx

from server import create_app


BACKEND = "https://private-vss.example/team-prefix"
USERNAME = "synthetic-workshop-user"
PASSWORD = "synthetic-password-private-marker"
TOKEN = "synthetic-session-private-marker"
PRIVATE_DETAIL = "synthetic-upstream-private-diagnostic"
SOURCE = "s3://workshop-bucket/videos/loading bay/clip.mp4"
STREAM_PATH = "/api/v1/videos/stream"


class TrackedStream(httpx.AsyncByteStream):
    def __init__(self, chunks, stall=False):
        self.chunks = chunks
        self.stall = stall
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.stall:
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


def video_response(status=200, chunks=(b"synthetic-", b"video"), headers=None):
    stream = TrackedStream(chunks)
    return httpx.Response(status, headers=headers or {"Content-Type": "video/mp4"}, stream=stream), stream


class VideoStreamTests(unittest.TestCase):
    def make_client(self, video_handler=None, login_tokens=None, source=SOURCE):
        self.requests = []
        tokens = iter(login_tokens or [TOKEN])

        def upstream(request):
            self.requests.append(request)
            if request.url.path.endswith("/auth/login"):
                return httpx.Response(200, json={"access_token": next(tokens), "password": PASSWORD}, headers={
                    "Set-Cookie": "private-session=synthetic-cookie; Path=/; Secure; HttpOnly",
                })
            if request.url.path.endswith("/search"):
                return httpx.Response(200, json={"results": [{"source": source}]})
            return video_handler(request)

        app = create_app(BACKEND, username=USERNAME, password=PASSWORD, transport=httpx.MockTransport(upstream))
        client = self.enterContext(TestClient(app))
        if source is not None:
            self.assertEqual(client.post("/api/v1/search", json={"query": "forklift"}).status_code, 200)
        return client

    def assert_private_values_absent(self, response):
        public = response.text + str(response.headers)
        for private in (USERNAME, PASSWORD, TOKEN, PRIVATE_DETAIL, BACKEND):
            self.assertNotIn(private, public)
        self.assertNotIn("set-cookie", response.headers)
        self.assertNotIn("location", response.headers)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def assert_safe_error(self, response, expected):
        self.assertEqual(response.status_code, expected)
        self.assertEqual(set(response.json()), {"detail"})
        self.assert_private_values_absent(response)

    def test_full_video_stream_uses_cached_server_session_and_only_media_headers(self):
        upstream_response, stream = video_response(headers={
            "Content-Type": "video/mp4", "Content-Length": "15", "Accept-Ranges": "bytes",
            "X-Private-Debug": PRIVATE_DETAIL, "X-Session-Token": TOKEN,
            "Set-Cookie": "private-session=synthetic-cookie; Path=/; Secure; HttpOnly",
        })
        client = self.make_client(lambda request: upstream_response)
        response = client.get(STREAM_PATH, params={"source": SOURCE}, headers={
            "Authorization": "Bearer caller-session-marker", "Cookie": "browser-cookie=private",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"synthetic-video")
        self.assertEqual(response.headers["content-type"], "video/mp4")
        self.assertEqual(response.headers["content-length"], "15")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertNotIn("x-private-debug", response.headers)
        self.assertNotIn("x-session-token", response.headers)
        self.assert_private_values_absent(response)
        self.assertTrue(stream.closed)
        self.assertEqual(len(self.requests), 3)
        login, search, media = self.requests
        self.assertEqual(json.loads(login.content), {"username": USERNAME, "password": PASSWORD})
        self.assertEqual(media.method, "GET")
        self.assertEqual(str(media.url.copy_with(query=None)), BACKEND + STREAM_PATH)
        self.assertEqual(dict(media.url.params), {"source": SOURCE, "token": TOKEN})
        self.assertEqual(media.headers["accept-encoding"], "identity")
        self.assertNotIn("cookie", media.headers)
        self.assertNotIn("caller-session-marker", str(media.headers))
        self.assertEqual(search.headers["authorization"], "Bearer " + TOKEN)

    def test_range_requests_preserve_partial_response_for_seeking(self):
        streams = []

        def upstream(request):
            self.assertEqual(request.headers["range"], "bytes=5-9")
            response, stream = video_response(206, chunks=(b"567", b"89"), headers={
                "Content-Type": "video/mp4", "Content-Length": "5",
                "Content-Range": "bytes 5-9/20", "Accept-Ranges": "bytes",
            })
            streams.append(stream)
            return response

        client = self.make_client(upstream)
        response = client.get(STREAM_PATH, params={"source": SOURCE}, headers={"Range": "bytes=5-9"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"56789")
        self.assertEqual(response.headers["content-range"], "bytes 5-9/20")
        self.assertEqual(response.headers["content-length"], "5")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertTrue(streams[0].closed)

    def test_octet_stream_is_accepted_for_video_storage_responses(self):
        for content_type in ("application/octet-stream", "binary/octet-stream"):
            with self.subTest(content_type=content_type):
                upstream_response, stream = video_response(headers={"Content-Type": content_type})
                client = self.make_client(lambda request: upstream_response)
                response = client.get(STREAM_PATH, params={"source": SOURCE})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b"synthetic-video")
                self.assertEqual(response.headers["content-type"], "video/mp4")
                self.assertTrue(stream.closed)

    def test_unsatisfiable_range_preserves_total_size_without_upstream_body(self):
        upstream_response, stream = video_response(416, chunks=(PRIVATE_DETAIL.encode(),), headers={
            "Content-Range": "bytes */20", "Content-Type": "text/html", "X-Session-Token": TOKEN,
        })
        client = self.make_client(lambda request: upstream_response)
        response = client.get(STREAM_PATH, params={"source": SOURCE}, headers={"Range": "bytes=100-"})
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["content-range"], "bytes */20")
        self.assert_private_values_absent(response)
        self.assertTrue(stream.closed)

    def test_expired_session_closes_rejected_stream_then_refreshes_once(self):
        streams = []

        def upstream(request):
            if streams:
                self.assertTrue(streams[0].closed)
            status = 401 if request.url.params["token"] == TOKEN else 200
            response, stream = video_response(status, chunks=(b"video",))
            streams.append(stream)
            return response

        client = self.make_client(upstream, login_tokens=[TOKEN, "synthetic-refreshed-session"])
        response = client.get(STREAM_PATH, params={"source": SOURCE})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"video")
        self.assertEqual([request.url.path for request in self.requests], [
            "/team-prefix/api/v1/auth/login", "/team-prefix/api/v1/search", "/team-prefix/api/v1/videos/stream",
            "/team-prefix/api/v1/auth/login", "/team-prefix/api/v1/videos/stream",
        ])
        self.assertTrue(all(stream.closed for stream in streams))
        self.assert_private_values_absent(response)
        self.assertNotIn("synthetic-refreshed-session", str(response.headers))

    def test_repeated_session_rejection_is_bounded_and_invalidates_cached_token(self):
        streams = []

        def upstream(request):
            token = request.url.params["token"]
            status = 200 if token == "synthetic-third-session" else 401
            response, stream = video_response(status, chunks=(b"video",))
            streams.append(stream)
            return response

        client = self.make_client(upstream, login_tokens=[TOKEN, "synthetic-second-session", "synthetic-third-session"])
        self.assert_safe_error(client.get(STREAM_PATH, params={"source": SOURCE}), 503)
        self.assertEqual(len(self.requests), 5)
        self.assertTrue(all(stream.closed for stream in streams))
        self.assertEqual(client.get(STREAM_PATH, params={"source": SOURCE}).status_code, 200)
        self.assertEqual(len(self.requests), 7)
        self.assertTrue(all(stream.closed for stream in streams))

    def test_missing_blank_and_excessive_source_are_rejected_before_login(self):
        client = self.make_client(source=None)
        for params in ({}, {"source": ""}, {"source": " \n\t "}, {"source": "x" * 20000}):
            with self.subTest(length=len(params.get("source", ""))):
                self.assert_safe_error(client.get(STREAM_PATH, params=params), 422)
        self.assertEqual(self.requests, [])

    def test_source_is_an_opaque_parameter_and_does_not_control_upstream_address(self):
        upstream_response, stream = video_response()
        remote_source = "https://unrelated.example/collect?token=caller-token"
        client = self.make_client(lambda request: upstream_response, source=remote_source)
        response = client.get(STREAM_PATH, params={"source": remote_source})
        self.assertEqual(response.status_code, 200)
        media = self.requests[-1]
        self.assertEqual(media.url.host, "private-vss.example")
        self.assertEqual(media.url.path, "/team-prefix/api/v1/videos/stream")
        self.assertEqual(media.url.params["source"], remote_source)
        self.assertEqual(media.url.params["token"], TOKEN)
        self.assertTrue(stream.closed)

    def test_source_not_returned_by_authenticated_search_is_rejected_without_fetching(self):
        client = self.make_client(source=None)
        self.assert_safe_error(client.get(STREAM_PATH, params={"source": SOURCE}), 403)
        self.assertEqual(self.requests, [])
        client = self.make_client()
        previous_count = len(self.requests)
        self.assert_safe_error(client.get(STREAM_PATH, params={"source": "s3://another-bucket/private.mp4"}), 403)
        self.assertEqual(len(self.requests), previous_count)

    def test_html_or_other_nonvideo_success_response_is_rejected_and_closed(self):
        for content_type in ("text/html", "application/json", "text/plain"):
            with self.subTest(content_type=content_type):
                upstream_response, stream = video_response(chunks=(PRIVATE_DETAIL.encode(),), headers={"Content-Type": content_type})
                client = self.make_client(lambda request: upstream_response)
                self.assert_safe_error(client.get(STREAM_PATH, params={"source": SOURCE}), 502)
                self.assertTrue(stream.closed)

    def test_upstream_errors_are_redacted_and_closed(self):
        for status, expected in ((400, 400), (403, 403), (404, 404), (429, 429), (500, 502), (503, 502)):
            with self.subTest(status=status):
                upstream_response, stream = video_response(status, chunks=(PRIVATE_DETAIL.encode(),), headers={
                    "Content-Type": "text/html", "X-Session-Token": TOKEN,
                })
                client = self.make_client(lambda request: upstream_response)
                self.assert_safe_error(client.get(STREAM_PATH, params={"source": SOURCE}), expected)
                self.assertTrue(stream.closed)
                self.assertEqual(len(self.requests), 3)

    def test_redirect_is_neither_followed_nor_returned_to_browser(self):
        upstream_response, stream = video_response(307, chunks=(PRIVATE_DETAIL.encode(),), headers={
            "Location": "https://unrelated.example/collect?token=" + TOKEN,
        })
        client = self.make_client(lambda request: upstream_response)
        self.assert_safe_error(client.get(STREAM_PATH, params={"source": SOURCE}), 502)
        self.assertTrue(stream.closed)
        self.assertEqual(len(self.requests), 3)
        self.assertTrue(all(request.url.host == "private-vss.example" for request in self.requests))

    def test_timeout_and_connection_failures_before_stream_are_safe(self):
        for error_type, expected in ((httpx.ReadTimeout, 504), (httpx.ConnectTimeout, 504), (httpx.ConnectError, 502)):
            with self.subTest(error_type=error_type):
                def upstream(request, error=error_type):
                    raise error(PRIVATE_DETAIL + TOKEN, request=request)

                client = self.make_client(upstream)
                self.assert_safe_error(client.get(STREAM_PATH, params={"source": SOURCE}), expected)

    def test_failure_during_playback_closes_stream_and_redacts_exception(self):
        class BrokenStream(TrackedStream):
            async def __aiter__(self):
                yield b"first-video-chunk"
                raise httpx.ReadError(PRIVATE_DETAIL + " " + TOKEN)

        stream = BrokenStream(())
        client = self.make_client(lambda request: httpx.Response(
            200, headers={"Content-Type": "video/mp4"}, stream=stream,
        ))
        # Once media bytes start, HTTP cannot switch to a JSON error response.
        with self.assertRaisesRegex(RuntimeError, "video stream was interrupted") as caught:
            client.get(STREAM_PATH, params={"source": SOURCE})
        self.assertTrue(stream.closed)
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertNotIn(PRIVATE_DETAIL, str(caught.exception))


class VideoDisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_disconnect_closes_incomplete_upstream_stream(self):
        stream = TrackedStream((b"first-video-chunk",), stall=True)

        def upstream(request):
            if request.url.path.endswith("/auth/login"):
                return httpx.Response(200, json={"access_token": TOKEN})
            if request.url.path.endswith("/search"):
                return httpx.Response(200, json={"results": [{"source": SOURCE}]})
            return httpx.Response(200, headers={"Content-Type": "video/mp4"}, stream=stream)

        app = create_app(BACKEND, username=USERNAME, password=PASSWORD, transport=httpx.MockTransport(upstream))
        first_body = asyncio.Event()
        request_sent = False
        messages = []

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await first_body.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                first_body.set()

        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1", "method": "GET", "scheme": "http", "path": STREAM_PATH,
            "raw_path": STREAM_PATH.encode(), "query_string": urlencode({"source": SOURCE}).encode(),
            "root_path": "", "headers": [], "server": ("testserver", 80), "client": ("127.0.0.1", 1234),
        }
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                response = await client.post("/api/v1/search", json={"query": "forklift"})
                self.assertEqual(response.status_code, 200)
            await asyncio.wait_for(app(scope, receive, send), timeout=2)
        self.assertTrue(first_body.is_set())
        self.assertEqual(messages[0]["status"], 200)
        self.assertTrue(stream.closed)


if __name__ == "__main__":
    unittest.main()
