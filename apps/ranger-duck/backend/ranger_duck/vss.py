"""Read-only VSS client. Never log upstream URLs, bodies, tokens, or exceptions."""
import asyncio
import logging

import httpx

from .config import Settings
from .errors import DemoError, timeout_error, upstream_error
from .stream import close_stream

# httpx INFO logs include the playback query token. Keep these libraries quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class VSSClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_sec),
            follow_redirects=False, transport=transport, trust_env=False,
        )
        self._token: str | None = None
        self._auth_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.http.aclose()

    def _url(self, path: str) -> str:
        return self.settings.ingress_url.rstrip("/") + "/api/v1" + path

    async def _request(self, method: str, path: str, *, stream: bool = False, **kwargs) -> httpx.Response:
        request = self.http.build_request(method, self._url(path), **kwargs)
        # Like server.py, use per-request JWTs rather than pooled upstream cookies.
        request.headers.pop("cookie", None)
        return await self.http.send(request, stream=stream)

    def _require_config(self) -> None:
        if not self.settings.configured:
            raise DemoError("live_not_configured", "Live search requires INGRESS_URL, USERNAME, and PASSWORD on the backend.", 503)

    async def _token_for(self, failed_token: str | None = None) -> str:
        self._require_config()
        async with self._auth_lock:
            if self._token and self._token != failed_token:
                return self._token
            self._token = None
            response = await self._request("POST", "/auth/login", json={
                "username": self.settings.username, "password": self.settings.password,
            })
            if response.status_code != 200:
                raise upstream_error()
            try:
                token = response.json()["access_token"]
                if not isinstance(token, str) or not token or len(token) > 16384 or any(c.isspace() for c in token):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise upstream_error() from None
            verified = await self._request("GET", "/auth/me", headers={"Authorization": f"Bearer {token}"})
            if verified.status_code != 200:
                raise upstream_error()
            self._token = token
            return token

    async def search(self, query: str) -> dict:
        self._require_config()
        try:
            async with asyncio.timeout(self.settings.search_timeout_sec):
                token = await self._token_for()
                for attempt in range(2):
                    response = await self._request("POST", "/search", headers={"Authorization": f"Bearer {token}"}, json={
                        "query": query, "tags": ["wildlife"], "top_k": 15,
                        "llm_top_n": 1, "min_similarity": 0.3,
                        "include_public": True,
                    })
                    if response.status_code == 401 and attempt == 0:
                        token = await self._token_for(failed_token=token)
                        continue
                    if response.status_code == 401 and self._token == token:
                        self._token = None
                    if response.status_code != 200:
                        raise upstream_error()
                    data = response.json()
                    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                        raise upstream_error()
                    return data
        except (TimeoutError, httpx.TimeoutException):
            raise timeout_error() from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise upstream_error() from None
        raise upstream_error()

    async def video(self, source: str, method: str, range_header: str | None, if_range: str | None = None) -> httpx.Response:
        """Open only the fixed VSS stream endpoint; never follow a redirect."""
        self._require_config()
        try:
            async with asyncio.timeout(self.settings.search_timeout_sec):
                token = await self._token_for()
                headers = {"Accept-Encoding": "identity"}
                if range_header:
                    headers["Range"] = range_header
                if if_range:
                    headers["If-Range"] = if_range
                for attempt in range(2):
                    response = await self._request(method, "/videos/stream", stream=True,
                        params={"source": source, "token": token}, headers=headers)
                    # Some VSS deployments expose GET only. Do not download the body.
                    if method == "HEAD" and response.status_code == 405:
                        await close_stream(response)
                        response = await self._request("GET", "/videos/stream", stream=True,
                            params={"source": source, "token": token}, headers=headers)
                    if response.status_code == 401 and attempt == 0:
                        await close_stream(response)
                        token = await self._token_for(failed_token=token)
                        continue
                    if response.status_code == 401 and self._token == token:
                        self._token = None
                    if response.status_code not in {200, 206, 416}:
                        await close_stream(response)
                        raise upstream_error()
                    return response
        except (TimeoutError, httpx.TimeoutException):
            raise timeout_error() from None
        except (httpx.HTTPError, ValueError):
            raise upstream_error() from None
        raise upstream_error()
