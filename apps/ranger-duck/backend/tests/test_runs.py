"""The unified page shares one pipeline and acknowledges real action attempts."""
import asyncio
import copy
import json

import httpx
import pytest

from ranger_duck.app import create_app
from ranger_duck.encounter_agent import EncounterActionsDecision, RunActionsDecision
from ranger_duck.evidence import Manifest
from test_backend import EncounterAgent, SETTINGS, ROW, Upstream, make_client, reviewed


class RunAgent(EncounterAgent):
    def __init__(self, mutate=None):
        super().__init__()
        self.mutate = mutate

    async def decide(self, context, schema):
        result = await super().decide(context, EncounterActionsDecision if schema is RunActionsDecision else schema)
        if schema is RunActionsDecision:
            data = result.model_dump()
            for action in data['actions']:
                action['role_plan'] = None
            if self.mutate:
                self.mutate(data)
            return RunActionsDecision.model_validate(data)
        return result


def rows():
    captions = ['A cat looks around.', 'A cat walks.', 'A cat feeds.', 'A cat stands still.',
                'A cat looks around and sits down.', 'A cat raises its head.']
    return [{**ROW, 'source': f's3://test-segments/run-{i}.mp4', 'segment_start_sec': i * 10,
             'segment_end_sec': i * 10 + 5, 'reasoning_content': caption} for i, caption in enumerate(captions)]


def setup(agent=None, clips=None, manifest=None):
    return make_client(Upstream(rows() if clips is None else clips), manifest=manifest, agent=agent or RunAgent())


def start(client, adaptive=False, run_id='run-1'):
    response = client.post('/demo-api/runs', json={'run_id': run_id, 'animal': 'cat', 'scenario_id': 'cat-greeting',
                                                   'intent': 'Meet the cat calmly', 'adaptive': adaptive})
    assert response.status_code == 200, response.text
    assert response.json()['execution'] is None
    return response.json()


def plan(client):
    response = client.post('/demo-api/runs/run-1/plan', json={})
    assert response.status_code == 200, response.text
    return response.json()


def search(client, planned=None):
    planned = planned or plan(client)
    response = client.post('/demo-api/runs/run-1/search', json={'plan_id': planned['plan_id']})
    assert response.status_code == 200, response.text
    return response.json()


def report(round_data, cursor):
    execution = cursor['execution']
    entry = next(entry for entry in round_data['queue'] if entry['action_id'] == execution['action_id'])
    return {'round_id': round_data['round_id'], **execution, 'primitive': entry['candidate']['action']['primitive'],
            'status': 'completed', 'playback': 'ended',
            'state': {'status': 'complete', 'position': [0., 0., .12], 'head_yaw': 0., 'simulation_time': 12.},
            'companion': {'behavior': entry['role_plan']['companion_behavior'], 'status': 'completed'}}


