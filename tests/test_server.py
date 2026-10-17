"""Exercise the FastAPI boundary using synthetic upstream responses only."""

import asyncio
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx

from server import create_app


BACKEND = "https://private-vss.example/team-prefix"
USERNAME = "synthetic-workshop-user"
PASSWORD = "synthetic-password-private-marker"
TOKEN = "synthetic-session-private-marker"
PRIVATE_DETAIL = "synthetic-upstream-private-diagnostic"


def login_response():
    return httpx.Response(200, json={
        "access_token": TOKEN,
        "password": PASSWORD,
        "internal_debug": PRIVATE_DETAIL,
    })


class ServerTests(unittest.TestCase):
    def make_client(self, handler=None, backend=BACKEND, username=USERNAME, password=PASSWORD):
        self.requests = []

        def record(request):
            self.requests.append(request)
            if handler is not None:
                return handler(request)
            if request.url.path.endswith("/auth/login"):
                return login_response()
            return httpx.Response(200, json={"results": []})

        app = create_app(backend, transport=httpx.MockTransport(record), username=username, password=password)
        return self.enterContext(TestClient(app))

    def assert_safe_error(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(set(response.json()), {"detail"})
        for private_value in (USERNAME, PASSWORD, TOKEN, PRIVATE_DETAIL, BACKEND):
            self.assertNotIn(private_value, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_search_logs_in_with_server_credentials_and_keeps_session_private(self):
        client = self.make_client()
        response = client.post("/api/v1/search", json={"query": "forklift"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": []})
        for private_value in (USERNAME, PASSWORD, TOKEN, PRIVATE_DETAIL):
            self.assertNotIn(private_value, response.text)
        self.assertEqual(len(self.requests), 2)
        login, search = self.requests
        self.assertEqual(str(login.url), BACKEND + "/api/v1/auth/login")
        self.assertEqual(login.method, "POST")
        self.assertEqual(json.loads(login.content), {"username": USERNAME, "password": PASSWORD})
        self.assertNotIn("authorization", login.headers)
        self.assertEqual(search.headers["authorization"], "Bearer " + TOKEN)

    def test_login_is_cached_and_browser_authorization_is_ignored(self):
        client = self.make_client()
        for authorization in (None, "Bearer browser-private-marker", "Basic browser-private-marker"):
            headers = {"Authorization": authorization} if authorization else {}
            response = client.post("/api/v1/search", json={"query": "forklift"}, headers=headers)
            self.assertEqual(response.status_code, 200)
        self.assertEqual([request.url.path for request in self.requests], [
            "/team-prefix/api/v1/auth/login",
            "/team-prefix/api/v1/search", "/team-prefix/api/v1/search", "/team-prefix/api/v1/search",
        ])
        self.assertEqual([request.headers.get("authorization") for request in self.requests],
                         [None, "Bearer " + TOKEN, "Bearer " + TOKEN, "Bearer " + TOKEN])
        self.assertNotIn("browser-private-marker", " ".join(str(request.headers) for request in self.requests))

    def test_browser_login_route_is_not_exposed(self):
        client = self.make_client()
        response = client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})
        self.assertIn(response.status_code, (404, 405))
        self.assertNotIn(PASSWORD, response.text)
        self.assertEqual(self.requests, [])

    def test_search_trims_query_preserves_order_and_uses_upstream_defaults(self):
        matches = [
            {"reasoning_content": "First ranked match", "fixture_start": 50},
            {"reasoning_content": "Second ranked match", "fixture_start": 0},
        ]

        def upstream(request):
            if request.url.path.endswith("/auth/login"):
                return login_response()
            return httpx.Response(200, json={
                "results": matches,
                "synthesis": PRIVATE_DETAIL,
                "sql": "SELECT private_fixture FROM internal_table",
            })

        client = self.make_client(upstream)
        response = client.post("/api/v1/search", json={"query": "  forklift near a person \n"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": matches})
        request = self.requests[1]
        self.assertEqual(str(request.url), BACKEND + "/api/v1/search")
        self.assertEqual(json.loads(request.content), {"query": "forklift near a person"})
        self.assertNotIn(PRIVATE_DETAIL, response.text)

    def test_search_rejects_invalid_input_without_echoing_or_calling_upstream(self):
        client = self.make_client()
        for payload in (
            {}, {"query": ""}, {"query": " \n\t "}, {"query": None}, {"query": 7},
            {"query": "forklift", "top_k": 20}, {"query": "forklift", "token": TOKEN},
            {"query": "forklift", "password": PASSWORD},
        ):
            with self.subTest(payload_keys=list(payload)):
                self.assert_safe_error(client.post("/api/v1/search", json=payload), 422)
        response = client.post(
            "/api/v1/search", content='{"password":"' + PASSWORD + '", invalid json',
            headers={"Content-Type": "application/json"},
        )
        self.assert_safe_error(response, 422)
        self.assertEqual(self.requests, [])

    def test_expired_token_is_refreshed_once_and_new_token_is_cached(self):
        tokens = iter((TOKEN, "synthetic-refreshed-session"))

        def upstream(request):
            if request.url.path.endswith("/auth/login"):
                return httpx.Response(200, json={"access_token": next(tokens)})
            if request.headers["authorization"] == "Bearer " + TOKEN:
                return httpx.Response(401, json={"detail": PRIVATE_DETAIL})
            return httpx.Response(200, json={"results": []})

        client = self.make_client(upstream)
        for _ in range(2):
            self.assertEqual(client.post("/api/v1/search", json={"query": "forklift"}).status_code, 200)
        self.assertEqual([request.headers.get("authorization") for request in self.requests], [
            None, "Bearer " + TOKEN, None, "Bearer synthetic-refreshed-session", "Bearer synthetic-refreshed-session",
        ])

    def test_repeated_token_rejection_is_bounded_and_next_request_logs_in_again(self):
        login_count = 0

        def upstream(request):
            nonlocal login_count
            if request.url.path.endswith("/auth/login"):
                login_count += 1
                return httpx.Response(200, json={"access_token": f"synthetic-session-{login_count}"})
            if login_count < 3:
                return httpx.Response(401, json={"detail": PRIVATE_DETAIL})
            return httpx.Response(200, json={"results": []})

        client = self.make_client(upstream)
        self.assert_safe_error(client.post("/api/v1/search", json={"query": "forklift"}), 503)
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(login_count, 2)
        self.assertEqual(client.post("/api/v1/search", json={"query": "forklift"}).status_code, 200)
        self.assertEqual(login_count, 3)
        self.assertEqual(len(self.requests), 6)

    def test_rejected_server_credentials_are_safe_configuration_errors(self):
        for status in (400, 401, 403, 422):
            with self.subTest(upstream_status=status):
                client = self.make_client(lambda request, code=status: httpx.Response(
                    code, json={"detail": PRIVATE_DETAIL, "password": PASSWORD, "token": TOKEN}))
                self.assert_safe_error(client.post("/api/v1/search", json={"query": "forklift"}), 503)
                self.assertEqual(len(self.requests), 1)
                self.assertTrue(self.requests[0].url.path.endswith("/auth/login"))

    def test_invalid_upstream_sessions_are_safe_errors(self):
        for payload in (None, [], {}, {"access_token": " "}, {"access_token": 12}):
            with self.subTest(payload=payload):
                client = self.make_client(lambda request, data=payload: httpx.Response(200, json=data))
                self.assert_safe_error(client.post("/api/v1/search", json={"query": "forklift"}), 502)
                self.assertEqual(len(self.requests), 1)

    def test_upstream_cookies_are_neither_reused_nor_exposed(self):
        def upstream(request):
            payload = {"access_token": TOKEN} if request.url.path.endswith("/auth/login") else {"results": []}
            return httpx.Response(200, json=payload, headers={
                "Set-Cookie": "upstream-session=private-fixture-cookie; Path=/; Secure; HttpOnly",
            })

        client = self.make_client(upstream)
        for _ in range(2):
            response = client.post("/api/v1/search", json={"query": "forklift"})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("set-cookie", response.headers)
        for request in self.requests:
            self.assertNotIn("cookie", request.headers)

    def test_upstream_search_http_errors_are_safe(self):
        for upstream_status, expected in ((400, 400), (403, 403), (422, 422), (429, 429), (500, 502), (503, 502)):
            with self.subTest(upstream_status=upstream_status):
                def upstream(request, status=upstream_status):
                    if request.url.path.endswith("/auth/login"):
                        return login_response()
                    return httpx.Response(status, json={"detail": PRIVATE_DETAIL, "password": PASSWORD, "token": TOKEN})

                client = self.make_client(upstream)
                self.assert_safe_error(client.post("/api/v1/search", json={"query": "forklift"}), expected)
                self.assertEqual(len(self.requests), 2)

    def test_upstream_timeouts_and_transport_errors_are_safe(self):
        for stage in ("auth/login", "search"):
            for error_type, expected in ((httpx.ReadTimeout, 504), (httpx.ConnectTimeout, 504), (httpx.ConnectError, 502)):
                with self.subTest(stage=stage, error_type=error_type):
                    def fail(request, error=error_type, failing_stage=stage):
                        if request.url.path.endswith("/" + failing_stage):
                            raise error(PRIVATE_DETAIL + PASSWORD, request=request)
                        return login_response()

                    client = self.make_client(fail)
                    self.assert_safe_error(client.post("/api/v1/search", json={"query": "forklift"}), expected)

    def test_upstream_redirects_are_not_followed(self):
        client = self.make_client(lambda request: httpx.Response(
            307, headers={"Location": "https://unrelated.example/collect"}, text=PRIVATE_DETAIL))
        response = client.post("/api/v1/search", json={"query": "forklift"})
        self.assert_safe_error(response, 502)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.host, "private-vss.example")
        self.assertNotIn("location", response.headers)

    def test_malformed_search_responses_are_safe_errors(self):
        responses = [
            httpx.Response(200, text=PRIVATE_DETAIL), httpx.Response(200, json=None),
            httpx.Response(200, json={"results": None}), httpx.Response(200, json={"results": {}}),
        ]
        for upstream_response in responses:
            with self.subTest(response_body=upstream_response.text):
                def upstream(request, response=upstream_response):
                    return login_response() if request.url.path.endswith("/auth/login") else response

                client = self.make_client(upstream)
                self.assert_safe_error(client.post("/api/v1/search", json={"query": "forklift"}), 502)

    def test_missing_configuration_fails_without_network_access(self):
        for config in ({"backend": ""}, {"username": ""}, {"password": ""}):
            with self.subTest(config=config):
                client = self.make_client(**config)
                self.assert_safe_error(client.post("/api/v1/search", json={"query": "forklift"}), 503)
                self.assertEqual(self.requests, [])

    def test_workshop_configuration_is_read_from_environment(self):
        with patch.dict(os.environ, {"INGRESS_URL": BACKEND + "/", "USERNAME": USERNAME, "PASSWORD": PASSWORD}):
            client = self.make_client(backend=None, username=None, password=None)
        self.assertEqual(client.post("/api/v1/search", json={"query": "forklift"}).status_code, 200)
        self.assertEqual(str(self.requests[0].url), BACKEND + "/api/v1/auth/login")
        self.assertEqual(json.loads(self.requests[0].content), {"username": USERNAME, "password": PASSWORD})

    def test_public_config_excludes_upstream_address_and_credentials(self):
        client = self.make_client()
        client.post("/api/v1/search", json={"query": "forklift"})
        with patch.dict(os.environ, {
            "INGRESS_URL": BACKEND, "USERNAME": USERNAME, "PASSWORD": PASSWORD,
            "VSS_RESULT_START_FIELD": "fixture_start", "VSS_RESULT_END_FIELD": "fixture_end",
            "VSS_RESULT_TIME_UNIT": "milliseconds",
        }):
            response = client.get("/config.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])
        prefix = "window.VSS_CONFIG = "
        self.assertTrue(response.text.startswith(prefix))
        config = json.loads(response.text[len(prefix):].strip().removesuffix(";"))
        self.assertEqual(config, {
            "apiBaseUrl": "",
            "resultTiming": {"startField": "fixture_start", "endField": "fixture_end", "unit": "milliseconds"},
        })
        for private_value in (USERNAME, PASSWORD, TOKEN, BACKEND):
            self.assertNotIn(private_value, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_static_routes_serve_frontend_without_exposing_repository_files(self):
        client = self.make_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<h1>Video search</h1>", response.text)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(client.get("/app.js").status_code, 200)
        for path in ("/server.py", "/requirements.txt", "/docs/spec.md", "/AGENTS.md",
                     "/%2e%2e/AGENTS.md", "/%2e%2e%2fAGENTS.md", "/docs", "/openapi.json"):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 404)
        self.assertEqual(self.requests, [])


class ConcurrentSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_and_search_share_one_overall_timeout(self):
        calls = []

        async def upstream(request):
            calls.append(request.url.path)
            # Each individual call fits the budget; their combined delay does not.
            await asyncio.sleep(0.03)
            if request.url.path.endswith("/auth/login"):
                return login_response()
            return httpx.Response(200, json={"results": []})

        app = create_app(BACKEND, transport=httpx.MockTransport(upstream), username=USERNAME, password=PASSWORD)
        with patch("server.REQUEST_TIMEOUT_SECONDS", 0.05):
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                    response = await client.post("/api/v1/search", json={"query": "forklift"})
        self.assertEqual(response.status_code, 504)
        self.assertEqual(set(response.json()), {"detail"})
        self.assertEqual(calls, ["/team-prefix/api/v1/auth/login", "/team-prefix/api/v1/search"])
        for private_value in (USERNAME, PASSWORD, TOKEN, PRIVATE_DETAIL, BACKEND):
            self.assertNotIn(private_value, response.text)

    async def test_concurrent_searches_share_initial_login_and_expired_token_refresh(self):
        login_count = 0
        search_tokens = []
        rejected_tokens = set()
        arrivals = 0
        all_arrived = asyncio.Event()

        async def upstream(request):
            nonlocal login_count, arrivals
            if request.url.path.endswith("/auth/login"):
                login_count += 1
                await asyncio.sleep(0.01)
                return httpx.Response(200, json={"access_token": f"synthetic-token-{login_count}"})
            token = request.headers["authorization"]
            search_tokens.append(token)
            if token in rejected_tokens:
                arrivals += 1
                if arrivals == 4:
                    all_arrived.set()
                await asyncio.wait_for(all_arrived.wait(), timeout=2)
                return httpx.Response(401, json={"detail": PRIVATE_DETAIL})
            return httpx.Response(200, json={"results": []})

        app = create_app(BACKEND, transport=httpx.MockTransport(upstream), username=USERNAME, password=PASSWORD)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                async def search_together():
                    responses = await asyncio.gather(*(
                        client.post("/api/v1/search", json={"query": "forklift"}) for _ in range(4)
                    ))
                    self.assertEqual([response.status_code for response in responses], [200] * 4)

                await search_together()
                self.assertEqual(login_count, 1)
                self.assertEqual(search_tokens, ["Bearer synthetic-token-1"] * 4)
                search_tokens.clear()
                rejected_tokens.add("Bearer synthetic-token-1")
                await search_together()
                self.assertEqual(login_count, 2)
                self.assertEqual(search_tokens.count("Bearer synthetic-token-1"), 4)
                self.assertEqual(search_tokens.count("Bearer synthetic-token-2"), 4)


if __name__ == "__main__":
    unittest.main()
