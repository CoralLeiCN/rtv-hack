"""Loop contracts use fabricated archive results and an injected structured agent."""
import asyncio
from dataclasses import replace
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ranger_duck.app import create_app
from ranger_duck.evidence import Manifest
from ranger_duck.loop_agent import ActionDecision, QueryDecision, CodexAgent, RolePlan
from ranger_duck.errors import DemoError
from ranger_duck.encounter_agent import EncounterQueryDecision, EncounterActionsDecision
from test_backend import SETTINGS, ROW, Upstream, reviewed, EncounterAgent


def neutral_plan():
    return RolePlan(grounding='insufficient_evidence',
                    companion={'subject': 'Unknown', 'evidence': ''},
                    duck={'subject': 'Unknown counterpart', 'evidence': ''},
                    companion_behavior='standing', duck_behavior='unknown', timing='together')


def paired_plan(caption, primitive='head_scan'):
    return RolePlan(grounding='caption_roles',
                    companion={'subject': 'Approaching deer', 'evidence': 'one deer approaches'},
                    duck={'subject': 'Watching deer', 'evidence': caption[caption.index('the other deer'):].rstrip('.') if 'the other deer' in caption else 'the other deer watches'},
                    companion_behavior='approach', duck_behavior={'head_scan':'looking', 'stand_hold':'still', 'short_walk':'moving', 'ground_pick':'feeding'}.get(primitive, 'looking'), timing='companion_first')


class Agent:
    available = True
    def __init__(self):
        self.calls = []
        self.primitive = 'head_scan'
        self.invalid_id = False
        self.plan = None

    async def decide(self, context, schema):
        if schema in {EncounterQueryDecision, EncounterActionsDecision}:
            return await EncounterAgent.decide(self, context, schema)
        self.calls.append(json.loads(json.dumps(context)))
        if schema is QueryDecision:
            return QueryDecision(query=f"A {context['animal']} approaches another {context['animal']}",
                                 individual_query=f"A {context['animal']} walks alone", reason='Follow the prior actual reaction.')
        selected = next(c for c in context['candidates'] if c['allowed_actions'])
        plan = self.plan or (paired_plan(selected['caption'], self.primitive) if 'one deer approaches' in selected['caption'] and 'the other deer' in selected['caption'] else neutral_plan())
        return ActionDecision.model_construct(candidate_id='unknown' if self.invalid_id else next(c['candidate_id'] for c in context['candidates'] if c['allowed_actions']),
                              primitive=self.primitive, reason='Approximate the watching deer with a head scan.', role_plan=plan)


def row(index=0, caption='Two deer interact; one deer approaches and the other deer watches.'):
    return {**ROW, 'source': f's3://test-segments/{index}.mp4',
            'segment_start_sec': index * 10, 'segment_end_sec': index * 10 + 5,
            'reasoning_content': caption}


def setup(results=None, agent=None, manifest=None):
    upstream = Upstream(results or [row()])
    agent = agent or Agent()
    app = create_app(SETTINGS, httpx.MockTransport(upstream), manifest or Manifest(), agent)
    return TestClient(app), upstream, agent, app


def start(client, sid='loop-1', animal='deer'):
    client.get('/demo-api/health')
    response = client.post('/demo-api/loop', json={'session_id': sid, 'prompt': 'Meet a curious deer', 'animal': animal})
    assert response.status_code == 200, response.text


def next_cycle(client, sid='loop-1'):
    return client.post(f'/demo-api/loop/{sid}/next')


def outcome(cycle, **overrides):
    return {'cycle_id': cycle['cycle_id'], 'primitive': cycle['action']['primitive'], 'status': 'completed',
            'playback': 'ended', 'companion': {'behavior': cycle['role_plan']['companion_behavior'], 'status': 'completed'}, 'state': {'status': 'complete', 'position': [0.1, 0.0, 0.2],
                                         'head_yaw': 0.01, 'simulation_time': 12.0}, **overrides}


