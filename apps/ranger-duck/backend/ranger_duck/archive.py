"""Authenticated client for the independent archive; secrets stay server-side."""
import asyncio
import logging

import httpx

from .capture import Capture
from .errors import DemoError, timeout_error, upstream_error
from .stream import close_stream

for name in ('httpx', 'httpcore'):
    logging.getLogger(name).setLevel(logging.WARNING)


def animal_search_scope(animal):
    if animal == 'cat':
        return {'tags': ['meow-10k', 'cat-behavior'],
                'requested_dataset_id': 'hf-smgjch-meow-10k', 'dataset_filter_applied': False}
    return {'tags': ['wildlife']}


class ArchiveClient:
    def __init__(self, settings, transport=None, capture=None):
        self.settings = settings
        self.capture = capture or Capture()
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout_sec),
                                     follow_redirects=False, transport=transport, trust_env=False)

    async def close(self):
        await self.http.aclose()

    def _require_config(self):
        if not self.settings.configured:
            raise DemoError('live_not_configured', 'Search requires ARCHIVE_URL and ARCHIVE_API_KEY on the backend.', 503)

    async def _request(self, method, path, *, stream=False, **kwargs):
        self._require_config()
        headers = {**kwargs.pop('headers', {}), 'Authorization': 'Bearer ' + self.settings.api_key}
        request = self.http.build_request(method, self.settings.archive_url + '/api/v1' + path, headers=headers, **kwargs)
        request.headers.pop('cookie', None)
        return await self.http.send(request, stream=stream)

    async def search(self, query, tags=None, *, top_k=15):
        payload = {'query': query, 'tags': ['wildlife'] if tags is None else tags, 'top_k': top_k}
        return await self.capture.call('archive.search', payload, lambda: self._search(payload))

    async def _search(self, payload):
        try:
            async with asyncio.timeout(self.settings.search_timeout_sec):
                response = await self._request('POST', '/search', json=payload,
                    timeout=httpx.Timeout(self.settings.request_timeout_sec, read=self.settings.search_timeout_sec))
                if response.status_code == 503:
                    error = response.json()
                    if isinstance(error, dict) and error.get('detail') == 'search_limit_reached':
                        raise DemoError('search_limit_reached', 'Search could not finish validating matches. Archive index maintenance is required before retrying.', 503, retryable=False)
                if response.status_code != 200:
                    raise upstream_error()
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get('results'), list):
                    raise upstream_error()
                return data
        except (TimeoutError, httpx.TimeoutException):
            raise timeout_error() from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise upstream_error() from None

    async def video(self, source, method, range_header, if_range=None):
        headers = {'Accept-Encoding': 'identity'}
        if range_header:
            headers['Range'] = range_header
        if if_range:
            headers['If-Range'] = if_range
        try:
            async with asyncio.timeout(self.settings.search_timeout_sec):
                response = await self._request(method, '/videos/stream', stream=True, params={'source': source}, headers=headers)
                if response.status_code not in {200, 206, 416}:
                    await close_stream(response)
                    raise upstream_error()
                return response
        except (TimeoutError, httpx.TimeoutException):
            raise timeout_error() from None
        except (httpx.HTTPError, ValueError):
            raise upstream_error() from None
