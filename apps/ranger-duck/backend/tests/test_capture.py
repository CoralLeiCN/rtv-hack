import asyncio
from dataclasses import replace
import json
import stat
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from ranger_duck.app import create_app
from ranger_duck.capture import Capture, export_pending
from ranger_duck.evidence import Manifest
from ranger_duck.errors import DemoError
from ranger_duck.loop_agent import CodexAgent, QueryDecision
from test_backend import SETTINGS, PAYLOAD, ROW, Upstream, EncounterAgent
from test_loop import Agent, start, next_cycle, outcome, row


def events(directory):
    return [json.loads(line) for path in directory.glob('*.jsonl') for line in path.read_text().splitlines()]


def test_full_search_and_decisions_survive_filters_and_link_to_outcome(tmp_path):
    rows = [row(), {'source': None, 'reasoning_content': 'invalid but preserved'}, row()]
    app = create_app(replace(SETTINGS, capture_dir=tmp_path), httpx.MockTransport(Upstream(rows)), Manifest(), Agent())
    with TestClient(app) as client:
        start(client)
        cycle = next_cycle(client).json()
        assert client.post('/demo-api/loop/loop-1/outcome', json=outcome(cycle)).status_code == 200
    captured = events(tmp_path)
    searches = [e for e in captured if e['kind'] == 'archive.search.completed']
    assert searches[0]['output']['results'] == rows
    decisions = [e for e in captured if e['kind'] == 'codex.decision.completed']
    assert len(decisions) == 2
    assert decisions[1]['output']['reason'] == 'Approximate this observed active motion.'
    assert len(decisions[1]['inputs']['context']['candidates']) == 3
    result = next(e for e in captured if e['kind'] == 'loop.action.outcome')
    assert result['output']['status'] == 'completed'
    assert {e['run_id'] for e in captured} == {result['run_id']}
    assert result['run_id']
    data = next(tmp_path.glob('*.jsonl')).read_text()
    assert 'test-secret' not in data and 'test-token' not in data
    assert stat.S_IMODE(next(tmp_path.glob('*.jsonl')).stat().st_mode) == 0o600


def test_cancelled_issued_action_has_unknown_outcome(tmp_path):
    app = create_app(replace(SETTINGS, capture_dir=tmp_path), httpx.MockTransport(Upstream([row()])), Manifest(), Agent())
    with TestClient(app) as client:
        start(client)
        assert next_cycle(client).status_code == 200
        client.post('/demo-api/loop/loop-1/pause')
    captured = events(tmp_path)
    assert next(e for e in captured if e['kind'] == 'loop.action.interrupted')['output'] == {'status': 'unknown'}
    assert not any(e['kind'] == 'loop.action.outcome' for e in captured)


def test_encounter_outcomes_require_session_and_issued_action(tmp_path):
    app = create_app(replace(SETTINGS, capture_dir=tmp_path), httpx.MockTransport(Upstream()), Manifest(), EncounterAgent())
    with TestClient(app) as client:
        response = client.post('/demo-api/search', json=PAYLOAD).json()
        candidate = response['candidates'][0]
        payload = {'clip_id': candidate['clip_id'], 'search_id': response['search_id'], 'execution_id': 'execution-1',
                   'cycle': 1, 'primitive': candidate['action']['primitive'], 'status': 'completed',
                   'state': {'status': 'complete', 'position': [0., 0., 0.], 'head_yaw': 0., 'simulation_time': 1.}}
        assert client.post('/demo-api/action-outcome', json={**payload, 'primitive': 'sit_cycle'}).status_code == 409
        assert client.post('/demo-api/action-outcome', json={**payload, 'state': None}).status_code == 422
        assert client.post('/demo-api/action-outcome', json=payload).json()['status'] == 'recorded'
        client.cookies.clear()
        assert client.post('/demo-api/action-outcome', json=payload).status_code == 404
    captured = events(tmp_path)
    result = next(e for e in captured if e['kind'] == 'encounter.action.completed')
    assert result['run_id'] == next(e for e in captured if e['kind'] == 'archive.search.completed')['run_id']
    assert len([e for e in captured if e['kind'] == 'encounter.action.completed']) == 1


