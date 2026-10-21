"""Decision ownership and evidence boundaries; agent replies are explicit fixtures."""
import pytest

from ranger_duck.encounter_agent import RunActionsDecision
from test_backend import ROW, reviewed
from test_runs import RunAgent, setup, start, search, outcome, report


class DecisionAgent(RunAgent):
    def __init__(self, primitive='short_walk', mutate=None):
        super().__init__()
        self.primitive, self.change = primitive, mutate

    async def decide(self, context, schema):
        if schema is not RunActionsDecision:
            return await super().decide(context, schema)
        self.calls.append(context)
        data = {'summary': 'Explicit fixture decision.', 'actions': [{
            'candidate_id': c['candidate_id'], 'decision': 'imitate' if self.primitive else 'skip',
            'primitive': self.primitive, 'evidence_excerpt': c['caption'] if self.primitive else '',
            'reason': 'Use the supported observed behavior.', 'role_plan': None,
        } for c in context['candidates']]}
        if self.change:
            self.change(data)
        return schema.model_validate(data)


@pytest.mark.parametrize('caption,primitive', [
    ('A brown cat is rolling on the brown surface and then walks away.', 'short_walk'),
    ('The tabby cat ambles toward the doorway.', 'short_walk'),
    ('A cat walks over and sits down.', 'sit_cycle'),
])
def test_agent_selects_from_all_capabilities_without_legacy_phrase_veto(monkeypatch, caption, primitive):
    def forbidden(*args, **kwargs):
        raise AssertionError('Runtime planning must not call the legacy caption classifier')
    monkeypatch.setattr('ranger_duck.evidence.classify_interaction', forbidden)
    monkeypatch.setattr('ranger_duck.interaction.classify_interaction', forbidden)
    agent = DecisionAgent(primitive)
    client, _, _ = setup(agent=agent, clips=[{**ROW, 'reasoning_content': caption}])
    with client:
        start(client)
        result = search(client)
    supplied = agent.calls[-1]['candidates'][0]
    assert agent.calls[-1]['original_prompt'] == 'Meet the cat calmly'
    assert set(supplied['allowed_actions']) == {'short_walk', 'ground_pick', 'head_nod', 'sit_cycle'}
    assert 'preferred_action' not in supplied
    candidate = result['queue'][0]['candidate']
    assert candidate['action']['primitive'] == primitive
    assert candidate['evidence_excerpt'] == caption
    assert candidate['action_basis'] == 'video_caption' and candidate['review_status'] == 'unreviewed'


def test_agent_can_skip_a_keyword_match_and_explain_why():
    client, _, _ = setup(agent=DecisionAgent(None), clips=[{**ROW, 'reasoning_content': 'A cat walks.'}])
    with client:
        start(client)
        result = search(client)
    assert not result['queue']
    assert result['candidates'][0]['eligibility_reason'] == 'agent_skipped'


def test_agent_can_reuse_only_reference_with_actual_outcomes_in_context():
    agent = DecisionAgent()
    client, _, _ = setup(agent=agent, clips=[{**ROW, 'reasoning_content': 'A cat walks away.'}])
    with client:
        start(client, adaptive=True)
        first = search(client)
        assert outcome(client, report(first, first))['status'] == 'needs_plan'
        second = search(client)
    context = agent.calls[-1]
    assert context['candidates'][0]['recently_used'] is True
    assert context['history'][0]['outcome']['status'] == 'completed'
    assert second['queue'][0]['candidate']['action'] == first['queue'][0]['candidate']['action']


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'unknown'])
def test_batch_requires_exactly_one_decision_per_supplied_candidate(mutation):
    def change(data):
        if mutation == 'missing':
            data['actions'] = []
        elif mutation == 'duplicate':
            data['actions'] *= 2
        else:
            data['actions'][0]['candidate_id'] = 'rank-unknown'
    client, _, _ = setup(agent=DecisionAgent(mutate=change), clips=[{**ROW, 'reasoning_content': 'A cat walks.'}])
    with client:
        start(client)
        planned = client.post('/demo-api/runs/run-1/plan', json={}).json()
        result = client.post('/demo-api/runs/run-1/search', json={'plan_id': planned['plan_id']})
    assert result.status_code == 502 and result.json()['error']['code'] == 'invalid_agent_action'


def test_agent_cannot_replace_exact_review_with_another_available_controller_motion():
    clip = {**ROW, 'reasoning_content': 'A cat walks over and feeds.'}
    client, _, _ = setup(agent=DecisionAgent('ground_pick'), clips=[clip],
                          manifest=[reviewed(clip, animal='cat', behavior='walking')])
    with client:
        start(client)
        result = search(client)
    assert not result['queue']
    assert result['candidates'][0]['eligibility_reason'] == 'agent_action_unverified'


def test_evidence_id_changes_with_exact_caption_or_interval():
    ids = []
    for change in [{}, {'reasoning_content': 'A cat walks away!'}, {'segment_end_sec': 6}]:
        clip = {**ROW, 'reasoning_content': 'A cat walks away.', **change}
        client, _, _ = setup(agent=DecisionAgent(), clips=[clip])
        with client:
            start(client)
            ids.append(search(client)['queue'][0]['candidate']['action']['evidence_id'])
    assert len(set(ids)) == 3
