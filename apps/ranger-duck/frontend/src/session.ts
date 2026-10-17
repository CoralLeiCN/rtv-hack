import { checkActive, playAndReact, reactionState, runRoleActions, type AgentCycle } from './agentLoop';
import { interruptible, isEligible, motionLabel, waitFor } from './demo';
import type { MicroduckSceneHandle } from './simulator/MicroduckScene';
import type { Execution, QueueAction, RunCursor, RunInput, RunOutcome, RunPlan, RunRound, RunScenario, SessionApi } from './sessionApi';

export type SessionPhase = 'idle' | 'starting' | 'planning' | 'searching' | 'approaching' | 'playback' | 'acting' | 'reporting' | 'complete' | 'paused' | 'empty' | 'failed';
export interface HistoryRecord {
  round: number; pass: number; query: string; queryReason: string; sourceRank: number;
  attemptId: string; primitive: string; status: RunOutcome['status']; replay: boolean;
  interaction: string;
}
export interface SessionState {
  phase: SessionPhase; running: boolean; stopping: boolean; runId: string | null;
  adaptive: boolean; roundAdaptive: boolean; round: RunRound | null; plan: RunPlan | null;
  currentScenario: RunScenario | null;
  execution: Execution | null; selectedId: string | null; pass: number;
  rankStates: Record<string, string>; history: HistoryRecord[];
  startedAt: number | null; elapsedMs: number; actionStartedAt: number | null;
  error: string | null; note: string | null; playbackBlocked: boolean; replay: boolean;
}
const initial = (): SessionState => ({
  phase: 'idle', running: false, stopping: false, runId: null, adaptive: false, roundAdaptive: false,
  round: null, plan: null, currentScenario: null, execution: null, selectedId: null, pass: 1, rankStates: {}, history: [],
  startedAt: null, elapsedMs: 0, actionStartedAt: null, error: null, note: null, playbackBlocked: false, replay: false,
});
type Scene = Pick<MicroduckSceneHandle, 'ensureInteraction' | 'perform' | 'performCompanion' | 'stopCompanion' | 'stop' | 'telemetry' | 'updateEncounterBehavior'>;