def test_redaction_does_not_mutate_sources_or_truncate_results(tmp_path):
    capture = Capture(tmp_path, ('private-password',))
    data = {'results': [{'source': 's3://archive/clip.mp4', 'caption': 'x' * 20000,
                        'url': 'https://user:pass@example.invalid/clip.mp4?token=signature#fragment',
                        'nested': {'access_token': 'secret-token'}, 'text': 'private-password Bearer bearer-secret'}] * 25}
    capture.emit('test', output=data)
    saved = events(tmp_path)[0]['output']
    assert len(saved['results']) == 25
    assert saved['results'][0]['caption'] == 'x' * 20000
    assert saved['results'][0]['source'] == 's3://archive/clip.mp4'
    assert saved['results'][0]['url'] == 'https://example.invalid/clip.mp4'
    assert saved['results'][0]['nested']['access_token'] == '[redacted]'
    assert data['results'][0]['nested']['access_token'] == 'secret-token'


def test_failure_and_concurrent_runs_remain_separate(tmp_path):
    capture = Capture(tmp_path)
    async def run(identity, fail):
        with capture.scope(identity):
            async def operation():
                await asyncio.sleep(0)
                if fail:
                    raise ValueError('private-error-secret')
                return {'ok': True}
            try:
                await capture.call('test', {'identity': identity}, operation)
            except ValueError:
                pass
    async def together():
        await asyncio.gather(run('one', False), run('two', True))
    asyncio.run(together())
    captured = events(tmp_path)
    assert all(e['run_id'] == e['inputs']['identity'] for e in captured)
    assert next(e for e in captured if e['kind'] == 'test.failed')['attributes']['error_type'] == 'ValueError'
    assert 'private-error-secret' not in next(tmp_path.glob('*.jsonl')).read_text()


def test_storage_failure_is_visible_without_losing_app_result(tmp_path):
    path = tmp_path / 'file'
    path.write_text('not a directory')
    capture = Capture(path)
    capture.emit('test')
    assert capture.failed


def test_raw_codex_output_is_retained_even_when_schema_validation_fails(tmp_path, monkeypatch):
    capture = Capture(tmp_path)
    agent = CodexAgent(capture)
    agent.executable = '/fake/codex'
    async def fake_process(*args, **kwargs):
        from pathlib import Path
        output = Path(args[args.index('--output-last-message') + 1])
        async def communicate(data):
            output.write_text('{"reason":"Returned explanation, but missing required fields"}')
        return SimpleNamespace(communicate=communicate, returncode=0)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_process)
    with pytest.raises(DemoError):
        asyncio.run(agent.decide({'animal': 'deer'}, QueryDecision))
    captured = events(tmp_path)
    assert captured[0]['inputs']['context'] == {'animal': 'deer'}
    assert captured[0]['inputs']['instructions']
    assert 'Returned explanation' in next(e for e in captured if e['kind'] == 'codex.output')['output']


def test_weave_export_preserves_full_payload_and_join_keys(tmp_path, monkeypatch):
    capture = Capture(tmp_path)
    capture.emit('archive.search.completed', {'query': 'deer'}, {'results': [ROW]}, run_id='run-1')
    calls = []
    def log_call(**kw):
        calls.append(kw)
        return SimpleNamespace(id='remote-call')
    weave = SimpleNamespace(log_call=log_call)
    client = SimpleNamespace(flush=lambda: None, get_call=lambda id: SimpleNamespace(attributes=calls[-1]['attributes']))
    assert export_pending(tmp_path, 'team/project', weave, client) == 1
    assert export_pending(tmp_path, 'team/project', weave, client) == 0
    assert calls[0]['output']['results'] == [ROW]
    assert calls[0]['attributes']['run_id'] == 'run-1'
    assert calls[0]['attributes']['event_id'] == events(tmp_path)[0]['event_id']


def test_unconfirmed_export_is_retried(tmp_path):
    Capture(tmp_path).emit('test', output={'ok': True})
    calls = []
    def log_call(**kw):
        calls.append(kw)
        return SimpleNamespace(id='remote-call')
    client = SimpleNamespace(flush=lambda: None, get_call=lambda id: SimpleNamespace(attributes={}))
    for _ in range(2):
        with pytest.raises(RuntimeError):
            export_pending(tmp_path, 'team/project', SimpleNamespace(log_call=log_call), client)
    assert len(calls) == 2
    assert not list(tmp_path.glob('*.acks'))


