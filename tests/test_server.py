"""Simple search adapter contracts against a fabricated independent archive."""
import json

from fastapi.testclient import TestClient
import httpx
import pytest

from server import create_app

BASE = 'https://archive.invalid'
KEY = 'private-archive-key'
SOURCE = 'media://7e1404b8-e5cc-4d92-a09a-bf6815c2a209'


def test_server_auth_preserves_order_and_never_forwards_browser_credentials():
    requests = []
    rows = [{'source': SOURCE, 'reasoning_content': 'A deer walks.'}, {'reasoning_content': 'A cat sits.'}]
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'results': rows, 'debug': KEY}, headers={'set-cookie': 'secret=x'})
    with TestClient(create_app(BASE, httpx.MockTransport(handler), KEY)) as client:
        for _ in range(2):
            response = client.post('/api/v1/search', json={'query': ' deer '}, headers={'Authorization': 'Bearer browser'})
            assert response.json() == {'results': rows}
            assert KEY not in response.text
            assert 'set-cookie' not in response.headers
            assert response.headers['cache-control'] == 'no-store'
        assert len(requests) == 2
        assert all(r.headers['authorization'] == 'Bearer ' + KEY and 'cookie' not in r.headers for r in requests)
        assert json.loads(requests[0].content) == {'query': 'deer', 'tags': [], 'top_k': 15}
        assert all(r.url.path == '/api/v1/search' for r in requests)


@pytest.mark.parametrize('payload', [{}, {'query': ''}, {'query': ' \n'}, {'query': 7}, {'query': 'deer', 'api_key': KEY}])
def test_invalid_input_never_contacts_archive(payload):
    def forbidden(request):
        pytest.fail('Unexpected network call')
    with TestClient(create_app(BASE, httpx.MockTransport(forbidden), KEY)) as client:
        response = client.post('/api/v1/search', json=payload)
        assert response.status_code == 422 and KEY not in response.text


@pytest.mark.parametrize('status', [301, 401, 403, 422, 429, 500])
def test_archive_failure_is_redacted_and_not_retried(status):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={'detail': KEY}, headers={'location': BASE + '/private'})
    with TestClient(create_app(BASE, httpx.MockTransport(handler), KEY)) as client:
        response = client.post('/api/v1/search', json={'query': 'deer'})
        assert response.status_code == 502 and KEY not in response.text
        assert len(requests) == 1 and 'location' not in response.headers


@pytest.mark.parametrize('data', [[], None, {}, {'results': {}}])
def test_malformed_archive_response_is_safe(data):
    with TestClient(create_app(BASE, httpx.MockTransport(lambda r: httpx.Response(200, json=data)), KEY)) as client:
        assert client.post('/api/v1/search', json={'query': 'deer'}).status_code == 502


@pytest.mark.parametrize('error,code', [(httpx.ReadTimeout, 504), (httpx.ConnectError, 502)])
def test_transport_errors_do_not_expose_url_or_key(error, code):
    def fail(request):
        raise error(BASE + KEY, request=request)
    with TestClient(create_app(BASE, httpx.MockTransport(fail), KEY)) as client:
        result = client.post('/api/v1/search', json={'query': 'deer'})
        assert result.status_code == code and KEY not in result.text


def test_config_and_static_files_do_not_expose_repository_or_secrets():
    with TestClient(create_app(BASE, api_key=KEY)) as client:
        assert client.get('/').status_code == 200
        config = client.get('/config.js').text
        assert 'segment_start_sec' in config and BASE not in config and KEY not in config
        for path in ('/.env', '/server.py', '/config.example', '/AGENTS.md'):
            assert client.get(path).status_code == 404
        assert client.post('/api/v1/auth/login', json={}).status_code in (404, 405)
    with TestClient(create_app('', api_key='')) as client:
        assert client.post('/api/v1/search', json={'query': 'deer'}).status_code == 503
