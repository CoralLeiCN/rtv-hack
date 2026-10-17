"""Encounter agent decisions are real inputs, never bypasses for evidence guards."""
import asyncio
import json
import time

import httpx
import pytest

from ranger_duck.app import create_app
from ranger_duck.encounter_agent import EncounterQueryDecision, EncounterActionsDecision
from ranger_duck.evidence import Manifest
from ranger_duck.session import COOKIE_NAME
from test_backend import EncounterAgent, SETTINGS, PAYLOAD, ROW, Upstream, make_client, reviewed, search


class Agent(EncounterAgent):
    def __init__(self, query=None, mutate=None, individual_query=None):
        super().__init__()
        self.query, self.mutate = query, mutate
        self.individual_query = individual_query

    async def decide(self, context, schema):
        result = await super().decide(context, schema)
        if schema is EncounterQueryDecision and self.query:
            result.query = self.query
        if schema is EncounterQueryDecision and self.individual_query is not None:
            result.individual_query = self.individual_query
        if schema is EncounterActionsDecision and self.mutate:
            self.mutate(result)
        return result


def test_plan_exposes_generated_query_before_search_and_replay_reuses_decisions():
    agent = Agent(query='A deer forages beside another deer')
    client, upstream, app = make_client(agent=agent)
    with client:
        client.get('/demo-api/health')
        plan = client.post('/demo-api/encounter-plan', json=PAYLOAD).json()
        expected_query = agent.query + ' OR A deer alone showing similar observable motion'
        assert plan['query'] == expected_query and plan['query_basis'] == 'agent' and plan['query_reason']
        assert len(agent.calls) == 1 and not upstream.requests
        result = client.post('/demo-api/search', json={**PAYLOAD, 'plan_id': plan['plan_id']}).json()
        assert len(agent.calls) == 2
        assert result['query'] == plan['query'] and result['agent_plan']['summary']
        assert result['candidates'][0]['action_planner'] == 'agent'
        assert result['candidates'][0]['evidence_excerpt'] == ROW['reasoning_content']
        assert json.loads(next(r.content for r in upstream.requests if r.url.path.endswith('/search')))['query'] == expected_query
        replay = client.post('/demo-api/search', json={**PAYLOAD, 'mode': 'replay'}).json()
        assert len(agent.calls) == 2
        assert replay['candidates'][0]['agent_reason'] == result['candidates'][0]['agent_reason']
        assert replay['candidates'][0]['action'] == result['candidates'][0]['action']
        assert app.state.loop_service.agent is app.state.encounter_service.agent


def test_plans_are_scoped_expire_and_cannot_be_replayed_for_another_encounter():
    client, _, app = make_client()
    with client:
        client.get('/demo-api/health')
        plan = client.post('/demo-api/encounter-plan', json=PAYLOAD).json()
        for change in [{'encounter_id': 'other'}, {'scenario_id': 'cat-play'}, {'broaden': True}]:
            assert client.post('/demo-api/search', json={**PAYLOAD, **change, 'plan_id': plan['plan_id']}).status_code == 409
        owner = client.cookies.get(COOKIE_NAME)
        app.state.encounter_service.plans[owner].expires = time.monotonic() - 1
        assert client.post('/demo-api/search', json={**PAYLOAD, 'plan_id': plan['plan_id']}).status_code == 409
        client.cookies.clear()
        assert client.post('/demo-api/search', json={**PAYLOAD, 'plan_id': plan['plan_id']}).status_code == 409


def test_no_agent_fallback_and_wrong_species_query_never_reaches_archive():
    for agent, expected in [(Agent(query='Cats playing with a toy'), 'invalid_agent_query'), (Agent(), 'agent_unavailable')]:
        if expected == 'agent_unavailable':
            agent.available = False
        client, upstream, _ = make_client(agent=agent)
        with client:
            result = client.post('/demo-api/search', json=PAYLOAD)
        assert result.json()['error']['code'] == expected and not upstream.requests


@pytest.mark.parametrize('individual_query', ['A cat walks alone', '   '])
def test_individual_query_branch_is_validated_before_any_archive_search(individual_query):
    client, upstream, _ = make_client(agent=Agent(individual_query=individual_query))
    with client:
        result = client.post('/demo-api/search', json=PAYLOAD)
    assert result.json()['error']['code'] == 'invalid_agent_query'
    assert not upstream.requests