def test_follow_retries_initial_connection_failure(tmp_path, monkeypatch):
    import sys
    from ranger_duck import capture
    settings = tmp_path / '.env'
    settings.write_text('RANGER_WEAVE_PROJECT=team/project\nWANDB_API_KEY=test-key\n')
    monkeypatch.setenv('RANGER_ENV_FILE', str(settings))
    monkeypatch.setenv('WANDB_API_KEY', '')
    monkeypatch.delenv('WANDB_API_KEY')
    monkeypatch.setattr(sys, 'argv', ['export-captures', '--follow', '--directory', str(tmp_path)])
    attempts, exports, finishes = [], [], []

    def init(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise ConnectionError('offline')
        return object()

    def sleep(seconds):
        if len(attempts) == 2:
            raise KeyboardInterrupt

    monkeypatch.setitem(sys.modules, 'weave', SimpleNamespace(init=init, finish=lambda: finishes.append(True)))
    monkeypatch.setattr(capture, 'export_pending', lambda *args: exports.append(True) or 0)
    monkeypatch.setattr(capture.time, 'sleep', sleep)
    capture.main()
    assert len(attempts) == 2
    assert exports == finishes == [True]


@pytest.mark.parametrize('adaptive', [False, True])
@pytest.mark.parametrize('status', ['completed', 'failed', 'cancelled'])
def test_unified_run_captures_search_decisions_and_one_validated_outcome(tmp_path, adaptive, status):
    from test_runs import RunAgent, rows, start as start_run, search as search_run, report
    clips = rows()
    app = create_app(replace(SETTINGS, capture_dir=tmp_path),
                     httpx.MockTransport(Upstream(clips)), Manifest(), RunAgent())
    with TestClient(app) as client:
        start_run(client, adaptive)
        result = search_run(client)
        body = report(result, result)
        if status != 'completed':
            body.update(status=status, playback=status)
            body['state']['status'] = 'ready'
            body['companion']['status'] = status
        invalid = {**body, 'attempt_id': 'not-issued'}
        assert client.post('/demo-api/runs/run-1/outcome', json=invalid).status_code == 409
        first = client.post('/demo-api/runs/run-1/outcome', json=body)
        assert first.status_code == 200
        assert client.post('/demo-api/runs/run-1/outcome', json=body).json() == first.json()
    captured = events(tmp_path)
    assert next(e for e in captured if e['kind'] == 'archive.search.completed')['output']['results'] == clips
    assert len([e for e in captured if e['kind'] == 'codex.decision.completed']) == 2
    assert next(e for e in captured if e['kind'] == 'run.search.result')['output'] == result
    outcomes = [e for e in captured if e['kind'] == 'run.action.outcome']
    assert len(outcomes) == 1 and outcomes[0]['output'] == body
    assert outcomes[0]['attributes']['outcome_source'] == 'browser_report'
    issued = next(e for e in captured if e['kind'] == 'run.action.issued')
    assert issued['inputs']['attempt_id'] == body['attempt_id']
    assert {e['run_id'] for e in captured} == {outcomes[0]['run_id']}
    assert outcomes[0]['run_id']


def test_unified_pause_records_unknown_and_replay_outcomes_are_labelled(tmp_path):
    from test_runs import RunAgent, rows, start as start_run, search as search_run, report
    app = create_app(replace(SETTINGS, capture_dir=tmp_path),
                     httpx.MockTransport(Upstream(rows())), Manifest(), RunAgent())
    with TestClient(app) as client:
        start_run(client)
        result = search_run(client)
        assert client.post('/demo-api/runs/run-1/pause').status_code == 200
        assert client.post('/demo-api/runs/run-1/pause').status_code == 200
        replay = client.post('/demo-api/runs/run-1/replay').json()
        body = report(replay, replay)
        assert client.post('/demo-api/runs/run-1/outcome', json=body).status_code == 200
    captured = events(tmp_path)
    interrupted = [e for e in captured if e['kind'] == 'run.action.interrupted']
    assert len(interrupted) == 1
    assert interrupted[0]['inputs']['attempt_id'] == result['execution']['attempt_id']
    assert interrupted[0]['output'] == {'status': 'unknown'}
    outcomes = [e for e in captured if e['kind'] == 'run.action.outcome']
    assert len(outcomes) == 1 and outcomes[0]['inputs']['origin'] == 'replay'


def test_unified_run_does_not_issue_an_action_when_capture_storage_fails(tmp_path):
    from test_runs import RunAgent, rows, start as start_run, plan
    blocked = tmp_path / 'file'
    blocked.write_text('not a directory')
    app = create_app(replace(SETTINGS, capture_dir=blocked),
                     httpx.MockTransport(Upstream(rows())), Manifest(), RunAgent())
    with TestClient(app) as client:
        start_run(client)
        planned = plan(client)
        response = client.post('/demo-api/runs/run-1/search', json={'plan_id': planned['plan_id']})
        assert response.status_code == 503
        run = next(iter(app.state.run_service.runs.values()))
        assert run.pending is None and run.phase == 'paused'
