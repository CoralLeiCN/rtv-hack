import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from ranger_duck.evaluation import Case, Suite, evaluate, file_hash, load_suite, score
from ranger_duck.evidence import caption_hash


def case(**changes):
    return Case.model_validate({'id': 'cat-walk', 'animal': 'cat', 'evidence_kind': 'supplied_caption',
        'caption': 'A cat walks forward.', 'challenge': 'supported', 'expected_actions': ['short_walk'],
        **changes})


def test_scoring_counts_wrong_actions_misses_and_wrong_roles():
    expected = case(expected_grounding='caption_roles', expected_companion='standing')
    assert score(expected, {'action': None}, 1)['missed_action']
    wrong = score(expected, {'action': {'primitive': 'sit_cycle'}}, 1)
    assert wrong['false_selection'] and wrong['missed_action'] and wrong['role_error'] and not wrong['passed']
    skipped = case(id='rejected', expected_actions=[])
    assert score(skipped, {'action': None}, 1)['passed']
    assert score(skipped, {'action': {'primitive': 'short_walk'}}, 1)['false_selection']


def test_reviewed_video_requires_viewing_confirmation_and_unchanged_bytes_and_caption(tmp_path):
    media = tmp_path / 'synthetic-fixture.mp4'
    media.write_bytes(b'Fixture bytes only; this test does not validate real footage.')
    entry = case().model_dump()
    entry.update(evidence_kind='reviewed_video', video={
        'path': str(media), 'sha256': file_hash(media), 'caption_sha256': caption_hash(entry['caption']),
        'start_sec': 0., 'end_sec': 1.,
        'source_url': 'https://fixture.invalid/video', 'source_revision': 'fixture-revision',
        'licence': 'fixture', 'caption_model': 'fixture', 'caption_revision': 'fixture',
        'review_method': 'agent_sampled_frames',
        'reviewed_by': 'fixture reviewer', 'review_note': 'Synthetic test binding', 'confirmed_viewed': True})
    path = tmp_path / 'suite.json'
    def save(item):
        path.write_text(json.dumps({'version': 1, 'cases': [item]}))
    save(entry)
    assert len(load_suite(path).cases) == 1
    changed = deepcopy(entry)
    changed['video']['confirmed_viewed'] = False
    save(changed)
    with pytest.raises(ValueError):
        load_suite(path)
    changed = deepcopy(entry)
    changed['caption'] += ' Changed.'
    save(changed)
    with pytest.raises(ValueError):
        load_suite(path)
    save(entry)
    media.write_bytes(b'Replaced fixture')
    with pytest.raises(ValueError):
        load_suite(path)


def test_evaluation_uses_production_validation_and_never_sends_expected_labels():
    class Agent:
        available = True
        async def decide(self, context, schema):
            text = json.dumps(context)
            assert 'expected_actions' not in text and 'reviewed_by' not in text
            assert 'source_url' not in text and 'media://' not in text
            assert 'evaluation_failed' not in text
            return schema.model_validate({'summary': 'Fixture decision', 'actions': [
                {'candidate_id': candidate['candidate_id'], 'decision': 'imitate', 'primitive': 'short_walk',
                 'evidence_excerpt': 'invented quote', 'reason': 'Fixture', 'role_plan': None}
                for candidate in context['candidates']]})
    report = asyncio.run(evaluate(Suite(version=1, cases=[case()]), Agent(), repeats=2))
    assert report['groups']['supplied_caption']['attempts'] == 2
    assert report['groups']['supplied_caption']['missed_actions'] == 2
    assert report['groups']['reviewed_video']['status'] == 'not_run'
    assert report['groups']['reviewed_video']['coverage']['missing']
    assert all(row['selected'] is None and not row['passed'] for row in report['results'])


def test_model_errors_are_failures_even_for_expected_rejections():
    class Agent:
        available = True
        async def decide(self, context, schema):
            raise RuntimeError('private-token')
    report = asyncio.run(evaluate(Suite(version=1, cases=[case(expected_actions=[])]), Agent()))
    group = report['groups']['supplied_caption']
    assert group['errors'] == 1 and group['passed'] == 0
    assert group['false_selection_rate'] is None and group['missed_action_rate'] is None
    assert 'private-token' not in json.dumps(report)


def test_bundled_suite_covers_actions_species_and_semantic_challenges():
    from ranger_duck.evaluation import coverage
    suite = load_suite(Path(__file__).parents[2] / 'evaluation' / 'caption-cases.json')
    assert not coverage(suite.cases)['missing']
    assert all(case.evidence_kind == 'supplied_caption' for case in suite.cases)
    with pytest.raises(ValueError):
        Suite(version=1, cases=[suite.cases[0], suite.cases[0]])
