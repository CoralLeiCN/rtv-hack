"""Cancelable, session-scoped query and caption-action planning for Encounter."""
import asyncio
from dataclasses import dataclass
import secrets
import time

from .encounter_agent import EncounterQueryDecision, EncounterActionsDecision, RunActionsDecision, combined_behavior_query
from .errors import DemoError
from .interaction import ACTIVE_PRIMITIVES, classify_interaction
from .session import COOKIE_NAME
from .capture import Capture
from .loop_agent import COMPANION_BEHAVIORS, DUCK_ROLE_ACTIONS
from .interaction import has_species_pair

PLAN_TIMEOUT = 60
ENCOUNTER_TIMEOUT = 180


@dataclass
class EncounterPlan:
    id: str
    encounter_id: str
    scenario_id: str
    broaden: bool
    query: str
    reason: str
    expires: float


class EncounterService:
    def __init__(self, registry, manifest, public_text, agent, capture=None):
        self.capture = capture or Capture()
        self.registry, self.manifest, self.public_text, self.agent = registry, manifest, public_text, agent
        self.plans: dict[str | tuple[str, str], EncounterPlan] = {}
        self.tasks: dict[str | tuple[str, str], tuple[str, asyncio.Task]] = {}

    @staticmethod
    def key(owner, scope=None):
        # Legacy endpoints retain their owner-wide scope. Unified runs isolate
        # each tab's query and cancellation under the same browser cookie.
        return (owner, scope) if scope is not None else owner

    def owner(self, request):
        self.registry._prune()
        for key in list(self.plans):
            owner = key[0] if isinstance(key, tuple) else key
            if owner not in self.registry.sessions or self.plans[key].expires < time.monotonic():
                self.plans.pop(key, None)
        for key in list(self.tasks):
            owner = key[0] if isinstance(key, tuple) else key
            if owner not in self.registry.sessions:
                _, task = self.tasks.pop(key)
                task.cancel()
        return self.registry.session(request.cookies.get(COOKIE_NAME))

    def require_agent(self):
        if not self.agent.available:
            raise DemoError('agent_unavailable', 'The signed-in agent is unavailable. Check Codex login on the agent host, then retry.', 503)

    def cancel(self, owner, encounter_id, *, scope=None):
        key = self.key(owner, scope)
        active = self.tasks.get(key)
        if active and active[0] == encounter_id:
            self.tasks.pop(key, None)
            active[1].cancel()
        plan = self.plans.get(key)
        if plan and plan.encounter_id == encounter_id:
            self.plans.pop(key, None)

    async def close(self):
        tasks = [item[1] for item in self.tasks.values()]
        self.tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, owner, encounter_id, operation, request, timeout, *, scope=None):
        key = self.key(owner, scope)
        prior = self.tasks.pop(key, None)
        if prior:
            prior[1].cancel()
        async def captured():
            with self.capture.scope(self.capture.run_id(owner, 'encounter:' + encounter_id)):
                self.capture.emit('encounter.request', {'encounter_id': encounter_id})
                try:
                    return await operation()
                except BaseException as error:
                    self.capture.emit('encounter.failed', error_type=type(error).__name__)
                    raise
        task = asyncio.create_task(captured())
        self.tasks[key] = (encounter_id, task)

        async def watch_disconnect():
            while not task.done():
                if await request.is_disconnected():
                    task.cancel()
                    return
                await asyncio.sleep(0.1)

        watcher = asyncio.create_task(watch_disconnect())
        try:
            result = await asyncio.wait_for(task, timeout)
            if self.tasks.get(key) != (encounter_id, task):
                raise DemoError('encounter_cancelled', 'The encounter was stopped or replaced.', 409)
            self.registry._prune()
            if owner not in self.registry.sessions:
                raise DemoError('encounter_session_expired', 'Reconnect and plan the encounter again.', 409)
            return result
        except asyncio.CancelledError:
            raise DemoError('encounter_cancelled', 'The encounter was stopped or replaced.', 409) from None
        except TimeoutError:
            raise DemoError('encounter_timeout', 'The agent encounter exceeded its deadline. Retry when ready.', 504, True) from None
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            if self.tasks.get(key) == (encounter_id, task):
                self.tasks.pop(key, None)

    async def plan(self, owner, encounter_id, scenario, broaden, *, intent='', history=None, scope=None):
        self.require_agent()
        context = {'task': 'encounter_query', 'animal': scenario['animal'], 'broaden': broaden,
                   'encounter': {key: scenario[key] for key in ('id', 'label', 'interaction', 'behavior_hint', 'description')}}
        if intent or history:
            context.update(original_prompt=intent, history=history or [])
        choice = await self.agent.decide(context, EncounterQueryDecision)
        query = combined_behavior_query(self.public_text(choice.query, 280),
                                        self.public_text(choice.individual_query, 280), scenario['animal'])
        reason = self.public_text(choice.reason, 800).strip()
        if not reason:
            raise DemoError('invalid_agent_query', 'The agent query needs an explanation. Retry planning.', 502)
        plan = EncounterPlan(secrets.token_urlsafe(24), encounter_id, scenario['id'], broaden,
                             query, reason, time.monotonic() + min(self.registry.ttl, 300))
        self.plans[self.key(owner, scope)] = plan
        return plan

    def planned(self, owner, plan_id, encounter_id, scenario_id, broaden, *, scope=None):
        plan = self.plans.get(self.key(owner, scope))
        if (not plan or plan.id != plan_id or plan.encounter_id != encounter_id or plan.scenario_id != scenario_id
                or plan.broaden != broaden or plan.expires <= time.monotonic()):
            raise DemoError('encounter_plan_expired', 'Plan this encounter again before searching.', 409)
        return plan

    async def actions(self, segments, scenario, query, *, role_plans=False, history=None, recent=()):
        """Agent creates proposals; exact reviews and caption checks bound them."""
        self.require_agent()
        choices, annotations = [], []
        for segment in segments:
            annotation = self.manifest.annotate_interaction(segment, scenario['animal'], scenario['interaction_partner'],
                                                           allowed_primitives=ACTIVE_PRIMITIVES)
            annotations.append(annotation)
            action = annotation['action']
            if action and (segment.parent, segment.start, segment.end) in recent:
                annotation.update(action=None, action_basis=None, eligibility_reason='recent_clip')
                action = None
            # A bounded imitation cannot wait on an arbitrarily long reference.
            if action and segment.end - segment.start > 120:
                annotation.update(action=None, action_basis=None, eligibility_reason='clip_too_long')
                action = None
            choices.append({'candidate_id': f'rank-{segment.rank}', 'rank': segment.rank,
                            'caption': self.public_text(segment.caption),
                            'allowed_actions': [action['primitive']] if action else [],
                            'preferred_action': action['primitive'] if action else None,
                            'observed_behavior': annotation.get('inferred_behavior') or annotation.get('reviewed_behavior'),
                            'review_status': annotation['review_status'],
                            'unavailable_reason': None if action else annotation['eligibility_reason']})
        submitted = [choice for choice in choices if choice['allowed_actions']] if role_plans else choices
        if not submitted:
            return tuple(annotations), 'No active supported video motions were found.'
        context = {'task': 'encounter_actions', 'animal': scenario['animal'], 'query': query, 'candidates': submitted}
        if role_plans:
            context.update(history=history or [], allowed_companion_behaviors=COMPANION_BEHAVIORS[scenario['animal']],
                           encounter={key: scenario[key] for key in ('id', 'label', 'interaction', 'behavior_hint')})
        decision = await self.agent.decide(context, RunActionsDecision if role_plans else EncounterActionsDecision)
        identifiers = [item.candidate_id for item in decision.actions]
        if len(set(identifiers)) != len(identifiers) or any(value not in {c['candidate_id'] for c in submitted} for value in identifiers):
            raise DemoError('invalid_agent_action', 'The agent returned duplicate or unknown clip decisions. Retry planning.', 502)
        proposals = {item.candidate_id: item for item in decision.actions}
        output = []
        for choice, annotation in zip(choices, annotations):
            item = dict(annotation)
            proposal = proposals.get(choice['candidate_id'])
            item.update(action_planner='agent', agent_reason=None, evidence_excerpt=None)
            if not item['action']:
                # Review/provenance/content vetoes are never bypassed by an agent.
                output.append(item)
                continue
            if proposal:
                item['agent_reason'] = self.public_text(proposal.reason, 400)
            if not proposal or proposal.decision != 'imitate':
                item.update(action=None, action_basis=None, eligibility_reason='agent_skipped',
                            action_reason=item['agent_reason'] or 'The agent did not establish a supported action for this clip.')
                output.append(item)
                continue
            valid = proposal.primitive in choice['allowed_actions']
            if item['action_basis'] != 'reviewed':
                excerpt = proposal.evidence_excerpt.strip()
                grounded, _ = classify_interaction(excerpt, scenario['animal'], allowed_primitives=ACTIVE_PRIMITIVES)
                valid &= bool(excerpt and excerpt in choice['caption'] and grounded and grounded[1] == proposal.primitive)
                if valid:
                    item['evidence_excerpt'] = excerpt
            if not valid:
                item.update(action=None, action_basis=None, eligibility_reason='agent_action_unverified',
                            action_reason='The agent proposal did not match this clip’s supported behavior and exact caption evidence.')
            else:
                # The validated action retains its exact source-bound evidence ID,
                # bounded duration, review status, and canonical approximation.
                item['action_reason'] = f"{item['agent_reason']} {item['action_reason']}".strip()
                if role_plans:
                    role = self.role_plan(proposal, choice, scenario['animal'], item['action_basis'] == 'reviewed')
                    if role is None:
                        item.update(action=None, action_basis=None, eligibility_reason='agent_action_unverified',
                                    action_reason='The proposed video roles do not match this clip’s evidence.')
                    else:
                        item['role_plan'] = role
            output.append(item)
        return tuple(output), self.public_text(decision.summary, 800)

    def role_plan(self, proposal, choice, animal, reviewed=False):
        primitive = proposal.primitive
        behavior = {'short_walk': 'moving', 'ground_pick': 'feeding', 'head_nod': 'nodding', 'sit_cycle': 'sitting'}[primitive]
        supplied = proposal.role_plan
        if supplied is None or supplied.grounding == 'single_behavior':
            excerpt = proposal.evidence_excerpt if proposal.evidence_excerpt in choice['caption'] else choice['caption'][:800]
            return {'grounding': 'single_behavior', 'companion': {'subject': 'Unassigned scene companion', 'evidence': ''},
                    'duck': {'subject': f'The observed {animal}', 'evidence': self.public_text(excerpt or choice['caption'][:800], 800)},
                    'duck_behavior': behavior, 'companion_behavior': 'standing', 'companion_duration_ms': 3000, 'timing': 'together'}
        plan = supplied.model_dump()
        if (plan['grounding'] != 'caption_roles' or not has_species_pair(choice['caption'], animal)
                or plan['companion_behavior'] not in COMPANION_BEHAVIORS[animal]
                or DUCK_ROLE_ACTIONS.get(plan['duck_behavior']) != primitive
                or plan['companion']['subject'].strip().casefold() == plan['duck']['subject'].strip().casefold()
                or any(not plan[role]['subject'].strip() or not plan[role]['evidence'].strip()
                       or plan[role]['evidence'] not in choice['caption'] for role in ('companion', 'duck'))):
            return None
        observed, _ = classify_interaction(plan['duck']['evidence'], animal, allowed_primitives=ACTIVE_PRIMITIVES)
        if not reviewed and (not observed or observed[1] != primitive):
            return None
        companion = plan['companion_behavior']
        companion_primitives = {'standing': 'stand_hold', 'alert': 'stand_hold', 'hissing': 'stand_hold',
            'feeding': 'ground_pick', 'walking': 'short_walk', 'approach': 'short_walk',
            'greeting': 'short_walk', 'play': 'short_walk'}
        allowed = frozenset({companion_primitives[companion]}) if companion in companion_primitives else None
        companion_motion, companion_reason = classify_interaction(plan['companion']['evidence'], animal, allowed_primitives=allowed)
        if companion == 'retreat':
            if companion_reason != 'unsupported_retreat':
                return None
        elif not companion_motion:
            return None
        elif companion == 'hissing' and companion_motion[0] not in {'hissing_boundary', 'focal_hissing'}:
            return None
        elif companion == 'play' and companion_motion[0] != 'social_play':
            return None
        elif companion == 'greeting' and companion_motion[0] != 'social_approach':
            return None
        for role in ('companion', 'duck'):
            plan[role] = {key: self.public_text(value, 600) for key, value in plan[role].items()}
        plan['companion_duration_ms'] = 3000
        return plan