def test_actual_outcome_guides_next_search_and_clip_capabilities_work():
    client, upstream, agent, _ = setup([row(0), row(1)])
    with client:
        start(client)
        first = next_cycle(client).json()
        assert first['action']['primitive'] == 'head_scan'
        assert first['clip']['evidence_basis'] == 'video_caption'
        assert next_cycle(client).status_code == 409  # no overlap while action outstanding
        assert client.get(first['clip']['video_url']).status_code == 200
        assert client.post('/demo-api/loop/loop-1/outcome', json=outcome(first)).status_code == 200
        assert client.post('/demo-api/loop/loop-1/outcome', json=outcome(first)).status_code == 409
        second = next_cycle(client).json()
        assert second['cycle'] == 2 and second['clip']['start_sec'] != first['clip']['start_sec']
        history = agent.calls[2]['history']
        assert history[0]['outcome']['state']['position'] == [0.1, 0.0, 0.2]
        assert agent.calls[2]['original_prompt'] == 'Meet a curious deer'
        assert 'test-secret' not in json.dumps(agent.calls)
        assert 's3://' not in json.dumps(agent.calls)
        assert 's3://' not in json.dumps(second)


@pytest.mark.parametrize('invalid_id,primitive', [(True, 'head_scan'), (False, 'jump')])
def test_unknown_clip_and_behavior_inappropriate_action_are_rejected(invalid_id, primitive):
    agent = Agent(); agent.invalid_id = invalid_id; agent.primitive = primitive
    client, _, _, _ = setup(agent=agent)
    with client:
        start(client)
        assert next_cycle(client).json()['error']['code'] == 'invalid_agent_action'


def test_can_select_beyond_rank_three_without_changing_existing_mode():
    client, _, _, _ = setup([{**row(i), 'segment_end_sec': None} for i in range(3)] + [row(3)])
    with client:
        start(client)
        assert next_cycle(client).json()['clip']['rank'] == 4
        old = client.post('/demo-api/search', json={'encounter_id': 'old', 'scenario_id': 'deer-standing'}).json()
        assert old['status'] == 'ok'  # main now selects compatible actions beyond rank three
        assert any(c['rank'] == 4 and c['action'] for c in old['candidates'])


def test_no_match_has_two_searches_per_attempt_and_pauses_after_three():
    client, upstream, agent, _ = setup([{**row(), 'segment_end_sec': None}])
    with client:
        start(client)
        for _ in range(3):
            assert next_cycle(client).json()['error']['code'] == 'no_loop_match'
        assert len(agent.calls) == 6
        assert next_cycle(client).json()['error']['code'] == 'loop_not_ready'
        assert client.post('/demo-api/loop/loop-1/resume').status_code == 200
        assert next_cycle(client).json()['error']['code'] == 'no_loop_match'


def test_stop_invalidates_outcome_and_resume_preserves_context():
    client, _, agent, _ = setup([row(0), row(1)])
    with client:
        start(client)
        first = next_cycle(client).json()
        assert client.post('/demo-api/loop/loop-1/pause').status_code == 200
        assert client.post('/demo-api/loop/loop-1/outcome', json=outcome(first)).status_code == 409
        assert next_cycle(client).status_code == 409
        assert client.post('/demo-api/loop/loop-1/resume').status_code == 200
        assert next_cycle(client).status_code == 200
        assert agent.calls[2]['history'][0]['outcome'] == {'status': 'cancelled', 'state': None}


def test_failed_physics_outcome_pauses_and_false_completion_is_rejected():
    client, _, _, _ = setup()
    with client:
        start(client)
        first = next_cycle(client).json()
        assert client.post('/demo-api/loop/loop-1/outcome', json=outcome(first, playback='failed')).status_code == 422
        state = {'status': 'failed', 'position': [0., 0., 0.1], 'head_yaw': 0., 'simulation_time': 13.}
        result = client.post('/demo-api/loop/loop-1/outcome', json=outcome(first, status='failed', state=state))
        assert result.json()['status'] == 'paused'
        assert next_cycle(client).status_code == 409


def test_loop_session_isolation_and_reset():
    client, _, _, app = setup()
    with client, TestClient(app) as other:
        start(client)
        other.get('/demo-api/health')
        assert next_cycle(other).status_code == 404
        first = next_cycle(client).json()
        assert other.get(first['clip']['video_url']).status_code == 404
        start(client, 'new-loop')
        assert next_cycle(client).status_code == 404
        assert next_cycle(client, 'new-loop').json()['cycle'] == 1


def test_caption_content_does_not_filter_results_but_stale_reviews_block_execution():
    for caption in ['A lone deer is standing.', 'Two deer do not approach another deer.', 'Two cats are playing together.']:
        client, _, _, _ = setup([row(caption=caption)])
        with client:
            start(client)
            assert next_cycle(client).status_code == 200
    item = reviewed(row(), interaction_partner='deer', interaction_evidence='One deer approaches another deer.')
    client, _, _, _ = setup([row(caption='Two deer are following another deer.')], manifest=Manifest([item]))
    with client:
        start(client)
        assert next_cycle(client).json()['error']['code'] == 'no_loop_match'


