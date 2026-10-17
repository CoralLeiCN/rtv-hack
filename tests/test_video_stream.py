"""Verify the simple UI's playback allowlist, seeking and stream cleanup."""
import asyncio

from fastapi.testclient import TestClient
import httpx
import pytest

from server import create_app, VideoStreamResponse
from test_server import BASE, KEY, SOURCE


class TrackedStream(httpx.AsyncByteStream):
    closed = False
    read = False

    async def __aiter__(self):
        self.read = True
        yield b'abcdef'

    async def aclose(self):
        self.closed = True


def setup(status=200, headers=None):
    requests, streams = [], []
    def handler(request):
        requests.append(request)
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'results': [{'source': SOURCE}]})
        stream = TrackedStream()
        streams.append(stream)
        return httpx.Response(status, stream=stream, headers=headers or {
            'content-type': 'video/mp4', 'content-length': '6', 'accept-ranges': 'bytes',
            'set-cookie': 'private=x', 'x-secret': KEY})
    return TestClient(create_app(BASE, httpx.MockTransport(handler), KEY)), requests, streams


def test_full_video_auth_allowlist_and_cleanup():
    client, requests, streams = setup()
    with client:
        assert client.get('/api/v1/videos/stream', params={'source': SOURCE}).status_code == 403
        assert not requests
        client.post('/api/v1/search', json={'query': 'deer'})
        response = client.get('/api/v1/videos/stream', params={'source': SOURCE}, headers={'Authorization': 'Bearer browser'})
        assert response.content == b'abcdef'
        assert 'set-cookie' not in response.headers and 'x-secret' not in response.headers
        assert KEY not in str(response.headers)
        assert streams[-1].closed
        media = requests[-1]
        assert dict(media.url.params) == {'source': SOURCE}
        assert media.headers['authorization'] == 'Bearer ' + KEY
        assert 'cookie' not in media.headers
        assert client.get('/api/v1/videos/stream', params={'source': 'file:///etc/passwd'}).status_code == 403


@pytest.mark.parametrize('method,status', [('GET', 206), ('HEAD', 200), ('GET', 416)])
def test_ranges_head_and_unsatisfiable_response(method, status):
    headers = {'content-type': 'video/mp4', 'content-length': '6', 'accept-ranges': 'bytes',
               'content-range': 'bytes */6' if status == 416 else 'bytes 1-6/10', 'etag': '"example"'}
    client, requests, streams = setup(status, headers)
    with client:
        client.post('/api/v1/search', json={'query': 'deer'})
        response = client.request(method, '/api/v1/videos/stream', params={'source': SOURCE},
                                  headers={'Range': 'bytes=1-6', 'If-Range': '"example"'})
        assert response.status_code == status
        assert response.headers['content-range'] == headers['content-range']
        assert response.headers['etag'] == '"example"'
        assert requests[-1].headers['if-range'] == '"example"'
        assert streams[-1].closed
        if method == 'HEAD' or status == 416:
            assert not streams[-1].read and response.content == b''


@pytest.mark.parametrize('status,mime', [(302, 'video/mp4'), (401, 'video/mp4'), (500, 'video/mp4'), (200, 'text/html')])
def test_invalid_video_response_is_closed_and_redacted(status, mime):
    client, _, streams = setup(status, {'content-type': mime, 'location': BASE + KEY})
    with client:
        client.post('/api/v1/search', json={'query': 'deer'})
        response = client.get('/api/v1/videos/stream', params={'source': SOURCE})
        assert response.status_code == 502 and KEY not in response.text
        assert 'location' not in response.headers and streams[-1].closed


def test_multiple_ranges_rejected_before_contacting_archive():
    client, requests, _ = setup()
    with client:
        client.post('/api/v1/search', json={'query': 'deer'})
        before = len(requests)
        assert client.get('/api/v1/videos/stream', params={'source': SOURCE}, headers={'Range': 'bytes=0-1,4-5'}).status_code == 416
        assert len(requests) == before


def test_disconnect_before_body_still_closes_stream():
    async def run():
        stream = TrackedStream()
        response = VideoStreamResponse(httpx.Response(200, stream=stream), {})
        async def send(message):
            raise RuntimeError('Disconnected')
        async def receive():
            await asyncio.Event().wait()
        with pytest.raises(RuntimeError):
            await response({'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, send)
        assert stream.closed
    asyncio.run(run())
