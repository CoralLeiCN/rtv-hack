"""Cancelable, session-scoped query and caption-action planning for Encounter."""
import asyncio
from dataclasses import dataclass
import secrets
import time

from .encounter_agent import EncounterQueryDecision, EncounterActionsDecision, combined_behavior_query
from .errors import DemoError
from .interaction import classify_interaction
from .session import COOKIE_NAME

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
    def __init__(self, registry, manifest, public_text, agent):
        self.registry, self.manifest, self.public_text, self.agent = registry, manifest, public_text, agent
        self.plans: dict[str, EncounterPlan] = {}
        self.tasks: dict[str, tuple[str, asyncio.Task]] = {}

    def owner(self, request):
        self.registry._prune()
        for owner in list(self.plans):
            if owner not in self.registry.sessions or self.plans[owner].expires < time.monotonic():
                self.plans.pop(owner, None)
        for owner in list(self.tasks):
            if owner not in self.registry.sessions:
                _, task = self.tasks.pop(owner)
                task.cancel()
        return self.registry.session(request.cookies.get(COOKIE_NAME))

    def require_agent(self):
        if not self.agent.available:
            raise DemoError('agent_unavailable', 'The signed-in agent is unavailable. Check Codex login on the agent host, then retry.', 503)

    def cancel(self, owner, encounter_id):
        active = self.tasks.get(owner)
        if active and active[0] == encounter_id:
            self.tasks.pop(owner, None)
            active[1].cancel()
        plan = self.plans.get(owner)
        if plan and plan.encounter_id == encounter_id:
            self.plans.pop(owner, None)

    async def close(self):
        tasks = [item[1] for item in self.tasks.values()]
        self.tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, owner, encounter_id, operation, request, timeout):
        prior = self.tasks.pop(owner, None)
        if prior:
            prior[1].cancel()
        task = asyncio.create_task(operation())
        self.tasks[owner] = (encounter_id, task)

        async def watch_disconnect():
            while not task.done():
                if await request.is_disconnected():
                    task.cancel()
                    return
                await asyncio.sleep(0.1)

        watcher = asyncio.create_task(watch_disconnect())
        try:
            result = await asyncio.wait_for(task, timeout)
            if self.tasks.get(owner) != (encounter_id, task):
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
            if self.tasks.get(owner) == (encounter_id, task):
                self.tasks.pop(owner, None)

    async def plan(self, owner, encounter_id, scenario, broaden):
        self.require_agent()
        context = {'task': 'encounter_query', 'animal': scenario['animal'], 'broaden': broaden,
                   'encounter': {key: scenario[key] for key in ('id', 'label', 'interaction', 'behavior_hint', 'description')}}
        choice = await self.agent.decide(context, EncounterQueryDecision)
        query = combined_behavior_query(self.public_text(choice.query, 280),
                                        self.public_text(choice.individual_query, 280), scenario['animal'])
        reason = self.public_text(choice.reason, 800).strip()
        if not reason:
            raise DemoError('invalid_agent_query', 'The agent query needs an explanation. Retry planning.', 502)
        plan = EncounterPlan(secrets.token_urlsafe(24), encounter_id, scenario['id'], broaden,
                             query, reason, time.monotonic() + min(self.registry.ttl, 300))
        self.plans[owner] = plan
        return plan

    def planned(self, owner, plan_id, encounter_id, scenario_id, broaden):
        plan = self.plans.get(owner)
        if (not plan or plan.id != plan_id or plan.encounter_id != encounter_id or plan.scenario_id != scenario_id
                or plan.broaden != broaden or plan.expires <= time.monotonic()):
            raise DemoError('encounter_plan_expired', 'Plan this encounter again before searching.', 409)
        return plan

    async def actions(self, segments, scenario, query):
        """Agent creates proposals; exact reviews and caption checks bound them."""
        self.require_agent()
        choices, annotations = [], []
        for segment in segments:
            annotation = self.manifest.annotate_interaction(segment, scenario['animal'], scenario['interaction_partner'])
            annotations.append(annotation)
            action = annotation['action']
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
        if not choices:
            return (), 'No archive clips were returned for action planning.'
        decision = await self.agent.decide({'task': 'encounter_actions', 'animal': scenario['animal'],
                                           'query': query, 'candidates': choices}, EncounterActionsDecision)
        identifiers = [item.candidate_id for item in decision.actions]
        if len(set(identifiers)) != len(identifiers) or any(value not in {c['candidate_id'] for c in choices} for value in identifiers):
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
                grounded, _ = classify_interaction(excerpt, scenario['animal'])
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
            output.append(item)
        return tuple(output), self.public_text(decision.summary, 800)
