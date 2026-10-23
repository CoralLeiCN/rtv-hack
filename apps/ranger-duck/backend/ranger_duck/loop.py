"""Separate, session-scoped agent loop; existing search/replay semantics stay intact."""
import asyncio
from dataclasses import dataclass, field
import secrets
import time
from typing import Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from .errors import DemoError
from .evidence import Segment
from .loop_evidence import annotate_response
from .loop_agent import CodexAgent, QueryDecision, ActionDecision, Primitive, LIMITS, CYCLE_TIMEOUT, CompanionBehavior, COMPANION_BEHAVIORS, DUCK_ROLE_ACTIONS
from .session import COOKIE_NAME
from .encounter_agent import combined_behavior_query
from .action_evidence import ACTION_BEHAVIORS
from .archive import animal_search_scope
from .capture import Capture


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Start(StrictModel):
    session_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    prompt: str = Field(min_length=1, max_length=1000)
    animal: Literal['cat', 'deer']


class Telemetry(StrictModel):
    status: Literal['ready', 'complete', 'recovering', 'busy', 'failed', 'loading']
    position: list[float] = Field(min_length=3, max_length=3)
    head_yaw: float
    simulation_time: float = Field(ge=0)


class CompanionOutcome(StrictModel):
    behavior: CompanionBehavior
    status: Literal['completed', 'failed', 'cancelled']


class Outcome(StrictModel):
    cycle_id: str = Field(min_length=1, max_length=100)
    primitive: Primitive
    status: Literal['completed', 'failed', 'cancelled']
    playback: Literal['ended', 'failed', 'cancelled']
    state: Telemetry
    companion: CompanionOutcome


@dataclass
class LoopSession:
    id: str
    owner: str
    prompt: str
    animal: str
    history: list = field(default_factory=list)
    recent: list = field(default_factory=list)
    failures: int = 0
    cycle: int = 0
    paused: bool = False
    pending: dict | None = None
    task: asyncio.Task | None = None


