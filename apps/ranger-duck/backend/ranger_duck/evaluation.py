"""Repeatable semantic evaluations through the production action planner.

Expected labels and private video provenance never enter the agent context.
Supplied-caption cases measure interpretation only, not video understanding.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .encounter import EncounterService, ENCOUNTER_TIMEOUT
from .encounter_agent import RunActionsDecision
from .evidence import Manifest, Segment, caption_hash, safe_text
from .loop_agent import ActivePrimitive, CodexAgent, CompanionBehavior
from .session import ClipRegistry

ACTIONS = {'short_walk', 'ground_pick', 'head_nod', 'sit_cycle'}
CHALLENGES = {'supported', 'paired', 'negation', 'uncertainty', 'wrong_species', 'unsupported'}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class VideoEvidence(Strict):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    caption_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    start_sec: float = Field(ge=0, allow_inf_nan=False)
    end_sec: float = Field(gt=0, allow_inf_nan=False)
    source_url: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    licence: str = Field(min_length=1)
    caption_model: str = Field(min_length=1)
    caption_revision: str = Field(min_length=1)
    review_method: Literal['human_video', 'agent_sampled_frames']
    reviewed_by: str = Field(min_length=1)
    review_note: str = Field(min_length=1)
    confirmed_viewed: Literal[True]

    @model_validator(mode='after')
    def interval(self):
        if self.end_sec <= self.start_sec:
            raise ValueError('Invalid video interval')
        return self


class Case(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    animal: Literal['cat', 'deer']
    evidence_kind: Literal['supplied_caption', 'reviewed_video']
    caption: str = Field(min_length=1, max_length=4000)
    challenge: Literal['supported', 'paired', 'negation', 'uncertainty', 'wrong_species', 'unsupported']
    expected_actions: list[ActivePrimitive] = Field(max_length=4)
    expected_grounding: Literal['single_behavior', 'caption_roles'] | None = None
    expected_companion: CompanionBehavior | None = None
    expected_duck_evidence: str | None = None
    video: VideoEvidence | None = None

    @model_validator(mode='after')
    def bound_evidence(self):
        if len(set(self.expected_actions)) != len(self.expected_actions):
            raise ValueError('Duplicate expected actions')
        if (self.evidence_kind == 'reviewed_video') != (self.video is not None):
            raise ValueError('Reviewed video requires bound source evidence')
        if self.video and self.video.caption_sha256 != caption_hash(self.caption):
            raise ValueError('Review caption changed')
        if self.expected_duck_evidence and self.expected_duck_evidence not in self.caption:
            raise ValueError('Expected actor quote must occur in the caption')
        if not self.expected_actions and any((self.expected_grounding, self.expected_companion, self.expected_duck_evidence)):
            raise ValueError('Rejected cases cannot expect executable roles')
        return self


class Suite(Strict):
    version: Literal[1]
    cases: list[Case] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError('Duplicate evaluation case IDs')
        return self


def file_hash(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def load_suite(path):
    suite = Suite.model_validate_json(Path(path).read_text())
    for case in suite.cases:
        if case.video:
            video = Path(case.video.path)
            if not video.is_absolute() or not video.is_file() or file_hash(video) != case.video.sha256:
                raise ValueError('Reviewed video is missing or changed')
    return suite


def coverage(cases, kind='supplied_caption'):
    actions = {action for case in cases for action in case.expected_actions}
    species = {case.animal for case in cases}
    challenges = {case.challenge for case in cases}
    # Negation is a caption-language challenge, not a physical video action.
    required = CHALLENGES if kind == 'supplied_caption' else {'supported', 'paired', 'unsupported', 'uncertainty', 'wrong_species'}
    missing = ([f'species:{animal}' for animal in sorted({'cat', 'deer'} - species)] +
               [f'action:{action}' for action in sorted(ACTIONS - actions)] +
               [f'challenge:{challenge}' for challenge in sorted(required - challenges)])
    return {'cases': len(cases), 'species': dict(Counter(case.animal for case in cases)),
            'actions': dict(Counter(action for case in cases for action in case.expected_actions)),
            'challenges': dict(Counter(case.challenge for case in cases)), 'missing': missing}


def score(case, annotation, repeat):
    action = annotation.get('action')
    selected = action['primitive'] if action else None
    correct = selected in case.expected_actions if selected else not case.expected_actions
    role = annotation.get('role_plan') or {}
    role_error = bool(selected and (
        (case.expected_grounding and role.get('grounding') != case.expected_grounding) or
        (case.expected_companion and role.get('companion_behavior') != case.expected_companion) or
        (case.expected_duck_evidence and case.expected_duck_evidence not in role.get('duck', {}).get('evidence', ''))))
    return {'id': case.id, 'repeat': repeat, 'evidence_kind': case.evidence_kind,
            'selected': selected, 'expected_active': bool(case.expected_actions),
            'false_selection': bool(selected and not correct),
            'missed_action': bool(case.expected_actions and not correct),
            'role_error': role_error, 'passed': bool(correct and not role_error), 'error': None}


async def evaluate(suite, agent, repeats=1):
    service = EncounterService(ClipRegistry(1800, 1), Manifest(), safe_text, agent)
    results = []
    try:
        for repeat in range(1, repeats + 1):
            # Keep modalities separate so supplied captions cannot inflate a
            # reviewed-video score. Production batches contain at most 15 clips.
            for kind in ('supplied_caption', 'reviewed_video'):
                for animal in ('cat', 'deer'):
                    cases = [case for case in suite.cases if case.animal == animal and case.evidence_kind == kind]
                    for offset in range(0, len(cases), 15):
                        batch = cases[offset:offset + 15]
                        # These are local evaluation identities, never issued as
                        # archive capabilities. Real clips retain their exact
                        # source-relative interval; only text fixtures use 0–5.
                        segments = tuple(Segment('media://' + str(uuid5(NAMESPACE_URL,
                            case.video.sha256 if case.video else 'eval:' + case.id)),
                            'media://' + str(uuid5(NAMESPACE_URL,
                            case.video.source_url + '@' + case.video.source_revision if case.video else 'eval-parent:' + case.id)),
                            case.caption, case.video.start_sec if case.video else 0.,
                            case.video.end_sec if case.video else 5., None, None, rank=index + 1)
                            for index, case in enumerate(batch))
                        scenario = {'id': animal + '-evaluation', 'animal': animal, 'label': 'Evidence evaluation',
                                    'interaction': 'copy supported observed behavior', 'behavior_hint': 'standing'}
                        try:
                            annotations, _ = await asyncio.wait_for(service.actions(segments, scenario,
                                f'Observed {animal} behavior', role_plans=True,
                                intent=f'Copy a supported movement from the {animal}. Use two observed roles when clearly supported.'),
                                timeout=ENCOUNTER_TIMEOUT)
                            results.extend(score(case, annotation, repeat) for case, annotation in zip(batch, annotations))
                        except Exception:
                            # Invalid model output/timeouts count as failures, not
                            # correct rejections or excluded observations.
                            results.extend({'id': case.id, 'repeat': repeat, 'evidence_kind': kind,
                                'selected': None, 'expected_active': bool(case.expected_actions),
                                'false_selection': False, 'missed_action': bool(case.expected_actions),
                                'role_error': False, 'passed': False, 'error': 'evaluation_failed'} for case in batch)
    finally:
        await service.close()
    groups = {}
    for kind in ('supplied_caption', 'reviewed_video'):
        rows = [row for row in results if row['evidence_kind'] == kind]
        selected = sum(row['selected'] is not None for row in rows)
        positives = sum(row['expected_active'] for row in rows)
        false = sum(row['false_selection'] for row in rows)
        missed = sum(row['missed_action'] for row in rows)
        groups[kind] = {'status': 'evaluated' if rows else 'not_run', 'attempts': len(rows),
            'passed': sum(row['passed'] for row in rows), 'errors': sum(row['error'] is not None for row in rows),
            'false_selections': false, 'missed_actions': missed,
            'role_errors': sum(row['role_error'] for row in rows),
            'review_methods': dict(Counter(case.video.review_method for case in suite.cases
                                           if case.evidence_kind == kind and case.video)),
            'false_selection_rate': false / selected if selected else None,
            'missed_action_rate': missed / positives if positives else None,
            'coverage': coverage([case for case in suite.cases if case.evidence_kind == kind], kind)}
    return {'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'model': 'gpt-6-luna',
            'instructions_sha256': caption_hash(RunActionsDecision.agent_instructions),
            'repeats': repeats, 'groups': groups, 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'run'])
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='New owner-only JSON report; existing files are never overwritten')
    parser.add_argument('--repeats', type=int, choices=range(1, 6), default=1)
    parser.add_argument('--require-video-coverage', action='store_true')
    args = parser.parse_args()
    try:
        suite = load_suite(args.suite)
        groups = {kind: coverage([case for case in suite.cases if case.evidence_kind == kind], kind)
                  for kind in ('supplied_caption', 'reviewed_video')}
        if args.command == 'validate':
            print(json.dumps(groups, sort_keys=True))
            return 2 if args.require_video_coverage and groups['reviewed_video']['missing'] else 0
        if args.output is None or args.output.exists():
            raise ValueError('Select a new output file')
        agent = CodexAgent()
        if not agent.available:
            raise ValueError('Agent executable unavailable')
        report = asyncio.run(evaluate(suite, agent, args.repeats))
        report['suite_sha256'] = file_hash(args.suite)
        # Reserve a private file before writing; no raw captions, private paths
        # or source URLs are included in the report or console output.
        with os.fdopen(os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
        print(json.dumps(report['groups'], sort_keys=True))
        incomplete = args.require_video_coverage and groups['reviewed_video']['missing']
        return 2 if incomplete or any(not row['passed'] for row in report['results']) else 0
    except (OSError, ValueError):
        print('Evaluation failed. Check suite bindings, video files, output permissions and agent availability.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
