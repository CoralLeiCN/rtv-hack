"""One staged agent pipeline for fixed queues and adaptive rounds."""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import copy
import secrets
import time
from typing import Literal

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import Field

from .encounter import PLAN_TIMEOUT, ENCOUNTER_TIMEOUT
from .errors import DemoError
from .evidence import normalize_segments
from .loop import StrictModel, Telemetry, CompanionOutcome
from .loop_agent import ActivePrimitive
from .session import COOKIE_NAME
from .archive import animal_search_scope

MAX_RUNS_PER_SESSION = 8


def public_scenario(scenario):
    return {key: scenario[key] for key in ('id', 'label', 'animal', 'behavior_hint',
                                          'interaction', 'description', 'interaction_partner')}


class StartRun(StrictModel):
    run_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    animal: Literal['cat', 'deer']
    scenario_id: str = Field(min_length=1, max_length=100)
    intent: str = Field(default='', max_length=1000)
    adaptive: bool = False


class PlanRun(StrictModel):
    broaden: bool = False


class SearchRun(StrictModel):
    plan_id: str = Field(min_length=1, max_length=100)


class AdaptiveRun(StrictModel):
    adaptive: bool


class RunOutcome(StrictModel):
    round_id: str = Field(min_length=1, max_length=100)
    action_id: str = Field(min_length=1, max_length=100)
    attempt_id: str = Field(min_length=1, max_length=100)
    primitive: ActivePrimitive
    status: Literal['completed', 'failed', 'cancelled']
    playback: Literal['ended', 'failed', 'cancelled']
    state: Telemetry
    companion: CompanionOutcome


@dataclass
class Round:
    id: str
    number: int
    query: str
    reason: str
    scope: dict
    segments: tuple
    annotations: tuple
    summary: str
    timings: dict
    recorded_at: str
    expires: float
    entries: list
    scenario: dict
    broaden: bool = False
    origin: str = 'live'


@dataclass
class Run:
    id: str
    owner: str
    animal: str
    scenario: dict
    intent: str
    adaptive: bool
    phase: str = 'needs_plan'
    revision: int = 0
    counter: int = 0
    plan: dict | None = None
    pending_scenario: dict | None = None
    completed_scenario: dict | None = None
    round: Round | None = None
    last_round: Round | None = None
    cursor: int = 0
    pass_number: int = 1
    pending: dict | None = None
    history: list = field(default_factory=list)
    recent: list = field(default_factory=list)
    acknowledgements: dict = field(default_factory=dict)


