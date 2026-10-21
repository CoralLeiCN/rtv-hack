"""Provenance and review constraints for the legacy Loop agent."""
from .action_evidence import prepare_candidate


def annotate_response(manifest, segment, animal: str) -> dict:
    annotation, allowed, evidence_id = prepare_candidate(manifest, segment, animal)
    return {'eligibility_reason': annotation['eligibility_reason'],
            'allowed_actions': allowed, 'evidence_id': evidence_id,
            'observed_behavior': annotation.get('reviewed_behavior'),
            'evidence_basis': 'reviewed' if allowed and annotation['review_status'] == 'reviewed' else None}