def test_combined_query_deduplicates_an_already_included_individual_branch():
    interaction = 'A deer walks beside another deer'
    individual = 'A single deer walks alone'
    client, upstream, _ = make_client(agent=Agent(query=f'{interaction} OR {individual}', individual_query=individual))
    with client:
        result = client.post('/demo-api/search', json=PAYLOAD)
    assert result.status_code == 200
    expected = f'{interaction} OR {individual}'
    assert result.json()['query'] == expected
    assert json.loads(next(request.content for request in upstream.requests if request.url.path.endswith('/search')))['query'] == expected


@pytest.mark.parametrize('caption,primitive', [
    ('A deer walks across a clearing.', 'short_walk'),
    ('A deer feeds.', 'ground_pick'),
    ('A deer raises its head.', 'head_nod'),
    ('A deer sits down.', 'sit_cycle'),
])
def test_agent_can_create_each_of_the_four_active_solitary_actions(caption, primitive):
    client, _, _ = make_client(Upstream([{**ROW, 'reasoning_content': caption}]))
    with client:
        item = search(client)['candidates'][0]
    assert item['action']['primitive'] == primitive and item['action_planner'] == 'agent'
    assert item['action_basis'] == 'video_caption' and item['review_status'] == 'unreviewed'


def test_passive_ranks_do_not_occupy_first_three_compatible_slots():
    captions = ['A cat looks around.', 'A cat stands still.', 'A cat walks.',
                'A cat watches a toy.', 'A cat feeds.', 'A cat sits down.', 'A cat raises its head.']
    rows = [{**ROW, 'source': f's3://test-segments/active-{i}.mp4', 'reasoning_content': caption}
            for i, caption in enumerate(captions)]
    client, _, _ = make_client(Upstream(rows))
    with client:
        result = client.post('/demo-api/search', json={**PAYLOAD, 'scenario_id': 'cat-play'}).json()
    compatible = [item for item in result['candidates'] if item['action']]
    assert [item['rank'] for item in compatible[:3]] == [3, 5, 6]
    assert all(result['candidates'][rank-1]['eligibility_reason'] == 'passive_behavior_excluded' for rank in [1, 2, 4])


@pytest.mark.parametrize('caption', ['A cat looks around.', 'A cat stands still.', 'A cat hisses.'])
def test_passive_only_encounter_has_no_substituted_action(caption):
    client, _, _ = make_client(Upstream([{**ROW, 'reasoning_content': caption}]))
    with client:
        result = client.post('/demo-api/search', json={**PAYLOAD, 'scenario_id': 'cat-hissing'}).json()
    assert result['status'] == 'no_supported_imitation'
    assert result['candidates'][0]['action'] is None
    assert result['candidates'][0]['eligibility_reason'] == 'passive_behavior_excluded'


def test_encounter_uses_active_sitting_even_when_caption_also_describes_looking():
    caption = 'A cat looks around and sits down.'
    client, _, _ = make_client(Upstream([{**ROW, 'reasoning_content': caption}]))
    with client:
        result = client.post('/demo-api/search', json={**PAYLOAD, 'scenario_id': 'cat-play'}).json()
    assert result['candidates'][0]['action']['primitive'] == 'sit_cycle'


def test_exact_passive_review_cannot_be_replaced_by_caption_active_motion():
    clip = {**ROW, 'reasoning_content': 'A deer stands still and then walks.'}
    client, _, _ = make_client(Upstream([clip]), manifest=[reviewed(clip, behavior='standing')])
    with client:
        result = search(client)
    item = result['candidates'][0]
    assert item['review_status'] == 'reviewed'
    assert item['action'] is None and item['eligibility_reason'] == 'passive_behavior_excluded'


