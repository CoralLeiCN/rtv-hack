"""Clip eligibility for duck responses, independent of encounter imitation."""
import hashlib
import json

from .evidence import caption_hash
from .loop_agent import LIMITS


def annotate_response(manifest, segment, animal: str) -> dict:
    """Preserve provenance/review vetoes without filtering caption content."""
    review = manifest.annotate(segment, animal)
    result = {'allowed_actions': [], 'evidence_id': None,
              'observed_behavior': None, 'evidence_basis': None}
    if manifest.warning:
        return {**result, 'eligibility_reason': 'invalid_review_manifest'}
    if review['eligibility_reason'] in {'incomplete_metadata', 'reference_changed', 'species_mismatch'}:
        return {**result, 'eligibility_reason': review['eligibility_reason']}
    # Caption content is context for Codex, not an imitation eligibility gate.
    # No pair, species-presence, or recognized behavior classifier runs here.
    binding = json.dumps([segment.source, segment.parent, segment.start, segment.end,
                          caption_hash(segment.caption)], separators=(',', ':'))
    return {'eligibility_reason': 'caption_response_match',
            'allowed_actions': list(LIMITS),
            'evidence_id': 'caption-' + hashlib.sha256(binding.encode()).hexdigest()[:32],
            'observed_behavior': 'caption_context', 'evidence_basis': 'video_caption'}
