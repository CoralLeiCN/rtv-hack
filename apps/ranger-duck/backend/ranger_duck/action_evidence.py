"""Structural evidence checks; the decision agent interprets caption meaning."""
import hashlib
import json

from .evidence import caption_hash
from .loop_agent import LIMITS

ACTIVE_ACTIONS = ('short_walk', 'ground_pick', 'head_nod', 'sit_cycle')
ACTION_BEHAVIORS = {'short_walk': 'walking', 'ground_pick': 'feeding',
                    'head_nod': 'nodding', 'sit_cycle': 'sitting'}


def prepare_candidate(manifest, segment, animal):
    annotation = manifest.annotate(segment, animal)
    reviewed_action = annotation['action']
    annotation.update(action=None, action_basis=None, inferred_behavior=None,
                      action_reason=None, interaction_partner=None)
    allowed, evidence_id = [], None
    if manifest.warning:
        annotation['eligibility_reason'] = 'invalid_review_manifest'
    elif annotation['eligibility_reason'] in {'not_reviewed', 'reviewed_match'}:
        if segment.end - segment.start > 120:
            annotation['eligibility_reason'] = 'clip_too_long'
        elif reviewed_action and reviewed_action['primitive'] not in ACTIVE_ACTIONS:
            annotation['eligibility_reason'] = 'passive_behavior_excluded'
        elif reviewed_action:
            allowed = [reviewed_action['primitive']]
            evidence_id = reviewed_action['evidence_id']
        else:
            allowed = list(ACTIVE_ACTIONS)
            binding = json.dumps([segment.source, segment.parent, segment.start, segment.end,
                                  caption_hash(segment.caption)], separators=(',', ':'))
            evidence_id = 'caption-' + hashlib.sha256(binding.encode()).hexdigest()[:32]
            annotation['eligibility_reason'] = 'awaiting_agent'
    return annotation, allowed, evidence_id


def bind_action(primitive, evidence_id):
    return {'primitive': primitive, 'evidence_id': evidence_id, 'max_duration_ms': LIMITS[primitive]}