@pytest.mark.parametrize('mutation', ['wrong_motion', 'invented_quote', 'quote_negated', 'idle_downgrade', 'skip'])
def test_agent_cannot_invent_motion_or_evidence_and_skips_do_not_fill_top_three(mutation):
    row = {**ROW, 'reasoning_content': 'A deer stands still. The deer does not nod. The deer walks across a clearing.'}
    def mutate(result):
        action = result.actions[0]
        if mutation in {'wrong_motion', 'quote_negated'}:
            action.primitive = 'head_nod'
        if mutation == 'invented_quote':
            action.evidence_excerpt = 'A deer walks toward a rabbit.'
        if mutation == 'quote_negated':
            action.evidence_excerpt = 'The deer does not nod.'
        if mutation == 'idle_downgrade':
            action.primitive = 'stand_hold'; action.evidence_excerpt = 'A deer stands still.'
        if mutation == 'skip':
            action.decision = 'skip'; action.primitive = None
    rows = [{**row, 'source': f's3://test-segments/{i}.mp4'} for i in range(4)]
    client, _, _ = make_client(Upstream(rows), agent=Agent(mutate=mutate))
    with client:
        result = search(client)
    compatible = [c for c in result['candidates'] if c['action']]
    assert [c['rank'] for c in compatible[:3]] == [2, 3, 4]
    assert all(c['action']['primitive'] == 'short_walk' for c in compatible)


def test_agent_cannot_bypass_provenance_or_exact_review_vetoes():
    changed = {**ROW, 'reasoning_content': 'A deer walks.'}
    def force(result):
        result.actions[0].decision = 'imitate'
        result.actions[0].primitive = 'short_walk'
        result.actions[0].evidence_excerpt = changed['reasoning_content']
    client, _, _ = make_client(Upstream([changed]), manifest=[reviewed()], agent=Agent(mutate=force))
    with client:
        item = search(client)['candidates'][0]
    assert item['action'] is None and item['eligibility_reason'] == 'reference_changed'


def test_agent_inputs_and_output_do_not_expose_private_configuration_or_sources():
    agent = Agent()
    row = {**ROW, 'reasoning_content': 'A deer walks. s3://private/file.mp4 test-secret test-user https://vss.invalid'}
    client, _, _ = make_client(Upstream([row]), agent=agent)
    with client:
        result = search(client)
    combined = json.dumps(agent.calls) + json.dumps(result)
    for forbidden in ('s3://', 'test-secret', 'test-user', 'https://vss.invalid'):
        assert forbidden not in combined


def test_cancel_inflight_planning_and_reuse_encounter_id_without_stale_plan():
    async def scenario():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        class Slow(EncounterAgent):
            slow = True
            async def decide(self, context, schema):
                if self.slow:
                    entered.set()
                    try: await asyncio.sleep(60)
                    finally: cancelled.set()
                return await super().decide(context, schema)
        agent = Slow()
        app = create_app(SETTINGS, httpx.MockTransport(Upstream()), Manifest(), agent)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            await client.get('/demo-api/health')
            task = asyncio.create_task(client.post('/demo-api/encounter-plan', json=PAYLOAD))
            await asyncio.wait_for(entered.wait(), 1)
            assert (await client.post('/demo-api/encounters/encounter-01/cancel')).status_code == 200
            assert (await task).status_code == 409 and cancelled.is_set()
            assert not app.state.encounter_service.plans
            agent.slow = False
            first = (await client.post('/demo-api/encounter-plan', json=PAYLOAD)).json()
            second = (await client.post('/demo-api/encounter-plan', json=PAYLOAD)).json()
            assert first['plan_id'] != second['plan_id']
            assert (await client.post('/demo-api/search', json={**PAYLOAD, 'plan_id': first['plan_id']})).status_code == 409
            assert (await client.post('/demo-api/search', json={**PAYLOAD, 'plan_id': second['plan_id']})).status_code == 200
        await app.state.encounter_service.close(); await app.state.vss.close()
    asyncio.run(scenario())


def test_encounter_timeout_cancels_agent_and_does_not_create_replay(monkeypatch):
    import ranger_duck.app as module
    monkeypatch.setattr(module, 'ENCOUNTER_TIMEOUT', 0.01)
    class Slow(EncounterAgent):
        async def decide(self, context, schema):
            await asyncio.sleep(1)
            return await super().decide(context, schema)
    client, upstream, _ = make_client(agent=Slow())
    with client:
        assert client.post('/demo-api/search', json=PAYLOAD).json()['error']['code'] == 'encounter_timeout'
        assert client.post('/demo-api/search', json={**PAYLOAD, 'mode': 'replay'}).status_code == 409
    assert not upstream.requests
