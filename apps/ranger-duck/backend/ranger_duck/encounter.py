"""Cancelable, session-scoped query and caption-action planning for Encounter."""
import asyncio
from dataclasses import dataclass
import secrets
import time

from .encounter_agent import EncounterQueryDecision, EncounterActionsDecision, RunActionsDecision, combined_behavior_query
from .errors import DemoError
from .action_evidence import prepare_candidate, bind_action, ACTION_BEHAVIORS
from .session import COOKIE_NAME
from .capture import Capture
from .loop_agent import COMPANION_BEHAVIORS, DUCK_ROLE_ACTIONS

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

    async def actions(self, segments, scenario, query, *, role_plans=False, intent='', history=None, recent=()):
        """Luna interprets evidence; code enforces provenance and command contracts."""
        self.require_agent()
        choices, annotations, evidence_ids = [], [], []
        for segment in segments:
            annotation, allowed, evidence_id = prepare_candidate(self.manifest, segment, scenario['animal'])
            annotations.append(annotation)
            evidence_ids.append(evidence_id)
            choices.append({'candidate_id': f'rank-{segment.rank}', 'rank': segment.rank,
                            'caption': self.public_text(segment.caption),
                            'allowed_actions': allowed,
                            'observed_behavior': annotation.get('reviewed_behavior'),
                            'review_status': annotation['review_status'],
                            'recently_used': (segment.parent, segment.start, segment.end) in recent,
                            'unavailable_reason': None if allowed else annotation['eligibility_reason']})
        submitted = [choice for choice in choices if choice['allowed_actions']]
        if not submitted:
            return tuple(annotations), 'No references with valid provenance and review constraints were found.'
        context = {'task': 'encounter_actions', 'animal': scenario['animal'], 'query': query,
                   'candidates': submitted, 'original_prompt': intent, 'history': history or []}
        if role_plans:
            context.update(allowed_companion_behaviors=COMPANION_BEHAVIORS[scenario['animal']],
                           encounter={key: scenario[key] for key in ('id', 'label', 'interaction', 'behavior_hint')})
        decision = await self.agent.decide(context, RunActionsDecision if role_plans else EncounterActionsDecision)
        identifiers = [item.candidate_id for item in decision.actions]
        if len(set(identifiers)) != len(identifiers) or set(identifiers) != {c['candidate_id'] for c in submitted}:
            raise DemoError('invalid_agent_action', 'The agent must decide each supplied clip exactly once. Retry planning.', 502)
        proposals = {item.candidate_id: item for item in decision.actions}
        output = []
        for segment, choice, annotation, evidence_id in zip(segments, choices, annotations, evidence_ids):
            item = dict(annotation)
            proposal = proposals.get(choice['candidate_id'])
            item.update(action_planner='agent', agent_reason=None, evidence_excerpt=None)
            if not choice['allowed_actions']:
                output.append(item)
                continue
            item['agent_reason'] = self.public_text(proposal.reason, 400)
            if proposal.decision == 'skip':
                item.update(eligibility_reason='agent_skipped', action_reason=item['agent_reason'])
                output.append(item)
                continue
            reviewed = item['review_status'] == 'reviewed'
            excerpt = proposal.evidence_excerpt.strip()
            valid_quote = bool(excerpt and excerpt in choice['caption'] and excerpt in segment.caption)
            if proposal.primitive not in choice['allowed_actions'] or (not reviewed and not valid_quote):
                item.update(eligibility_reason='agent_action_unverified',
                            action_reason='The agent must select an available command and quote exact caption evidence.')
            else:
                item.update(action=bind_action(proposal.primitive, evidence_id),
                            action_basis='reviewed' if reviewed else 'video_caption',
                            eligibility_reason='reviewed_match' if reviewed else 'caption_behavior_match',
                            animal=scenario['animal'], evidence_excerpt=excerpt if valid_quote else None,
                            inferred_behavior=None if reviewed else ACTION_BEHAVIORS[proposal.primitive],
                            action_reason=item['agent_reason'])
                if role_plans:
                    role = self.role_plan(proposal, choice, scenario['animal'], segment.caption)
                    if role is None:
                        item.update(action=None, action_basis=None, eligibility_reason='agent_action_unverified',
                                    action_reason='The proposed video roles need exact quotes and compatible commands.')
                    else:
                        item['role_plan'] = role
                        if role['grounding'] == 'caption_roles':
                            item['interaction_partner'] = scenario['animal']
            output.append(item)
        return tuple(output), self.public_text(decision.summary, 800)

    def role_plan(self, proposal, choice, animal, original_caption):
        primitive = proposal.primitive
        behavior = {'short_walk': 'moving', 'ground_pick': 'feeding', 'head_nod': 'nodding', 'sit_cycle': 'sitting'}[primitive]
        supplied = proposal.role_plan
        if supplied is None or supplied.grounding == 'single_behavior':
            excerpt = proposal.evidence_excerpt if proposal.evidence_excerpt in choice['caption'] else choice['caption'][:800]
            return {'grounding': 'single_behavior', 'companion': {'subject': 'Unassigned scene companion', 'evidence': ''},
                    'duck': {'subject': f'The observed {animal}', 'evidence': self.public_text(excerpt or choice['caption'][:800], 800)},
                    'duck_behavior': behavior, 'companion_behavior': 'standing', 'companion_duration_ms': 3000, 'timing': 'together'}
        plan = supplied.model_dump()
        if (plan['grounding'] != 'caption_roles'
                or plan['companion_behavior'] not in COMPANION_BEHAVIORS[animal]
                or DUCK_ROLE_ACTIONS.get(plan['duck_behavior']) != primitive
                or plan['companion']['subject'].strip().casefold() == plan['duck']['subject'].strip().casefold()
                or any(not plan[role]['subject'].strip() or not plan[role]['evidence'].strip()
                       or plan[role]['evidence'] not in choice['caption']
                       or plan[role]['evidence'] not in original_caption for role in ('companion', 'duck'))):
            return None
        for role in ('companion', 'duck'):
            plan[role] = {key: self.public_text(value, 600) for key, value in plan[role].items()}
        plan['companion_duration_ms'] = 3000
        return plan