def test_cat_scope_and_unavailable_agent():
    clip = {**row(caption='Two cats interact; one cat approaches another cat.'),
            'extra_metadata': json.dumps({'dataset_id': 'actual-archive-dataset'})}
    client, upstream, _, _ = setup([clip])
    with client:
        start(client, animal='cat')
        cycle = next_cycle(client)
        assert cycle.status_code == 200
        assert cycle.json()['search_scope'] == {'tags': ['meow-10k', 'cat-behavior'],
                                               'requested_dataset_id': 'hf-smgjch-meow-10k', 'dataset_filter_applied': False}
        assert cycle.json()['clip']['dataset_id'] == 'actual-archive-dataset'
        search = next(r for r in upstream.requests if r.url.path.endswith('/search'))
        assert json.loads(search.content)['tags'] == ['meow-10k', 'cat-behavior']
        assert 'metadata_filters' not in json.loads(search.content)
    agent = Agent(); agent.available = False
    client, _, _, _ = setup(agent=agent)
    with client:
        client.get('/demo-api/health')
        assert client.post('/demo-api/loop', json={'session_id': 's', 'prompt': 'deer', 'animal': 'deer'}).status_code == 503


def test_pause_cancels_inflight_agent_without_issuing_action():
    async def scenario():
        entered = asyncio.Event(); stopped = asyncio.Event()
        class SlowAgent(Agent):
            async def decide(self, context, schema):
                entered.set()
                try: await asyncio.sleep(60)
                finally: stopped.set()
        app = create_app(SETTINGS, httpx.MockTransport(Upstream([row()])), Manifest(), SlowAgent())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            await client.get('/demo-api/health')
            await client.post('/demo-api/loop', json={'session_id': 's', 'prompt': 'deer', 'animal': 'deer'})
            task = asyncio.create_task(client.post('/demo-api/loop/s/next'))
            await asyncio.wait_for(entered.wait(), 1)
            assert (await client.post('/demo-api/loop/s/next')).status_code == 409
            assert (await client.post('/demo-api/loop/s/pause')).status_code == 200
            assert (await task).status_code == 409
            assert stopped.is_set()
            assert next(iter(app.state.loop_service.sessions.values())).pending is None
        await app.state.vss.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('caption,primitive,behavior', [
    ('A deer walks across a clearing.', 'short_walk', 'moving'),
    ('A deer feeds.', 'ground_pick', 'feeding'),
    ('A deer raises its head.', 'head_nod', 'nodding'),
    ('A deer looks around.', 'head_scan', 'looking'),
    ('A deer sits down.', 'sit_cycle', 'sitting'),
    ('A deer stands still.', 'stand_hold', 'still'),
])
def test_loop_can_imitate_six_supported_solitary_behaviors_without_a_second_role(caption, primitive, behavior):
    agent = Agent(); agent.primitive = primitive
    agent.plan = RolePlan(grounding='single_behavior',
        companion={'subject': 'Unassigned', 'evidence': ''},
        duck={'subject': 'The solitary deer', 'evidence': caption},
        companion_behavior='standing', duck_behavior=behavior, timing='together')
    client, _, _, _ = setup([row(caption=caption)], agent=agent)
    with client:
        start(client)
        result = next_cycle(client)
    assert result.status_code == 200, result.text
    cycle = result.json()
    assert cycle['action']['primitive'] == primitive
    assert cycle['role_plan']['grounding'] == 'single_behavior'
    assert cycle['role_plan']['companion'] == {'subject': 'Unassigned scene companion', 'evidence': ''}
    assert cycle['role_plan']['companion_behavior'] == 'standing'


@pytest.mark.parametrize('caption', ['A cat walks across a room.', 'A deer does not walk.', 'A deer may walk.'])
def test_loop_single_behavior_needs_positive_selected_species_evidence(caption):
    agent = Agent(); agent.primitive = 'short_walk'
    agent.plan = RolePlan(grounding='single_behavior',
        companion={'subject': 'Unassigned', 'evidence': ''},
        duck={'subject': 'Claimed deer', 'evidence': caption},
        companion_behavior='standing', duck_behavior='moving', timing='together')
    client, _, _, _ = setup([row(caption=caption)], agent=agent)
    with client:
        start(client)
        assert next_cycle(client).json()['error']['code'] == 'invalid_agent_action'