def outcome(client, body):
    response = client.post('/demo-api/runs/run-1/outcome', json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('adaptive', [False, True])
def test_both_toggle_states_share_two_agent_calls_one_search_and_ordered_active_queue(adaptive):
    client, upstream, app = setup()
    with client:
        initial = start(client, adaptive)
        assert initial['status'] == 'needs_plan' and initial['round'] == 0 and initial['pass'] == 1
        planned = plan(client)
        assert ' OR ' in planned['query'] and not upstream.requests
        result = search(client, planned)
        agent = app.state.encounter_service.agent.agent
        assert len(agent.calls) == 2
        assert [candidate['rank'] for candidate in agent.calls[1]['candidates']] == [2, 3, 5, 6]
        assert [entry['candidate']['rank'] for entry in result['queue']] == [2, 3, 5]
        assert result['queue'][2]['candidate']['action']['primitive'] == 'sit_cycle'
        assert all(entry['role_plan']['grounding'] == 'single_behavior' for entry in result['queue'])
        assert set(result['timings']) == {'query_agent_ms', 'vss_search_ms', 'action_agent_ms'}
        assert result['elapsed_ms'] == sum(result['timings'].values())
        requests = [json.loads(r.content) for r in upstream.requests if r.url.path.endswith('/search')]
        assert len(requests) == 1 and requests[0]['top_k'] == 15
        assert requests[0]['tags'] == ['meow-10k', 'cat-behavior']
        cursor = result
        for _ in result['queue']:
            cursor = outcome(client, report(result, cursor))
        assert cursor['status'] == ('needs_plan' if adaptive else 'ready')
        assert cursor['execution'] is None if adaptive else cursor['execution']['action_id'] == result['queue'][0]['action_id']
        assert len(agent.calls) == 2  # OFF repeats; ON waits for an explicit next plan request.
        if not adaptive:
            assert cursor['round_id'] == result['round_id'] and cursor['pass'] == 2


def test_adaptive_next_query_uses_only_actual_acknowledged_outcomes_and_original_intent():
    client, _, app = setup()
    with client:
        start(client, True)
        result = search(client)
        cursor = result
        for _ in result['queue']:
            cursor = outcome(client, report(result, cursor))
        plan(client)
        context = app.state.encounter_service.agent.agent.calls[-1]
        assert context['original_prompt'] == 'Meet the cat calmly'
        assert len(context['history']) == 3
        assert all(item['outcome']['state']['status'] == 'complete' for item in context['history'])
        assert 's3://' not in json.dumps(context) and 'test-secret' not in json.dumps(context)


def test_toggle_applies_at_queue_boundary_without_cancelling_or_replanning():
    client, _, app = setup()
    with client:
        start(client)
        result = search(client)
        first = outcome(client, report(result, result))
        toggled = client.post('/demo-api/runs/run-1/adaptive', json={'adaptive': True}).json()
        assert toggled['execution'] == first['execution']
        cursor = first
        for _ in range(2):
            cursor = outcome(client, report(result, cursor))
        assert cursor['status'] == 'needs_plan'
        assert len(app.state.encounter_service.agent.agent.calls) == 2


def test_pause_resume_preserves_completed_cursor_invalidates_attempt_and_outcome_is_idempotent():
    client, _, app = setup()
    with client:
        start(client)
        result = search(client)
        first_body = report(result, result)
        acknowledged = outcome(client, first_body)
        interrupted = report(result, acknowledged)
        for _ in range(2):
            assert client.post('/demo-api/runs/run-1/pause').json()['status'] == 'paused'
        assert client.post('/demo-api/runs/run-1/outcome', json=interrupted).status_code == 409
        resumed = client.post('/demo-api/runs/run-1/resume').json()
        assert resumed['execution']['action_id'] == acknowledged['execution']['action_id']
        assert resumed['execution']['attempt_id'] != acknowledged['execution']['attempt_id']
        assert outcome(client, first_body) == acknowledged
        changed = copy.deepcopy(first_body); changed['state']['position'][0] = .1
        assert client.post('/demo-api/runs/run-1/outcome', json=changed).status_code == 409
        assert len(app.state.encounter_service.agent.agent.calls) == 2
        assert len(next(iter(app.state.run_service.runs.values())).history) == 1


def test_paused_run_cannot_restart_from_late_plan_or_search_request():
    client, _, app = setup()
    with client:
        start(client)
        planned = plan(client)
        client.post('/demo-api/runs/run-1/pause')
        assert client.post('/demo-api/runs/run-1/plan', json={}).status_code == 409
        assert client.post('/demo-api/runs/run-1/search', json={'plan_id': planned['plan_id']}).status_code == 409
        assert len(app.state.encounter_service.agent.agent.calls) == 1
        assert client.post('/demo-api/runs/run-1/resume').json()['status'] == 'needs_plan'
        assert plan(client)['plan_id'] != planned['plan_id']


def test_replay_uses_saved_plan_and_fresh_attempts_without_live_history_or_inference():
    client, upstream, app = setup()
    with client:
        start(client, True)
        original = search(client)
        client.post('/demo-api/runs/run-1/pause')
        replay = client.post('/demo-api/runs/run-1/replay').json()
        assert replay['mode'] == 'replay' and replay['query'] == original['query']
        assert replay['round_id'] != original['round_id'] and replay['elapsed_ms'] == 0
        assert replay['queue'][0]['candidate']['video_url'] != original['queue'][0]['candidate']['video_url']
        cursor = replay
        for _ in replay['queue']:
            cursor = outcome(client, report(replay, cursor))
        assert cursor['status'] == 'paused'
        assert client.post('/demo-api/runs/run-1/resume').json()['status'] == 'needs_plan'
        assert not next(iter(app.state.run_service.runs.values())).history
        assert len(app.state.encounter_service.agent.agent.calls) == 2
        assert sum(r.url.path.endswith('/search') for r in upstream.requests) == 1


def test_no_match_avoids_action_agent_call_and_pauses_without_hidden_retry():
    client, upstream, app = setup(clips=[{**ROW, 'reasoning_content': 'A cat stands still.'}])
    with client:
        start(client, True)
        result = search(client)
    assert result['queue'] == [] and result['execution'] is None and result['run_status'] == 'paused'
    assert result['candidates'][0]['eligibility_reason'] == 'passive_behavior_excluded'
    assert len(app.state.encounter_service.agent.agent.calls) == 1
    assert sum(r.url.path.endswith('/search') for r in upstream.requests) == 1


def test_expired_queue_and_failed_motion_require_resume_without_false_completion():
    client, _, app = setup()
    with client:
        start(client)
        result = search(client)
        body = report(result, result); body['state']['status'] = 'failed'
        assert client.post('/demo-api/runs/run-1/outcome', json=body).status_code == 422
        body['status'] = 'failed'
        assert outcome(client, body)['status'] == 'paused'
        run = next(iter(app.state.run_service.runs.values()))
        run.round.expires = 0
        assert client.post('/demo-api/runs/run-1/resume').json()['status'] == 'needs_plan'


def test_fabricated_companion_behavior_is_skipped_and_later_active_clip_fills_queue():
    clips = rows()
    clips[1]['reasoning_content'] = 'Two cats are visible. One cat stands still. The other cat walks.'
    def change(data):
        data['actions'][0]['role_plan'] = {'grounding': 'caption_roles',
            'companion': {'subject': 'Standing cat', 'evidence': 'One cat stands still.'},
            'duck': {'subject': 'Walking cat', 'evidence': 'The other cat walks.'},
            'companion_behavior': 'hissing', 'duck_behavior': 'moving', 'timing': 'together'}
    client, _, _ = setup(agent=RunAgent(change), clips=clips)
    with client:
        start(client)
        result = search(client)
    assert [entry['candidate']['rank'] for entry in result['queue']] == [3, 5, 6]
    assert result['candidates'][1]['eligibility_reason'] == 'agent_action_unverified'


def test_exact_passive_review_stays_excluded_in_shared_pipeline():
    clip = {**ROW, 'reasoning_content': 'A cat stands still and then walks.'}
    client, _, _ = setup(clips=[clip], manifest=[reviewed(clip, animal='cat', behavior='standing')])
    with client:
        start(client)
        result = search(client)
    assert not result['queue'] and result['candidates'][0]['review_status'] == 'reviewed'


def test_supported_paired_roles_survive_batch_validation():
    clip = {**ROW, 'reasoning_content': 'Two cats are visible. One cat stands still. The other cat walks.'}
    def change(data):
        data['actions'][0]['role_plan'] = {'grounding': 'caption_roles',
            'companion': {'subject': 'Standing cat', 'evidence': 'One cat stands still.'},
            'duck': {'subject': 'Walking cat', 'evidence': 'The other cat walks.'},
            'companion_behavior': 'standing', 'duck_behavior': 'moving', 'timing': 'together'}
    client, _, _ = setup(agent=RunAgent(change), clips=[clip])
    with client:
        start(client)
        result = search(client)
    assert result['queue'][0]['role_plan']['grounding'] == 'caption_roles'
    assert result['queue'][0]['candidate']['action']['primitive'] == 'short_walk'


def test_pause_cancels_inflight_query_and_late_result_cannot_issue_execution():
    async def scenario():
        entered, stopped = asyncio.Event(), asyncio.Event()
        class Slow(RunAgent):
            async def decide(self, context, schema):
                entered.set()
                try:
                    await asyncio.sleep(60)
                finally:
                    stopped.set()
        app = create_app(SETTINGS, httpx.MockTransport(Upstream(rows())), Manifest(), Slow())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            await client.post('/demo-api/runs', json={'run_id': 'run-1', 'animal': 'cat', 'scenario_id': 'cat-play'})
            task = asyncio.create_task(client.post('/demo-api/runs/run-1/plan', json={}))
            await asyncio.wait_for(entered.wait(), 1)
            assert (await client.post('/demo-api/runs/run-1/pause')).json()['status'] == 'paused'
            assert (await task).status_code == 409 and stopped.is_set()
            run = next(iter(app.state.run_service.runs.values()))
            assert run.phase == 'paused' and run.pending is None
        await app.state.encounter_service.close(); await app.state.archive.close()
    asyncio.run(scenario())


def test_two_tabs_share_cookie_but_keep_plans_video_outcomes_and_pause_independent():
    client, _, app = setup()
    with client:
        start(client, run_id='tab-one')
        first_plan = client.post('/demo-api/runs/tab-one/plan', json={}).json()
        start(client, run_id='tab-two')
        second_plan = client.post('/demo-api/runs/tab-two/plan', json={}).json()
        # The legacy endpoint remains isolated too, despite the common cookie.
        legacy = client.post('/demo-api/encounter-plan', json={'encounter_id': 'legacy', 'scenario_id': 'cat-play'})
        assert legacy.status_code == 200
        results = []
        for run_id, planned in [('tab-one', first_plan), ('tab-two', second_plan)]:
            response = client.post(f'/demo-api/runs/{run_id}/search', json={'plan_id': planned['plan_id']})
            assert response.status_code == 200, response.text
            result = response.json()
            video = client.get(result['queue'][0]['candidate']['video_url'])
            assert video.status_code == 200 and 'set-cookie' not in video.headers
            acknowledged = client.post(f'/demo-api/runs/{run_id}/outcome', json=report(result, result))
            assert acknowledged.status_code == 200, acknowledged.text
            results.append((result, acknowledged.json()))
        paused = client.post('/demo-api/runs/tab-one/pause')
        assert paused.json()['status'] == 'paused'
        result, cursor = results[1]
        still_active = client.post('/demo-api/runs/tab-two/outcome', json=report(result, cursor))
        assert still_active.status_code == 200 and still_active.json()['status'] == 'ready'
        runs = {run.id: run for run in app.state.run_service.runs.values()}
        assert runs['tab-one'].phase == 'paused' and len(runs['tab-one'].history) == 1
        assert runs['tab-two'].phase == 'ready' and len(runs['tab-two'].history) == 2
        # A run ID is not an ownership credential for a different browser.
        client.cookies.clear()
        client.get('/demo-api/health')
        denied = client.post('/demo-api/runs/tab-two/resume')
        assert denied.status_code == 404 and denied.json()['error']['code'] == 'run_not_found'


def test_pausing_one_tab_cancels_only_its_inflight_agent_task():
    async def scenario():
        entered = {name: asyncio.Event() for name in ('tab-one', 'tab-two')}
        release = asyncio.Event()
        cancelled = []
        class Blocking(RunAgent):
            async def decide(self, context, schema):
                if context['task'] == 'encounter_query':
                    name = context['original_prompt']
                    entered[name].set()
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        cancelled.append(name)
                        raise
                return await super().decide(context, schema)
        app = create_app(SETTINGS, httpx.MockTransport(Upstream(rows())), Manifest(), Blocking())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            for name in entered:
                created = await client.post('/demo-api/runs', json={'run_id': name, 'animal': 'cat',
                    'scenario_id': 'cat-play', 'intent': name})
                assert created.status_code == 200
            first = asyncio.create_task(client.post('/demo-api/runs/tab-one/plan', json={}))
            await asyncio.wait_for(entered['tab-one'].wait(), 1)
            second = asyncio.create_task(client.post('/demo-api/runs/tab-two/plan', json={}))
            await asyncio.wait_for(entered['tab-two'].wait(), 1)
            paused = await client.post('/demo-api/runs/tab-one/pause')
            assert paused.json()['status'] == 'paused'
            assert (await first).status_code == 409
            assert cancelled == ['tab-one'] and not second.done()
            release.set()
            planned = await second
            assert planned.status_code == 200, planned.text
            searched = await client.post('/demo-api/runs/tab-two/search', json={'plan_id': planned.json()['plan_id']})
            assert searched.status_code == 200 and searched.json()['queue']
        await app.state.encounter_service.close(); await app.state.archive.close()
    asyncio.run(scenario())


def test_run_limit_retires_paused_runs_without_replacing_active_tabs():
    client, _, app = setup()
    with client:
        for index in range(8):
            start(client, run_id=f'tab-{index}')
        rejected = client.post('/demo-api/runs', json={'run_id': 'tab-nine', 'animal': 'cat', 'scenario_id': 'cat-play'})
        assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'run_limit_reached'
        assert len(app.state.run_service.runs) == 8
        client.post('/demo-api/runs/tab-0/pause')
        start(client, run_id='tab-nine')
        assert {run.id for run in app.state.run_service.runs.values()} == {f'tab-{i}' for i in range(1, 8)} | {'tab-nine'}


def test_other_tab_searches_cannot_evict_selected_queue_clips_and_retirement_releases_them():
    client, _, app = setup()
    with client:
        start(client)
        first = search(client)
        protected_urls = [entry['candidate']['video_url'] for entry in first['queue']]
        start(client, run_id='other-tab')
        planned = client.post('/demo-api/runs/other-tab/plan', json={}).json()
        second = client.post('/demo-api/runs/other-tab/search', json={'plan_id': planned['plan_id']}).json()
        session = next(iter(app.state.registry.sessions.values()))
        # Simulate repeated round/replay rendering in another tab, well beyond
        # the shared capability limit, without a single new paid inference.
        for _ in range(15):
            replay = client.post('/demo-api/runs/other-tab/replay')
            assert replay.status_code == 200
            assert len(session.clips) <= 60
            assert sum(map(len, session.protected_clips.values())) == 6
        for url in protected_urls:
            assert client.get(url).status_code == 200
        assert client.post('/demo-api/runs/run-1/outcome', json=report(first, first)).status_code == 200
        # Explicit replacement of this same run ID retires only its protection.
        start(client)
        assert 'run-1' not in session.protected_clips and 'other-tab' in session.protected_clips
        for clip in session.protected_clips['other-tab']:
            source, _ = session.clips[clip]
            session.clips[clip] = (source, 0)
        app.state.registry._prune()
        assert not session.protected_clips


@pytest.mark.parametrize('animal,initial', [('cat', 'cat-greeting'), ('deer', 'deer-feeding')])
def test_adaptive_round_randomizes_a_different_same_species_encounter_after_actual_outcomes(monkeypatch, animal, initial):
    alternatives = []
    def choose(items):
        alternatives.append([item['id'] for item in items])
        return items[-1]
    monkeypatch.setattr('ranger_duck.runs.secrets.choice', choose)
    clips = [{**row, 'reasoning_content': row['reasoning_content'].replace('cat', animal)} for row in rows()]
    client, _, app = setup(clips=clips)
    with client:
        created = client.post('/demo-api/runs', json={'run_id': 'run-1', 'animal': animal, 'scenario_id': initial,
            'intent': 'React calmly to changing behavior', 'adaptive': True})
        assert created.status_code == 200
        first_plan = plan(client)
        assert first_plan['scenario']['id'] == initial and not alternatives
        first = search(client, first_plan)
        assert first['scenario'] == first_plan['scenario']
        cursor = first
        for _ in first['queue']:
            cursor = outcome(client, report(first, cursor))
        second_plan = plan(client)
        selected = second_plan['scenario']['id']
        assert selected != initial and second_plan['scenario']['animal'] == animal
        assert len(alternatives) == 1 and len(alternatives[0]) == 2
        assert all(item.startswith(f'{animal}-') and item != initial for item in alternatives[0])
        agent = app.state.encounter_service.agent.agent
        assert agent.calls[-1]['encounter']['id'] == selected
        assert agent.calls[-1]['original_prompt'] == 'React calmly to changing behavior'
        assert all(item['scenario']['id'] == initial for item in agent.calls[-1]['history'])
        second = search(client, second_plan)
        assert second['scenario']['id'] == selected and agent.calls[-1]['encounter']['id'] == selected
        # Replay is a snapshot, not a fresh random encounter or live outcome.
        client.post('/demo-api/runs/run-1/pause')
        replay = client.post('/demo-api/runs/run-1/replay').json()
        assert replay['scenario'] == second['scenario'] and len(alternatives) == 1
        run = next(iter(app.state.run_service.runs.values()))
        history_size = len(run.history)
        cursor = replay
        for _ in replay['queue']:
            cursor = outcome(client, report(replay, cursor))
        assert len(run.history) == history_size and run.completed_scenario['id'] == initial


def test_pending_random_encounter_survives_pause_retry_and_toggle_off(monkeypatch):
    choices = []
    def choose(items):
        choices.append(items[0]['id'])
        return items[0]
    monkeypatch.setattr('ranger_duck.runs.secrets.choice', choose)
    client, _, app = setup()
    with client:
        start(client, True)
        first = search(client)
        cursor = first
        for _ in first['queue']:
            cursor = outcome(client, report(first, cursor))
        pending = plan(client)
        client.post('/demo-api/runs/run-1/pause')
        # Replay does not consume or replace the pending next live scenario.
        replay = client.post('/demo-api/runs/run-1/replay').json()
        assert replay['scenario'] == first['scenario']
        client.post('/demo-api/runs/run-1/pause')
        run = next(iter(app.state.run_service.runs.values()))
        run.round.expires = 0  # Resume must prepare a fresh live query.
        client.post('/demo-api/runs/run-1/adaptive', json={'adaptive': False})
        assert client.post('/demo-api/runs/run-1/resume').json()['status'] == 'needs_plan'
        repeated = plan(client)
        assert repeated['scenario'] == pending['scenario'] and len(choices) == 1
        result = search(client, repeated)
        cursor = result
        for _ in result['queue']:
            cursor = outcome(client, report(result, cursor))
        assert cursor['status'] == 'ready' and cursor['pass'] == 2
        assert len(choices) == 1 and result['scenario'] == pending['scenario']


def test_fixed_queue_never_randomizes_its_encounter(monkeypatch):
    def forbidden(items):
        raise AssertionError('Loop OFF must not choose a new encounter')
    monkeypatch.setattr('ranger_duck.runs.secrets.choice', forbidden)
    client, _, app = setup()
    with client:
        start(client)
        planned = plan(client)
        result = search(client, planned)
        cursor = result
        for _ in range(len(result['queue']) * 2):
            cursor = outcome(client, report(result, cursor))
        assert cursor['pass'] == 3 and result['scenario']['id'] == 'cat-greeting'
        assert len(app.state.encounter_service.agent.agent.calls) == 2