class LoopService:
    def __init__(self, registry, client, manifest, public_text, agent=None, capture=None):
        self.capture = capture or Capture()
        self.registry, self.client, self.manifest = registry, client, manifest
        self.public_text = public_text
        self.agent = agent or CodexAgent()
        self.sessions: dict[str, LoopSession] = {}

    def owner(self, request):
        self.registry._prune()
        for owner in list(self.sessions):
            if owner not in self.registry.sessions:
                self.cancel(self.sessions.pop(owner))
        owner = request.cookies.get(COOKIE_NAME)
        if owner not in self.registry.sessions:
            raise DemoError('loop_session_expired', 'Reconnect to the backend and start a new loop.', 409)
        self.registry.session(owner)  # refresh browser-session TTL
        return owner

    def get(self, request, session_id):
        loop = self.sessions.get(self.owner(request))
        if loop is None or loop.id != session_id:
            raise DemoError('loop_not_found', 'This loop session is unavailable. Start a new loop.', 404)
        return loop

    def cancel(self, loop):
        loop.paused = True
        if loop.task:
            loop.task.cancel()
        if loop.pending:
            self.capture.emit('loop.action.interrupted', loop.pending, {'status': 'unknown'},
                run_id=self.capture.run_id(loop.owner, 'loop:' + loop.id))
            # No invented telemetry: an interrupted issued action has unknown outcome.
            loop.history.append({**loop.pending['context'], 'outcome': {'status': 'cancelled', 'state': None}})
            loop.history = loop.history[-5:]
        loop.pending = None

    async def close(self):
        tasks = [s.task for s in self.sessions.values() if s.task]
        for loop in self.sessions.values():
            self.cancel(loop)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def select(self, loop):
        rejected_queries = []
        for attempt in range(2):
            context = {'original_prompt': loop.prompt, 'animal': loop.animal,
                       'history': loop.history, 'rejected_queries': rejected_queries}
            query = await self.agent.decide(context, QueryDecision)
            words = self.public_text(query.query, 280).strip()
            if not words:
                raise DemoError('invalid_agent_query', 'The agent returned an empty query. Retry the loop.', 502)
            actual_query = combined_behavior_query(words, self.public_text(query.individual_query, 280), loop.animal)
            scope = animal_search_scope(loop.animal)
            result = await self.client.search(actual_query, tags=scope['tags'], top_k=10)
            choices, segments = [], {}
            # Preserve the first ten upstream ranks, including single animals,
            # weak matches, duplicates, and clips unavailable for execution.
            for rank, raw in enumerate(result['results'][:10], start=1):
                segment = Segment.parse(raw, rank)
                annotation = annotate_response(self.manifest, segment, loop.animal) if segment else {
                    'allowed_actions': [], 'eligibility_reason': 'invalid_source',
                    'observed_behavior': None, 'evidence_basis': None}
                identity = (segment.parent, segment.start, segment.end) if segment else None
                unavailable = None if annotation['allowed_actions'] else annotation['eligibility_reason']
                if segment and segment.complete and segment.end - segment.start > 120:
                    unavailable = 'clip_too_long'
                allowed = [] if unavailable else annotation['allowed_actions']
                candidate_id = secrets.token_urlsafe(16)
                caption = raw.get('reasoning_content', '') if isinstance(raw, dict) else ''
                choices.append({'candidate_id': candidate_id, 'rank': rank,
                                'caption': self.public_text(caption),
                                'observed_behavior': annotation['observed_behavior'],
                                'evidence_basis': annotation['evidence_basis'],
                                'allowed_actions': allowed, 'unavailable_reason': unavailable,
                                'recently_used': identity in loop.recent})
                segments[candidate_id] = (segment, annotation, identity)
            if not any(c['allowed_actions'] for c in choices):
                rejected_queries.append({'query': actual_query, 'reason': 'No new executable clips in the top ten.'})
                continue
            selection = await self.agent.decide({**context, 'query': actual_query, 'candidates': choices,
                                                'allowed_companion_behaviors': COMPANION_BEHAVIORS[loop.animal]}, ActionDecision)
            if selection.candidate_id is None and selection.primitive is None and selection.role_plan is None:
                rejected_queries.append({'query': actual_query, 'reason': self.public_text(selection.reason, 800)})
                continue
            chosen = next((c for c in choices if c['candidate_id'] == selection.candidate_id), None)
            if chosen is None or selection.primitive not in chosen['allowed_actions'] or selection.role_plan is None:
                raise DemoError('invalid_agent_action', 'Codex selected an unavailable clip or unsupported response. Retry the loop.', 502)
            segment, annotation, identity = segments[selection.candidate_id]
            plan = selection.role_plan.model_dump()
            primitive = selection.primitive
            if plan['grounding'] == 'insufficient_evidence':
                raise DemoError('invalid_agent_action', 'The selected clip needs an active supported behavior; a passive fallback is not allowed.', 502)
            elif plan['grounding'] == 'single_behavior':
                evidence = plan['duck']['evidence'].strip()
                if (not plan['duck']['subject'].strip() or not evidence or evidence not in chosen['caption']
                        or evidence not in segment.caption
                        or DUCK_ROLE_ACTIONS.get(plan['duck_behavior']) != primitive):
                    raise DemoError('invalid_agent_action', 'The single animal response needs a supported positive behavior and exact selected-species caption evidence.', 502)
                plan.update(companion_behavior='standing', timing='together',
                            companion={'subject': 'Unassigned scene companion', 'evidence': ''})
            elif (plan['companion_behavior'] not in COMPANION_BEHAVIORS[loop.animal]
                  or DUCK_ROLE_ACTIONS.get(plan['duck_behavior']) != primitive
                  or plan['companion']['subject'].strip().casefold() == plan['duck']['subject'].strip().casefold()
                  or any(not plan[role]['subject'].strip() or not plan[role]['evidence'].strip() or plan[role]['evidence'] not in chosen['caption'] or plan[role]['evidence'] not in segment.caption
                         for role in ('companion', 'duck'))):
                raise DemoError('invalid_agent_action', 'The two video roles need distinct subjects and evidence from the selected caption.', 502)
            for role in ('companion', 'duck'):
                plan[role] = {key: self.public_text(value, 600) for key, value in plan[role].items()}
            plan['companion_duration_ms'] = 3000
            if loop.paused or self.sessions.get(loop.owner) is not loop:
                raise DemoError('loop_cancelled', 'The loop was stopped.', 409)
            self.registry._prune()
            if loop.owner not in self.registry.sessions:
                raise DemoError('loop_session_expired', 'Start a new loop after reconnecting.', 409)
            clip_id = self.registry.add(loop.owner, segment.source)
            loop.cycle += 1
            cycle_id = secrets.token_urlsafe(24)
            action = {'primitive': primitive, 'max_duration_ms': LIMITS[primitive],
                      'evidence_id': annotation['evidence_id']}
            chosen = {**chosen, 'observed_behavior': annotation['observed_behavior'] or ACTION_BEHAVIORS[primitive],
                      'evidence_basis': annotation['evidence_basis'] or 'video_caption'}
            reason = self.public_text(selection.reason, 800)
            record = {'query': actual_query, 'caption': chosen['caption'],
                      'observed_behavior': chosen['observed_behavior'], 'action': action, 'reason': reason, 'role_plan': plan}
            loop.pending = {'cycle_id': cycle_id, 'context': record, 'identity': identity}
            loop.recent = (loop.recent + [identity])[-5:]
            return {'session_id': loop.id, 'cycle_id': cycle_id, 'cycle': loop.cycle,
                    'query': actual_query, 'query_reason': self.public_text(query.reason, 800),
                    'search_scope': scope,
                    'response_reason': reason, 'action': action, 'candidates': choices, 'role_plan': plan,
                    'clip': {'clip_id': clip_id, 'video_url': f'/demo-api/clips/{clip_id}/video',
                             'caption': chosen['caption'], 'rank': segment.rank,
                             'dataset': self.public_text(segment.dataset, 100) or None,
                             'dataset_id': self.public_text(segment.dataset_id, 100) or None,
                             'observed_behavior': chosen['observed_behavior'],
                             'evidence_basis': chosen['evidence_basis'],
                             'start_sec': segment.start, 'end_sec': segment.end}}
        raise DemoError('no_loop_match', 'No new active supported motion was found in the top ten after two searches.', 409)