@pytest.mark.parametrize('schema', [QueryDecision, EncounterQueryDecision])
def test_cli_runner_uses_schema_and_does_not_forward_workshop_secrets(tmp_path, monkeypatch, schema):
    import sys
    script = tmp_path / 'fake-codex'
    script.write_text(f'#!{sys.executable}\n' + '''import sys, os, json
from pathlib import Path
assert "PASSWORD" not in os.environ and "OPENAI_API_KEY" not in os.environ
assert "--sandbox" in sys.argv and "read-only" in sys.argv
assert "features.shell_tool=false" in sys.argv
assert "--ignore-user-config" in sys.argv
assert 'forced_login_method="chatgpt"' in sys.argv
assert sys.argv[sys.argv.index("--model")+1] == "gpt-6-luna"
payload = sys.stdin.read()
assert "original_prompt" in payload
assert "Interactions must be cat–cat or deer–deer" in payload
assert "similar solitary motion by that same species" in payload
assert "Do not expand the query to interactions with people or other species" in payload
assert "individual_query" in payload and "Both fields are required" in payload
Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(json.dumps({"query":"two deer interact", "individual_query":"A deer walks alone", "reason":"initial prompt"}))
''')
    script.chmod(0o700)
    monkeypatch.setenv('PASSWORD', 'do-not-pass')
    monkeypatch.setenv('OPENAI_API_KEY', 'do-not-pass')
    agent = CodexAgent(); agent.executable = str(script)
    result = asyncio.run(agent.decide({'original_prompt': 'deer'}, schema))
    assert result.query == 'two deer interact'
    assert result.individual_query == 'A deer walks alone'


@pytest.mark.parametrize('individual_query', ['A cat walks alone', '   '])
def test_loop_validates_individual_query_branch_before_archive_search(individual_query):
    class InvalidIndividual(Agent):
        async def decide(self, context, schema):
            result = await super().decide(context, schema)
            if schema is QueryDecision:
                result.individual_query = individual_query
            return result
    client, upstream, _, _ = setup(agent=InvalidIndividual())
    with client:
        start(client)
        result = next_cycle(client)
    assert result.json()['error']['code'] == 'invalid_agent_query'
    assert not any(r.url.path.endswith('/search') for r in upstream.requests)


@pytest.mark.parametrize('primitive', ['stand_hold', 'head_scan', 'short_walk', 'ground_pick'])
def test_top_ten_are_returned_without_pair_or_behavior_filtering(primitive):
    captions = ['Two deer interact; one deer approaches and the other deer watches.', 'A cat watches it.',
                'Two deer graze together.', 'No animals are visible.',
                'Possibly a deer.', 'A deer is standing.',
                'A dog is walking.', 'A deer runs away.',
                'A deer is visible.', 'A tree beside the road.',
                'Two deer approach each other.']
    captions[0] = 'Two deer interact; one deer approaches and the other deer ' + {'stand_hold':'stands still.', 'head_scan':'looks toward it.', 'short_walk':'walks toward it.', 'ground_pick':'feeds.'}[primitive]
    agent = Agent(); agent.primitive = primitive
    client, upstream, agent, _ = setup([row(i, c) for i, c in enumerate(captions)], agent=agent)
    with client:
        start(client)
        response = next_cycle(client)
        assert response.status_code == 200, response.text
        cycle = response.json()
        assert cycle['action']['primitive'] == primitive
        assert cycle['clip']['rank'] == 1
        assert cycle['clip']['observed_behavior'] == 'caption_context'
        assert [c['caption'] for c in cycle['candidates']] == captions[:10]
        assert [c['rank'] for c in cycle['candidates']] == list(range(1, 11))
        assert agent.calls[1]['candidates'] == cycle['candidates']
        assert all(c['allowed_actions'] for c in cycle['candidates'])
        search = next(r for r in upstream.requests if r.url.path.endswith('/search'))
        payload = json.loads(search.content)
        assert payload['top_k'] == 10
        assert payload['query'] == 'A deer approaches another deer OR A deer walks alone'
        assert payload['tags'] == ['wildlife']
        assert 'metadata_filters' not in payload
        assert cycle['search_scope'] == {'tags': ['wildlife']}
        assert 's3://' not in response.text