class RunService:
    def __init__(self, registry, client, encounters, render_candidate, scenarios):
        self.registry, self.client, self.encounters = registry, client, encounters
        self.render_candidate = render_candidate
        self.capture = encounters.capture
        self.scenarios = scenarios
        self.runs: dict[tuple[str, str], Run] = {}

    def emit(self, run, kind, inputs=None, output=None, **attributes):
        self.capture.emit(kind, inputs, output,
            run_id=self.capture.run_id(run.owner, 'encounter:' + run.id), **attributes)

    def owner(self, request):
        owner = self.encounters.owner(request)
        for expired in list(self.runs):
            if expired[0] not in self.registry.sessions:
                self.pause(self.runs.pop(expired))
        return owner

    def get(self, request, run_id):
        supplied = request.cookies.get(COOKIE_NAME)
        self.registry._prune()
        if supplied not in self.registry.sessions:
            raise DemoError('run_session_expired', 'Reconnect and start a new run.', 409)
        owner = self.owner(request)
        run = self.runs.get((owner, run_id))
        if run is None:
            raise DemoError('run_not_found', 'This run is unavailable. Start a new encounter.', 404)
        return run

    def check(self, run, revision):
        if self.runs.get((run.owner, run.id)) is not run or run.revision != revision or run.phase == 'paused':
            raise DemoError('run_cancelled', 'The run was paused or replaced.', 409)

    def reply(self, run):
        status = 'paused' if run.phase == 'paused' else 'ready' if run.pending else 'needs_plan'
        return {'run_id': run.id, 'status': status, 'adaptive': run.adaptive,
                'round_id': run.round.id if run.round else None,
                'round': run.round.number if run.round else run.counter,
                'pass': run.pass_number, 'execution': copy.deepcopy(run.pending)}

    def issue(self, run):
        if not run.round or not run.round.entries or run.cursor >= len(run.round.entries):
            run.pending = None
            run.phase = 'needs_plan'
            return
        run.phase = 'ready'
        run.pending = {'action_id': run.round.entries[run.cursor]['action_id'], 'attempt_id': secrets.token_urlsafe(24)}
        entry = run.round.entries[run.cursor]
        annotation = run.round.annotations[entry['index']]
        self.emit(run, 'run.action.issued',
            {'round_id': run.round.id, 'round': run.round.number, 'pass': run.pass_number,
             'origin': run.round.origin, **run.pending},
            {'action': annotation['action'], 'role_plan': annotation['role_plan']})
        if self.capture.failed:
            run.pending = None
            run.phase = 'paused'
            raise DemoError('capture_unavailable', 'Check private capture storage before resuming.', 503)

    def pause(self, run):
        if run.pending:
            self.emit(run, 'run.action.interrupted',
                {'round_id': run.round.id, 'origin': run.round.origin, **run.pending},
                {'status': 'unknown'})
        run.revision += 1
        self.encounters.cancel(run.owner, run.id, scope=run.id)
        run.pending = None
        # A partially planned query cannot be resumed as though it completed.
        if run.phase in {'planning', 'planned', 'searching'}:
            run.plan = None
            run.round = None
        run.phase = 'paused'
        return self.reply(run)

    def resume(self, run):
        if run.phase != 'paused':
            return self.reply(run)
        if not run.round or run.round.expires <= time.monotonic() or not run.round.entries:
            run.round = None
            run.phase = 'needs_plan'
        elif run.cursor >= len(run.round.entries):
            if run.adaptive or run.round.origin == 'replay':
                run.phase = 'needs_plan'
            else:
                run.cursor = 0
                run.pass_number += 1
                self.issue(run)
        else:
            self.issue(run)
        return self.reply(run)

    async def plan_round(self, run, payload, request):
        if run.pending or run.phase in {'paused', 'planning', 'searching'}:
            raise DemoError('run_not_ready', 'Finish or pause the current action before planning.', 409)
        run.revision += 1
        revision = run.revision
        run.phase = 'planning'
        run.plan = None
        run.round = None
        if run.pending_scenario is None:
            scenario = run.completed_scenario or run.scenario
            if run.adaptive and run.completed_scenario is not None:
                alternatives = [item for item in self.scenarios.values()
                                if item['animal'] == run.animal and item['id'] != scenario['id']]
                if alternatives:
                    scenario = secrets.choice(alternatives)
            run.pending_scenario = copy.deepcopy(scenario)
        scenario = copy.deepcopy(run.pending_scenario)
        started = time.monotonic()
        async def work():
            plan = await self.encounters.plan(run.owner, run.id, scenario, payload.broaden,
                                              intent=run.intent, history=run.history, scope=run.id)
            self.check(run, revision)
            run.plan = {'decision': plan, 'round_id': secrets.token_urlsafe(24), 'number': run.counter + 1,
                        'scenario': scenario,
                        'timings': {'query_agent_ms': round((time.monotonic() - started) * 1000)}}
            run.phase = 'planned'
            return {'run_id': run.id, 'encounter_id': run.id, 'round_id': run.plan['round_id'],
                    'round': run.plan['number'], 'plan_id': plan.id, 'query': plan.query,
                    'query_reason': plan.reason, 'query_basis': 'agent',
                    'scenario': public_scenario(scenario),
                    'search_scope': animal_search_scope(run.animal), 'timings': run.plan['timings']}
        try:
            return await self.encounters.run(run.owner, run.id, work, request, PLAN_TIMEOUT, scope=run.id)
        except BaseException:
            if self.runs.get((run.owner, run.id)) is run and run.revision == revision and run.phase != 'paused':
                run.phase = 'needs_plan'
            raise

    async def search_round(self, run, payload, request):
        if run.phase != 'planned' or not run.plan or run.plan['decision'].id != payload.plan_id:
            raise DemoError('run_plan_expired', 'Generate a new query plan before searching.', 409)
        plan = self.encounters.planned(run.owner, payload.plan_id, run.id, run.plan['scenario']['id'],
                                       run.plan['decision'].broaden, scope=run.id)
        revision, prepared = run.revision, run.plan
        run.phase = 'searching'
        async def work():
            scope = animal_search_scope(run.animal)
            started = time.monotonic()
            result = await self.client.search(plan.query, tags=scope['tags'], top_k=15)
            search_ms = round((time.monotonic() - started) * 1000)
            self.check(run, revision)
            segments = tuple(normalize_segments(result['results']))
            started = time.monotonic()
            annotations, summary = await self.encounters.actions(segments, prepared['scenario'], plan.query,
                role_plans=True, history=run.history, recent=run.recent)
            action_ms = round((time.monotonic() - started) * 1000)
            self.check(run, revision)
            entries = [{'action_id': secrets.token_urlsafe(24), 'index': index}
                       for index, annotation in enumerate(annotations) if annotation['action']][:3]
            run.round = Round(prepared['round_id'], prepared['number'], plan.query, plan.reason, scope,
                segments, annotations, summary,
                {**prepared['timings'], 'vss_search_ms': search_ms, 'action_agent_ms': action_ms},
                datetime.now(timezone.utc).isoformat(), time.monotonic() + self.registry.ttl, entries,
                scenario=copy.deepcopy(prepared['scenario']), broaden=plan.broaden)
            run.pending_scenario = None
            run.last_round = run.round
            run.counter = run.round.number
            run.cursor, run.pass_number, run.plan = 0, 1, None
            if entries:
                self.issue(run)
            else:
                run.phase, run.pending = 'paused', None
            response = self.render(run)
            self.emit(run, 'run.search.result', {'round_id': run.round.id}, response)
            return response
        try:
            return await self.encounters.run(run.owner, run.id, work, request, ENCOUNTER_TIMEOUT, scope=run.id)
        except BaseException:
            if self.runs.get((run.owner, run.id)) is run and run.revision == revision and run.phase != 'paused':
                run.phase = 'needs_plan'
            raise

    def render(self, run):
        record = run.round
        candidates = [self.render_candidate(run.owner, segment, annotation)
                      for segment, annotation in zip(record.segments, record.annotations)]
        queue = [{'action_id': entry['action_id'], 'candidate': candidates[entry['index']],
                  'role_plan': record.annotations[entry['index']]['role_plan']} for entry in record.entries]
        self.registry.protect(run.owner, run.id, [entry['candidate']['clip_id'] for entry in queue])
        return {'run_id': run.id, 'encounter_id': run.id, 'round_id': record.id, 'round': record.number,
                'scenario': public_scenario(record.scenario),
                'pass': run.pass_number, 'adaptive': run.adaptive, 'run_status': self.reply(run)['status'],
                'execution': copy.deepcopy(run.pending), 'queue': queue,
                'search_id': record.id, 'mode': record.origin,
                'status': 'ok' if queue else 'no_supported_imitation' if candidates else 'no_results',
                'query': record.query, 'query_reason': record.reason, 'query_basis': 'agent',
                'search_scope': record.scope, 'action_planner': 'agent', 'agent_plan': {'summary': record.summary},
                'timings': record.timings if record.origin == 'live' else {key: 0 for key in record.timings},
                'original_timings': record.timings, 'elapsed_ms': sum(record.timings.values()) if record.origin == 'live' else 0,
                'original_elapsed_ms': sum(record.timings.values()), 'recorded_at': record.recorded_at,
                'match_type': 'broader_behavior' if record.broaden else 'species_interaction',
                'candidates': candidates, 'warnings': ([self.encounters.manifest.warning] if self.encounters.manifest.warning else []) +
                    ['Actions are grounded in existing captions or exact reviews; caption inference is not visual review.']}

    def outcome(self, run, payload):
        body = payload.model_dump()
        key = (payload.round_id, payload.action_id, payload.attempt_id)
        prior = run.acknowledgements.get(key)
        if prior:
            if prior[0] != body:
                raise DemoError('conflicting_outcome', 'This attempt already has a different outcome.', 409)
            return copy.deepcopy(prior[1])
        if (not run.round or run.round.id != payload.round_id or not run.pending
                or run.pending != {'action_id': payload.action_id, 'attempt_id': payload.attempt_id}):
            raise DemoError('stale_outcome', 'This outcome does not match the current action attempt.', 409)
        entry = run.round.entries[run.cursor]
        annotation = run.round.annotations[entry['index']]
        if (payload.primitive != annotation['action']['primitive']
                or payload.companion.behavior != annotation['role_plan']['companion_behavior']):
            raise DemoError('invalid_outcome', 'The outcome must match the issued action and companion role.', 422)
        if payload.status == 'completed' and (payload.playback != 'ended' or payload.state.status != 'complete'
                                             or payload.companion.status != 'completed'):
            raise DemoError('invalid_outcome', 'Completion requires finished playback, duck motion, and companion animation.', 422)
        segment = run.round.segments[entry['index']]
        self.emit(run, 'run.action.outcome',
            {'round_id': run.round.id, 'origin': run.round.origin,
             'action': annotation['action'], 'role_plan': annotation['role_plan']},
            body, outcome_source='browser_report')
        if self.capture.failed:
            raise DemoError('capture_unavailable', 'The outcome could not be saved. Check private capture storage.', 503)
        if run.round.origin == 'live':
            run.history = (run.history + [{'query': run.round.query, 'caption': self.encounters.public_text(segment.caption),
                'scenario': public_scenario(run.round.scenario),
                'source_rank': segment.rank, 'action': annotation['action'], 'role_plan': annotation['role_plan'], 'outcome': body}])[-9:]
            identity = (segment.parent, segment.start, segment.end)
            run.recent = ([item for item in run.recent if item != identity] + [identity])[-3:]
        run.pending = None
        if payload.status != 'completed':
            run.phase = 'paused'
        else:
            run.cursor += 1
            if run.cursor == len(run.round.entries) and run.round.origin == 'live':
                run.completed_scenario = copy.deepcopy(run.round.scenario)
            if run.cursor < len(run.round.entries):
                self.issue(run)
            elif run.round.origin == 'replay':
                run.phase = 'paused'
            elif run.adaptive:
                run.phase = 'needs_plan'
            else:
                run.cursor = 0
                run.pass_number += 1
                self.issue(run)
        answer = self.reply(run)
        run.acknowledgements[key] = (body, copy.deepcopy(answer))
        if len(run.acknowledgements) > 128:
            del run.acknowledgements[next(iter(run.acknowledgements))]
        return answer

    def replay(self, run):
        snapshot = run.last_round
        if not snapshot or snapshot.expires <= time.monotonic() or not snapshot.entries:
            raise DemoError('replay_unavailable', 'Complete a live search with active actions before replaying it.', 409)
        self.pause(run)
        run.counter += 1
        run.round = replace(snapshot, id=secrets.token_urlsafe(24), number=run.counter, origin='replay',
                            entries=[{**entry, 'action_id': secrets.token_urlsafe(24)} for entry in snapshot.entries])
        run.cursor, run.pass_number = 0, 1
        self.issue(run)
        return self.render(run)


