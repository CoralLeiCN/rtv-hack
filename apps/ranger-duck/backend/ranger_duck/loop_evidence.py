"""Active clip eligibility shared with Encounter evidence grounding."""
from .interaction import ACTIVE_PRIMITIVES


def annotate_response(manifest, segment, animal: str) -> dict:
    annotation = manifest.annotate_interaction(segment, animal, animal, allowed_primitives=ACTIVE_PRIMITIVES)
    action = annotation['action']
    return {'eligibility_reason': annotation['eligibility_reason'],
            'allowed_actions': [action['primitive']] if action else [],
            'evidence_id': action['evidence_id'] if action else None,
            'observed_behavior': annotation.get('inferred_behavior') or annotation.get('reviewed_behavior'),
            'evidence_basis': annotation.get('action_basis')}