def test_unexecutable_and_duplicate_results_keep_original_top_ten_slots():
    rows = [row(i, 'A deer is visible.') for i in range(11)]
    rows[0]['source'] = 'invalid'
    rows[1]['segment_end_sec'] = None
    rows[2]['segment_end_sec'] = rows[2]['segment_start_sec'] + 121
    rows[4] = rows[3].copy()
    class SelectLastAgent(Agent):
        async def decide(self, context, schema):
            if schema is QueryDecision:
                return await super().decide(context, schema)
            return ActionDecision(candidate_id=context['candidates'][-1]['candidate_id'],
                                  primitive='stand_hold', reason='Observe this clip.', role_plan=neutral_plan())
    client, _, _, _ = setup(rows, agent=SelectLastAgent())
    with client:
        start(client)
        cycle = next_cycle(client).json()
        assert cycle['clip']['rank'] == 10
        assert len(cycle['candidates']) == 10
        assert [c['unavailable_reason'] for c in cycle['candidates'][:3]] == [
            'invalid_source', 'incomplete_metadata', 'clip_too_long']
        assert all(not c['allowed_actions'] for c in cycle['candidates'][:3])
        assert cycle['candidates'][3]['caption'] == cycle['candidates'][4]['caption']
        assert client.post('/demo-api/loop/loop-1/outcome', json=outcome(cycle)).status_code == 200
        # Recent clips remain visible but cannot be immediately executed again.
        assert next_cycle(client).json()['error']['code'] == 'invalid_agent_action'


def test_single_animal_uses_neutral_loop_roles_and_main_encounter_imitation():
    client, _, _, _ = setup([row(caption='A lone deer is standing.')])
    with client:
        start(client)
        assert next_cycle(client).status_code == 200
        old = client.post('/demo-api/search', json={'encounter_id': 'old', 'scenario_id': 'deer-standing'})
        assert old.json()['status'] == 'ok'
        assert old.json()['candidates'][0]['action']['primitive'] == 'stand_hold'


@pytest.mark.parametrize('change', ['fabricated_evidence', 'same_subject', 'unsupported_companion', 'wrong_duck_action'])
def test_invalid_two_role_plan_cannot_start_a_cycle(change):
    agent = Agent()
    plan = paired_plan('').model_dump()
    if change == 'fabricated_evidence': plan['duck']['evidence'] = 'the deer flies'
    if change == 'same_subject': plan['duck']['subject'] = plan['companion']['subject']
    if change == 'wrong_duck_action': plan['duck_behavior'] = 'feeding'
    if change == 'unsupported_companion': plan['companion_behavior'] = 'hissing'
    agent.plan = RolePlan.model_validate(plan)
    client, _, _, _ = setup(agent=agent)
    with client:
        start(client)
        assert next_cycle(client).json()['error']['code'] == 'invalid_agent_action'


def test_sparse_caption_keeps_clip_and_normalizes_neutral_roles():
    agent = Agent(); agent.primitive = 'ground_pick'; agent.plan = neutral_plan()
    client, _, _, _ = setup([row(caption='A deer is visible.')], agent=agent)
    with client:
        start(client)
        cycle = next_cycle(client).json()
        assert len(cycle['candidates']) == 1
        assert cycle['action']['primitive'] == 'stand_hold'
        assert cycle['role_plan']['companion_behavior'] == 'standing'
        assert cycle['role_plan']['grounding'] == 'insufficient_evidence'
        assert cycle['role_plan']['duck']['evidence'] == ''
        assert 'not an observed interaction' in cycle['response_reason']


def test_both_role_outcomes_and_evidence_reach_next_query():
    client, _, agent, _ = setup([row(0), row(1)])
    with client:
        start(client)
        cycle = next_cycle(client).json()
        assert cycle['role_plan']['companion_duration_ms'] == 3000
        for companion in [{'behavior': 'approach', 'status': 'failed'}, {'behavior': 'feeding', 'status': 'completed'}]:
            assert client.post('/demo-api/loop/loop-1/outcome', json=outcome(cycle, companion=companion)).status_code == 422
        assert client.post('/demo-api/loop/loop-1/outcome', json=outcome(cycle)).status_code == 200
        assert next_cycle(client).status_code == 200
        record = agent.calls[2]['history'][0]
        assert record['role_plan'] == cycle['role_plan']
        assert record['outcome']['companion'] == {'behavior': 'approach', 'status': 'completed'}
        assert record['outcome']['state']['position'] == [0.1, 0.0, 0.2]