def install_run_routes(app, service, scenarios, establish_cookie):
    @app.post('/demo-api/runs')
    async def start(payload: StartRun, request: Request):
        scenario = scenarios.get(payload.scenario_id)
        if not scenario or scenario['animal'] != payload.animal:
            raise DemoError('unknown_scenario', 'Choose an encounter for the selected species.', 422)
        service.client._require_config()
        service.encounters.require_agent()
        owner = service.owner(request)
        key = (owner, payload.run_id)
        previous = service.runs.get(key)
        if previous:
            service.pause(previous)
            service.registry.release(owner, previous.id)
        else:
            owned = [(key, run) for key, run in service.runs.items() if key[0] == owner]
            if len(owned) >= MAX_RUNS_PER_SESSION:
                # Retire a paused run first; never silently replace another tab
                # that is still planning or executing.
                retired = next((key for key, run in owned if run.phase == 'paused'), None)
                if retired is None:
                    raise DemoError('run_limit_reached', 'Pause an existing run before starting another.', 409)
                removed = service.runs.pop(retired)
                service.pause(removed)
                service.registry.release(owner, removed.id)
        run = Run(payload.run_id, owner, payload.animal, scenario,
                  service.encounters.public_text(payload.intent, 1000), payload.adaptive)
        service.runs[key] = run
        response = JSONResponse({**service.reply(run), 'encounter_plan_timeout_ms': PLAN_TIMEOUT * 1000,
                                 'encounter_timeout_ms': ENCOUNTER_TIMEOUT * 1000})
        establish_cookie(response, owner)
        return response

    @app.post('/demo-api/runs/{run_id}/plan')
    async def plan(run_id: str, payload: PlanRun, request: Request):
        return await service.plan_round(service.get(request, run_id), payload, request)

    @app.post('/demo-api/runs/{run_id}/search')
    async def search(run_id: str, payload: SearchRun, request: Request):
        return await service.search_round(service.get(request, run_id), payload, request)

    @app.post('/demo-api/runs/{run_id}/outcome')
    async def outcome(run_id: str, payload: RunOutcome, request: Request):
        return service.outcome(service.get(request, run_id), payload)

    @app.post('/demo-api/runs/{run_id}/pause')
    async def pause(run_id: str, request: Request):
        return service.pause(service.get(request, run_id))

    @app.post('/demo-api/runs/{run_id}/resume')
    async def resume(run_id: str, request: Request):
        return service.resume(service.get(request, run_id))

    @app.post('/demo-api/runs/{run_id}/adaptive')
    async def adaptive(run_id: str, payload: AdaptiveRun, request: Request):
        run = service.get(request, run_id)
        run.adaptive = payload.adaptive
        return service.reply(run)

    @app.post('/demo-api/runs/{run_id}/replay')
    async def replay(run_id: str, request: Request):
        return service.replay(service.get(request, run_id))