def install_loop_routes(app, service):
    @app.post('/demo-api/loop')
    async def start(payload: Start, request: Request):
        owner = service.owner(request)
        if not payload.prompt.strip():
            raise DemoError('invalid_prompt', 'Enter an initial prompt.', 422)
        service.client._require_config()
        if not service.agent.available:
            raise DemoError('agent_unavailable', 'Install Codex CLI and sign in on the backend host to use Loop mode.', 503)
        old = service.sessions.get(owner)
        if old:
            service.cancel(old)
        service.sessions[owner] = LoopSession(payload.session_id, owner, service.public_text(payload.prompt, 1000), payload.animal)
        return {'session_id': payload.session_id, 'cycle_timeout_ms': CYCLE_TIMEOUT * 1000}

    @app.post('/demo-api/loop/{session_id}/next')
    async def next_cycle(session_id: str, request: Request):
        loop = service.get(request, session_id)
        if loop.paused or loop.pending or loop.task:
            raise DemoError('loop_not_ready', 'Resume the loop or finish the current cycle before searching again.', 409)
        async def bounded():
            with service.capture.scope(service.capture.run_id(loop.owner, 'loop:' + loop.id)):
                return await service.capture.call('loop.cycle', {'session_id': loop.id},
                    lambda: asyncio.wait_for(service.select(loop), timeout=CYCLE_TIMEOUT))
        task = loop.task = asyncio.create_task(bounded())
        try:
            return await task
        except asyncio.CancelledError:
            raise DemoError('loop_cancelled', 'The loop was stopped.', 409) from None
        except (DemoError, TimeoutError) as error:
            loop.failures += 1
            if loop.failures >= 3:
                loop.paused = True
            if isinstance(error, TimeoutError):
                raise DemoError('loop_timeout', 'The agent cycle exceeded its deadline. Retry when ready.', 504) from None
            raise
        finally:
            if loop.task is task:
                loop.task = None

    @app.post('/demo-api/loop/{session_id}/outcome')
    async def outcome(session_id: str, payload: Outcome, request: Request):
        loop = service.get(request, session_id)
        pending = loop.pending
        if not pending or pending['cycle_id'] != payload.cycle_id or pending['context']['action']['primitive'] != payload.primitive:
            raise DemoError('stale_outcome', 'This outcome does not match the current action.', 409)
        if payload.companion.behavior != pending['context']['role_plan']['companion_behavior']:
            raise DemoError('invalid_outcome', 'The companion outcome must match the issued role plan.', 422)
        if payload.status == 'completed' and (payload.playback != 'ended' or payload.state.status != 'complete' or payload.companion.status != 'completed'):
            raise DemoError('invalid_outcome', 'Completion requires finished playback, companion animation, and duck action.', 422)
        loop.history = (loop.history + [{**pending['context'], 'outcome': payload.model_dump()}])[-5:]
        service.capture.emit('loop.action.outcome', pending, payload.model_dump(),
            run_id=service.capture.run_id(loop.owner, 'loop:' + loop.id), outcome_source='browser_report')
        loop.pending = None
        loop.paused = payload.status != 'completed'
        if not loop.paused:
            loop.failures = 0
        return {'status': 'paused' if loop.paused else 'ready'}

    @app.post('/demo-api/loop/{session_id}/pause')
    async def pause(session_id: str, request: Request):
        loop = service.get(request, session_id)
        service.cancel(loop)
        return {'status': 'paused'}

    @app.post('/demo-api/loop/{session_id}/resume')
    async def resume(session_id: str, request: Request):
        loop = service.get(request, session_id)
        if loop.task or loop.pending:
            raise DemoError('loop_not_ready', 'Wait for the previous cycle to stop.', 409)
        loop.paused = False
        loop.failures = 0
        return {'status': 'ready'}
