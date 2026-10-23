import base64

import pytest
from fastapi.testclient import TestClient

from video_archive.local_cosmos import create_app


def payload():
    return {'model': 'pinned-model', 'temperature': 0, 'max_tokens': 128,
            'mm_processor_kwargs': {'fps': 4, 'do_sample_frames': True},
            'messages': [{'role': 'user', 'content': [
                {'type': 'video_url', 'video_url': {'url': 'data:video/mp4;base64,' + base64.b64encode(b'video').decode()}},
                {'type': 'text', 'text': 'Describe the visible motion.'}]}]}


def test_caption_contract_and_truncation():
    calls = []

    def reasoner(*args):
        calls.append(args)
        return 'Fixture caption', 'length'

    client = TestClient(create_app('pinned-model', 'revision', reasoner))
    response = client.post('/v1/chat/completions', json=payload())
    assert response.status_code == 200
    assert response.json()['choices'][0]['finish_reason'] == 'length'
    assert calls == [(b'video', 'Describe the visible motion.', 128)]
    assert client.get('/v1/models').json()['data'][0]['revision'] == 'revision'


@pytest.mark.parametrize('url', ['https://example.org/video.mp4', 'file:///private/video.mp4',
                              'data:video/mp4;base64,!', 'data:video/mp4;base64,'])
def test_rejects_noninline_or_invalid_video_before_inference(url):
    client = TestClient(create_app('pinned-model', 'revision', lambda *_: pytest.fail('must not infer')))
    body = payload()
    body['messages'][0]['content'][0]['video_url']['url'] = url
    assert client.post('/v1/chat/completions', json=body).status_code == 400


def test_requires_model_and_sampling_match():
    client = TestClient(create_app('pinned-model', 'revision', lambda *_: pytest.fail('must not infer')))
    body = payload()
    body['model'] = 'other-model'
    assert client.post('/v1/chat/completions', json=body).status_code == 400
    body = payload()
    body['mm_processor_kwargs']['fps'] = 1
    assert client.post('/v1/chat/completions', json=body).status_code == 400


def test_inference_failure_is_private_and_releases_lock():
    def reasoner(*_):
        raise RuntimeError('private upstream diagnostics')

    client = TestClient(create_app('pinned-model', 'revision', reasoner))
    for _ in range(2):
        response = client.post('/v1/chat/completions', json=payload())
        assert response.status_code == 503
        assert response.json() == {'detail': 'Local Cosmos inference failed'}