/** One owner for agent work, media and physics, regardless of the Loop toggle. */
export class SessionController {
  private state = initial();
  private listeners = new Set<() => void>();
  private active: AbortController | null = null;
  private generation = 0;
  private creation: Promise<unknown> = Promise.resolve();
  private cleanup: Promise<unknown> = Promise.resolve();
  private settings: Promise<unknown> = Promise.resolve();
  private broaden = false;
  private animal: 'cat' | 'deer' = 'deer';
  private resumeOnVisible = false;
  constructor(private options: {
    api(): SessionApi;
    scene(): Scene | null;
    video(): HTMLVideoElement | null;
    now?: () => number;
    transitionMs?: number;
  }) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<SessionState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach(listener => listener());
  }
  private now() { return this.options.now?.() ?? Date.now(); }
  private stopLocal() {
    this.options.video()?.pause();
    this.options.scene()?.stop();
    this.options.scene()?.stopCompanion();
  }
  private launch(operation: (signal: AbortSignal, current: () => boolean) => Promise<void>) {
    if (this.active) return;
    const controller = new AbortController();
    const generation = ++this.generation;
    this.active = controller;
    const current = () => this.active === controller && generation === this.generation && !controller.signal.aborted;
    this.update({ running: true, error: null, note: null, playbackBlocked: false });
    void operation(controller.signal, current).catch(error => {
      if (!current()) return;
      this.stopLocal();
      this.update({ phase: 'failed', running: false, error: error instanceof Error ? error.message : 'The run could not continue.', actionStartedAt: null, note: null,
        elapsedMs: this.state.startedAt == null ? this.state.elapsedMs : this.now() - this.state.startedAt, startedAt: null,
        rankStates: Object.fromEntries(Object.entries(this.state.rankStates).map(([id, value]) => [id, ['approaching', 'playing', 'running', 'watching'].includes(value) ? 'failed' : value])) });
      const id = this.state.runId;
      if (id) this.cleanup = this.options.api().pause(id).catch(() => undefined);
    }).finally(() => { if (this.active === controller) { this.active = null; this.update({ running: false }); } });
  }
  start(input: RunInput, broaden = false) {
    this.pause();
    this.settings = Promise.resolve();
    this.broaden = broaden;
    this.animal = input.animal;
    this.resumeOnVisible = false;
    this.update({ ...initial(), adaptive: input.adaptive, roundAdaptive: input.adaptive, runId: input.run_id, phase: 'starting' });
    const previousCleanup = this.cleanup;
    // Publish creation synchronously: an immediate toggle must wait for this
    // run, even when cleanup of the previous run is still in flight.
    const creation = previousCleanup.then(() => {
      if (this.state.runId !== input.run_id || !this.state.running) throw new DOMException('Run paused.', 'AbortError');
      return this.options.api().create(input, new AbortController().signal);
    });
    this.creation = creation;
    this.launch(async (signal, current) => {
      // Let session creation finish so Pause can always invalidate the created run.
      const cursor = await creation;
      if (!current()) return;
      await this.advance(cursor, signal, current);
    });
  }
  pause(note = 'Paused. Resume restarts the interrupted clip; completed actions stay completed.') {
    this.resumeOnVisible = false;
    this.active?.abort(); this.active = null; this.generation += 1;
    this.stopLocal();
    const id = this.state.runId;
    this.update({ running: false, phase: this.state.phase === 'idle' ? 'idle' : 'paused', actionStartedAt: null, playbackBlocked: false,
      elapsedMs: this.state.startedAt == null ? this.state.elapsedMs : this.now() - this.state.startedAt, startedAt: null,
      note, error: null, stopping: !!id,
        rankStates: Object.fromEntries(Object.entries(this.state.rankStates).map(([key, value]) => [key, ['approaching', 'playing', 'running', 'watching'].includes(value) ? 'paused' : value])) });
    if (id) {
      const previous = this.cleanup;
      const work = Promise.allSettled([previous, this.creation, this.settings]).then(() => this.options.api().pause(id));
      this.cleanup = work.catch(() => undefined);
      void this.cleanup.finally(() => { if (this.state.runId === id && this.cleanup === settled) this.update({ stopping: false }); });
      const settled = this.cleanup;
    }
  }
  resume() {
    const id = this.state.runId;
    if (!id || this.active) return;
    this.resumeOnVisible = false;
    this.launch(async (signal, current) => {
      await this.cleanup; await this.settings; checkActive(signal);
      const cursor = await this.options.api().resume(id, signal);
      if (!current()) return;
      await this.advance(cursor, signal, current);
    });
  }
  visibility(hidden: boolean) {
    if (hidden && this.state.running) { this.pause('Paused while this tab is hidden. The run resumes when you return.'); this.resumeOnVisible = true; }
    else if (!hidden && this.resumeOnVisible) { this.resumeOnVisible = false; this.resume(); }
  }
  reset() { this.pause(); this.update({ ...initial(), adaptive: this.state.adaptive, roundAdaptive: this.state.adaptive }); }
  inspect(clipId: string) {
    if (!this.state.round?.queue.some(item => item.candidate.clip_id === clipId)) return;
    this.pause('Paused for evidence inspection. Resume continues the issued queue.');
    this.update({ selectedId: clipId });
  }
  setAdaptive(adaptive: boolean) {
    this.update({ adaptive });
    const id = this.state.runId;
    if (!id) { this.update({ roundAdaptive: adaptive }); return; }
    this.settings = this.settings.catch(() => undefined).then(async () => {
      await this.creation;
      if (this.state.runId !== id) return;
      await this.options.api().adaptive(id, adaptive);
      // An adaptive acknowledgement never drives an execution cursor.
    });
    void this.settings.catch(error => { if (this.state.runId === id) { this.pause('The Loop setting could not be saved. Resume after retrying the setting.'); this.update({ error: error instanceof Error ? error.message : 'The Loop setting could not be saved.' }); } });
  }
  replay() {
    const id = this.state.runId;
    if (!id || !this.state.round) return;
    this.pause();
    this.launch(async (signal, current) => {
      await this.cleanup; checkActive(signal);
      this.update({ startedAt: this.now() });
      const round = await this.options.api().replay(id, signal);
      if (!current()) return;
      this.installRound(round, true);
      await this.advance(this.cursor(round), signal, current);
    });
  }
  private cursor(round: RunRound): RunCursor {
    return { run_id: round.run_id, status: round.run_status ?? (round.execution ? 'ready' : 'paused'), adaptive: round.adaptive ?? this.state.adaptive,
      round_id: round.round_id, round: round.round, pass: round.pass ?? 1, execution: round.execution };
  }
  private applyScenario(scenario: RunScenario) {
    if (!scenario || scenario.animal !== this.animal || !scenario.id || !scenario.label || !scenario.behavior_hint) throw new Error('The agent round returned an invalid animal encounter.');
    // Update the same actor, never reset the duck or recreate the scene. This
    // synchronous hint change does not delay retrieval behind navigation.
    this.options.scene()?.updateEncounterBehavior(scenario.behavior_hint);
    this.update({ currentScenario: scenario });
  }
  private installRound(round: RunRound, replay = false) {
    if (round.run_id !== this.state.runId || !round.round_id || !Array.isArray(round.queue)) throw new Error('The agent returned an unrelated round. Start a new run.');
    if (round.queue.length > 3 || round.queue.some((item, i) => !isEligible(item.candidate) || !item.role_plan || !item.action_id ||
      (i > 0 && (item.candidate.rank ?? 0) <= (round.queue[i-1].candidate.rank ?? 0)))) throw new Error('The returned queue contains an unsupported action or invalid archive order.');
    if (replay || this.state.currentScenario?.id !== round.scenario?.id) this.applyScenario(round.scenario);
    this.update({ round, plan: null, replay, pass: round.pass ?? 1, execution: round.execution,
      selectedId: round.queue[0]?.candidate.clip_id ?? null, rankStates: {}, phase: round.queue.length ? 'approaching' : 'empty',
      elapsedMs: this.state.startedAt == null ? round.elapsed_ms : this.now() - this.state.startedAt, startedAt: null,
      roundAdaptive: this.state.adaptive, note: round.queue.length ? null : 'No active supported motion. Try another intent or a broader search.' });
  }
  private async advance(first: RunCursor, signal: AbortSignal, current: () => boolean) {
    let cursor = first;
    while (current()) {
      checkActive(signal);
      if (cursor.run_id !== this.state.runId) throw new Error('The server returned an unrelated run.');
      if (cursor.status === 'needs_plan') {
        // After a round, face the animal while planning runs. Initial appearance
        // already starts this automatically; never gate an agent call on walking.
        if (this.state.round) void this.options.scene()?.ensureInteraction().catch(error => {
          if (current()) this.update({ note: error instanceof Error ? error.message : 'Navigation paused while the agent searches.' });
        });
        this.update({ phase: 'planning', startedAt: this.now(), elapsedMs: 0, plan: null, execution: null, replay: false, rankStates: {}, actionStartedAt: null });
        const plan = await this.options.api().plan(cursor.run_id, this.broaden, signal);
        checkActive(signal);
        if (plan.run_id !== cursor.run_id || !plan.plan_id || !plan.query?.trim()) throw new Error('The agent returned an invalid query plan.');
        this.applyScenario(plan.scenario);
        this.update({ phase: 'searching', plan });
        const round = await this.options.api().search(cursor.run_id, plan.plan_id, signal);
        checkActive(signal);
        this.installRound(round);
        cursor = this.cursor(round);
        continue;
      }
      if (cursor.status === 'paused' || !cursor.execution) {
        // A completed replay or an empty queue must not leave an automatic
        // approach running after the UI has stopped offering Pause.
        this.stopLocal();
        this.update({ phase: this.state.round?.queue.length ? 'paused' : 'empty', running: false, execution: null,
          note: this.state.replay ? 'Saved round finished. Resume returns to the live run.' : this.state.note ?? 'Run paused. Resume when ready.' });
        return;
      }
      const round = this.state.round;
      if (!round || cursor.round_id !== round.round_id) throw new Error('The action queue expired. Start a new run.');
      const item = round.queue.find(entry => entry.action_id === cursor.execution!.action_id);
      if (!item || !isEligible(item.candidate)) throw new Error('No active supported action was issued for this attempt.');
      if (cursor.pass !== this.state.pass) this.update({ rankStates: {}, roundAdaptive: this.state.adaptive });
      // Resume is authoritative even when an earlier outcome reached the server
      // but its acknowledgement was lost during Pause.
      const completed = Object.fromEntries(round.queue.slice(0, round.queue.indexOf(item)).map(entry => [entry.action_id, 'completed']));
      this.update({ execution: cursor.execution, pass: cursor.pass, selectedId: item.candidate.clip_id, phase: 'approaching', actionStartedAt: null,
        rankStates: { ...this.state.rankStates, ...completed, [item.action_id]: 'approaching' }, playbackBlocked: false, note: null });
      const report = await this.execute(round, item, cursor.execution, signal);
      checkActive(signal);
      this.update({ phase: 'reporting', actionStartedAt: null, note: null });
      // A toggle made during an action is saved before its boundary acknowledgement.
      await this.settings; checkActive(signal);
      cursor = await this.options.api().outcome(round.run_id, report, signal);
      checkActive(signal);
      if (!current()) return;
      this.update({ rankStates: { ...this.state.rankStates, [item.action_id]: report.status },
        history: [{ round: round.round, pass: this.state.pass, query: round.query, queryReason: round.query_reason ?? '',
          sourceRank: item.candidate.rank ?? 0, attemptId: report.attempt_id, primitive: report.primitive, status: report.status, replay: this.state.replay,
          interaction: round.scenario.label }, ...this.state.history].slice(0, 15) });
      if (report.status !== 'completed') throw new Error(this.state.error ?? 'Playback or movement did not complete. The run is paused.');
      this.update({ phase: 'complete', execution: null });
      await waitFor(this.options.transitionMs ?? 450, signal);
    }
  }
  private async execute(round: RunRound, item: QueueAction, execution: Execution, signal: AbortSignal): Promise<RunOutcome> {
    const scene = this.options.scene();
    if (!scene || !isEligible(item.candidate)) throw new Error('The simulator or reference is unavailable.');
    await interruptible(scene.ensureInteraction(), signal);
    checkActive(signal);
    const video = this.options.video();
    if (!video) throw new Error('The reference player is not ready. Resume to retry.');
    const candidate = item.candidate;
    const cycle: AgentCycle = { session_id: round.run_id, cycle_id: execution.attempt_id, cycle: round.round,
      query: round.query, query_reason: round.query_reason ?? '', response_reason: candidate.agent_reason ?? candidate.action_reason ?? '',
      candidates: [], role_plan: item.role_plan, action: candidate.action,
      clip: { clip_id: candidate.clip_id, video_url: candidate.video_url, caption: candidate.caption, rank: candidate.rank ?? 0,
        observed_behavior: candidate.inferred_behavior ?? candidate.reviewed_behavior ?? '', evidence_basis: candidate.action_basis ?? '',
        start_sec: candidate.provenance.segment_start_sec ?? 0, end_sec: candidate.provenance.segment_end_sec ?? 0 } };
    let companionStatus: RunOutcome['companion']['status'] = 'cancelled';
    let completed = false;
    this.update({ phase: 'playback', rankStates: { ...this.state.rankStates, [item.action_id]: 'playing' } });
    try {
      await playAndReact(video, cycle, signal, () => {
        checkActive(signal);
        this.update({ phase: 'acting', actionStartedAt: this.now(), playbackBlocked: false,
          rankStates: { ...this.state.rankStates, [item.action_id]: 'running' } });
        return runRoleActions(item.role_plan, signal, async () => {
          try { await scene.performCompanion({ behavior: item.role_plan.companion_behavior, durationMs: item.role_plan.companion_duration_ms }); companionStatus = 'completed'; }
          catch (error) { companionStatus = signal.aborted ? 'cancelled' : 'failed'; throw error; }
        }, () => scene.perform({ primitive: candidate.action.primitive, evidenceId: candidate.action.evidence_id, maxDurationMs: candidate.action.max_duration_ms })).then(() => {
          checkActive(signal);
          this.update({ phase: 'playback', actionStartedAt: null,
            note: video.ended ? null : 'Movement completed. Waiting for reference playback to end.',
            rankStates: { ...this.state.rankStates, [item.action_id]: 'watching' } });
        });
      }, () => this.update({ playbackBlocked: true, note: 'Press Play to allow this clip. Its action waits for playback.' }));
      completed = true;
    } catch (error) {
      checkActive(signal);
      this.update({ error: error instanceof Error ? error.message : 'Playback or movement failed.' });
    } finally { scene.stopCompanion(); }
    checkActive(signal);
    // Capture observed completion before navigation/Stop changes controller state.
    const state = reactionState(scene.telemetry());
    if (!completed) scene.stop();
    return { round_id: round.round_id, action_id: execution.action_id, attempt_id: execution.attempt_id,
      primitive: candidate.action.primitive, status: completed ? 'completed' : 'failed', playback: video.ended ? 'ended' : 'failed',
      companion: { behavior: item.role_plan.companion_behavior, status: companionStatus }, state };
  }
}

export function sessionLabel(state: SessionState): string {
  const item = state.round?.queue.find(entry => entry.action_id === state.execution?.action_id);
  const position = item ? state.round!.queue.indexOf(item) + 1 : null;
  const prefix = state.round ? `Round ${state.round.round} · pass ${state.pass}${position ? ` · action ${position}/${state.round.queue.length}` : ''}` : '';
  const phase: Record<SessionPhase, string> = { idle: 'Choose an animal and press Start', starting: 'Starting the encounter', planning: 'Agent generating query', searching: 'Searching archive and planning actions', approaching: 'Facing and approaching the animal', playback: 'Waiting for reference playback', acting: item?.candidate.action ? motionLabel(item.candidate.action.primitive) : 'Acting', reporting: 'Recording actual outcome', complete: 'Action completed', paused: 'Paused', empty: 'No active supported motion', failed: 'Run paused after an error' };
  return `${prefix ? `${prefix} · ` : ''}${phase[state.phase]}`;
}
