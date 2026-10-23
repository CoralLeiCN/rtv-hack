import { describe, expect, it, vi } from 'vitest';
import { SessionController } from '../src/session';
import { runDeadline, type RunCursor, type RunInput, type RunOutcome, type RunPlan, type RunRound, type RunScenario, type SessionApi } from '../src/sessionApi';
import type { Candidate } from '../src/api';
import type { RolePlan } from '../src/agentLoop';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
class Video extends EventTarget {
  ended = false; muted = true; src = '';
  load = vi.fn(() => { this.ended = false; });
  play = vi.fn(async () => { this.dispatchEvent(new Event('playing')); });
  pause = vi.fn();
  finish() { this.ended = true; this.dispatchEvent(new Event('ended')); }
}
const role: RolePlan = { grounding: 'single_behavior', companion: { subject: '', evidence: '' }, duck: { subject: 'cat', evidence: 'A cat walks' },
  duck_behavior: 'moving', companion_behavior: 'standing', companion_duration_ms: 3000, timing: 'together' };
const input: RunInput = { run_id: 'run', animal: 'cat', scenario_id: 'cat-play', intent: '', adaptive: false };
const scenarios: RunScenario[] = [
  { id: 'cat-play', label: 'Social play', animal: 'cat', behavior_hint: 'play', interaction: 'play', description: 'Cat plays.' },
  { id: 'cat-greeting', label: 'Greeting', animal: 'cat', behavior_hint: 'greeting', interaction: 'greeting', description: 'Cat greets.' },
  { id: 'cat-hissing', label: 'Hissing', animal: 'cat', behavior_hint: 'hissing', interaction: 'hissing', description: 'Cat hisses.' },
];
function candidate(rank: number): Candidate {
  return { rank, clip_id: `clip-${rank}`, video_url: `/demo-api/clips/${rank}/video`, caption: 'A cat walks', similarity: 0.4,
    review_status: 'unreviewed', eligibility_reason: 'caption_behavior_match', animal: 'cat', reviewed_behavior: null,
    action_basis: 'video_caption', inferred_behavior: 'walking', provenance: { dataset: null, source_label: 'cat.mp4', parent_id: 'parent', segment_start_sec: 0, segment_end_sec: 1 },
    action: { primitive: 'short_walk', evidence_id: `e-${rank}`, max_duration_ms: 2000 } };
}
function fixture(adaptive = false) {
  let roundNumber = 0, pass = 1, index = 0, attempt = 0, isAdaptive = adaptive, replay = false;
  const candidates = [candidate(3), candidate(5), candidate(8)];
  const execution = () => ({ action_id: `a-${index}`, attempt_id: `attempt-${++attempt}` });
  const cursor = (status: RunCursor['status'] = 'ready'): RunCursor => ({ run_id: 'run', status, adaptive: isAdaptive, round_id: roundNumber ? `round-${roundNumber}` : null,
    round: roundNumber, pass, execution: status === 'ready' ? execution() : null });
  const round = (): RunRound => ({ run_id: 'run', round_id: `round-${roundNumber}`, round: roundNumber, pass, run_status: 'ready', scenario: scenarios[(roundNumber - 1) % scenarios.length],
    encounter_id: 'run', search_id: `search-${roundNumber}`, mode: replay ? 'replay' : 'live', status: 'ok', query: `query ${roundNumber}`, query_reason: 'Grounded intent', elapsed_ms: 10,
    candidates, warnings: [], queue: candidates.map((candidate, i) => ({ action_id: `a-${i}`, candidate, role_plan: role })), execution: execution() });
  const api = {
    create: vi.fn(async (_input: RunInput) => cursor('needs_plan')),
    plan: vi.fn(async (): Promise<RunPlan> => { roundNumber += 1; index = 0; pass = 1; return { run_id: 'run', round_id: `round-${roundNumber}`, round: roundNumber, plan_id: 'plan', query: 'actual query', query_reason: 'intent', scenario: scenarios[(roundNumber - 1) % scenarios.length] }; }),
    search: vi.fn(async () => round()),
    outcome: vi.fn(async (_id: string, _outcome: RunOutcome) => {
      if (++index === 3) { index = 0; pass += 1; if (replay) return cursor('paused'); if (isAdaptive) return cursor('needs_plan'); }
      return cursor();
    }),
    pause: vi.fn(async () => cursor('paused')),
    resume: vi.fn(async () => cursor(roundNumber ? 'ready' : 'needs_plan')),
    adaptive: vi.fn(async (_id: string, enabled: boolean) => { isAdaptive = enabled; return cursor(); }),
    replay: vi.fn(async () => { replay = true; index = 0; pass = 1; return round(); }),
  } satisfies SessionApi;
  const video = new Video();
  const scene = {
    ensureInteraction: vi.fn(async () => {}), updateEncounterBehavior: vi.fn(), perform: vi.fn(async () => {}), performCompanion: vi.fn(async () => {}), stopCompanion: vi.fn(), stop: vi.fn(),
    telemetry: vi.fn(() => ({ status: 'complete' as const, position: [0.12, 0, 0.2], head_yaw: 0, simulation_time: 4,
      navigation: 'idle' as const, approach_phase: null, primitive: null, commands: { forward: 0, lateral: 0, yaw: 0 }, body_yaw: 0, target: null })),
  };
  const controller = new SessionController({ api: () => api, scene: () => scene, video: () => video as unknown as HTMLVideoElement, transitionMs: 0 });
  const start = () => controller.start({ ...input, adaptive });
  const playing = () => vi.waitFor(() => { expect(['acting', 'playback']).toContain(controller.getSnapshot().phase); expect(video.play).toHaveBeenCalled(); });
  const finish = async () => { await playing(); const count = api.outcome.mock.calls.length; video.finish(); await vi.waitFor(() => expect(api.outcome).toHaveBeenCalledTimes(count + 1)); };
  return { controller, api, scene, video, start, playing, finish, cursor, round };
}

describe('one shared encounter session', () => {
  it('stops on reference expiry and searches again only after explicit Resume', async () => {
    const f = fixture();
    f.api.outcome.mockImplementationOnce(async () => ({ ...f.cursor('paused'), pause_reason: 'references_expired' }));
    f.start();
    await f.finish();
    await vi.waitFor(() => expect(f.controller.getSnapshot().phase).toBe('paused'));
    expect(f.controller.getSnapshot()).toMatchObject({ running: false, execution: null,
      note: 'Reference access expired. Resume searches for fresh references.' });
    expect(f.controller.getSnapshot().history).toHaveLength(1);
    expect(f.api.search).toHaveBeenCalledOnce();
    expect(f.scene.perform).toHaveBeenCalledOnce();
    expect(f.video.pause).toHaveBeenCalled();
    f.api.resume.mockImplementationOnce(async () => f.cursor('needs_plan'));
    f.controller.resume();
    await vi.waitFor(() => expect(f.api.search).toHaveBeenCalledTimes(2));
    f.controller.pause();
  });
  it('OFF repeats the same three source-ranked actions without another query or search', async () => {
    const f = fixture(); f.start();
    for (let i = 0; i < 4; i++) await f.finish();
    f.controller.pause();
    expect(f.api.plan).toHaveBeenCalledOnce(); expect(f.api.search).toHaveBeenCalledOnce();
    expect(f.api.outcome.mock.calls.map(([, result]) => result.action_id)).toEqual(['a-0', 'a-1', 'a-2', 'a-0']);
    expect(f.controller.getSnapshot().round?.queue.map(item => item.candidate.rank)).toEqual([3, 5, 8]);
    expect(f.controller.getSnapshot().history).toHaveLength(4);
    expect(f.scene.updateEncounterBehavior).toHaveBeenCalledOnce();
    expect(f.controller.getSnapshot().currentScenario?.id).toBe('cat-play');
  });
  it('ON uses the identical initial pipeline and searches again only after the third acknowledged action', async () => {
    const f = fixture(true); f.start();
    await f.finish(); await f.finish();
    expect(f.api.plan).toHaveBeenCalledOnce(); expect(f.api.search).toHaveBeenCalledOnce();
    await f.finish();
    await vi.waitFor(() => expect(f.api.search).toHaveBeenCalledTimes(2));
    f.controller.pause();
    expect(f.api.outcome).toHaveBeenCalledTimes(3);
  });
  it('applies the next adaptive interaction to the same scene before retrieval, retaining the original input', async () => {
    const f = fixture(true); f.start();
    await f.finish(); await f.finish(); await f.finish();
    await vi.waitFor(() => expect(f.api.search).toHaveBeenCalledTimes(2));
    expect(f.scene.updateEncounterBehavior.mock.calls.map(([hint]) => hint)).toEqual(['play', 'greeting']);
    expect(f.scene.updateEncounterBehavior.mock.invocationCallOrder[1]).toBeLessThan(f.api.search.mock.invocationCallOrder[1]);
    expect(f.controller.getSnapshot().currentScenario?.label).toBe('Greeting');
    expect(f.api.create.mock.calls[0][0]).toMatchObject({ scenario_id: 'cat-play', intent: '' });
    expect(f.api.create).toHaveBeenCalledOnce();
    f.controller.pause();
  });
  it('applies a mid-action Loop change at the round boundary without restarting the queue', async () => {
    const f = fixture(); f.start(); await f.playing();
    const first = f.controller.getSnapshot().execution;
    f.controller.setAdaptive(true);
    await vi.waitFor(() => expect(f.api.adaptive).toHaveBeenCalledOnce());
    expect(f.controller.getSnapshot().execution).toEqual(first);
    expect(f.scene.perform).toHaveBeenCalledOnce();
    await f.finish(); await f.finish(); await f.finish();
    await vi.waitFor(() => expect(f.api.plan).toHaveBeenCalledTimes(2));
    f.controller.pause();
  });
  it('queues an immediate toggle behind creation when the previous run is still stopping', async () => {
    const f = fixture(); f.start(); await f.playing();
    const cleanup = deferred<RunCursor>();
    f.api.pause.mockImplementationOnce(() => cleanup.promise);
    f.controller.pause();
    await vi.waitFor(() => expect(f.api.pause).toHaveBeenCalledOnce());
    f.controller.start(input);
    f.controller.setAdaptive(true);
    await Promise.resolve(); await Promise.resolve();
    expect(f.api.create).toHaveBeenCalledOnce(); expect(f.api.adaptive).not.toHaveBeenCalled();
    cleanup.resolve(f.cursor('paused'));
    await vi.waitFor(() => expect(f.api.adaptive).toHaveBeenCalledOnce());
    expect(f.api.create).toHaveBeenCalledTimes(2);
    expect(f.api.create.mock.invocationCallOrder[1]).toBeLessThan(f.api.adaptive.mock.invocationCallOrder[0]);
    f.controller.pause();
  });
  it('retries a failed Loop setting before Resume and preserves completed actions', async () => {
    const f = fixture(), saved = deferred<void>();
    const adaptive = f.api.adaptive.getMockImplementation()!;
    f.api.adaptive.mockRejectedValueOnce(new Error('Setting request failed.'))
      .mockImplementationOnce(async (id, enabled) => { await saved.promise; return adaptive(id, enabled); });
    try {
      f.start(); await f.finish(); await f.playing();
      const interrupted = f.controller.getSnapshot().execution!;
      f.controller.setAdaptive(true);
      await vi.waitFor(() => {
        expect(f.controller.getSnapshot().phase).toBe('paused');
        expect(f.controller.getSnapshot().stopping).toBe(false);
      });
      f.controller.resume();
      await vi.waitFor(() => expect(f.api.adaptive).toHaveBeenCalledTimes(2));
      expect(f.api.adaptive).toHaveBeenLastCalledWith('run', true);
      expect(f.api.resume).not.toHaveBeenCalled();
      expect(f.scene.perform).toHaveBeenCalledTimes(2);
      saved.resolve(); await f.playing();
      expect(f.api.resume).toHaveBeenCalledOnce();
      expect(f.controller.getSnapshot().execution?.action_id).toBe(interrupted.action_id);
      expect(f.controller.getSnapshot().execution?.attempt_id).not.toBe(interrupted.attempt_id);
      expect(f.controller.getSnapshot().rankStates['a-0']).toBe('completed');
      await f.finish(); await f.finish();
      await vi.waitFor(() => expect(f.api.plan).toHaveBeenCalledTimes(2));
    } finally { saved.resolve(); f.controller.pause(); }
  });
  it('stays paused if the Loop setting retry fails and allows another Resume attempt', async () => {
    const f = fixture();
    f.api.adaptive.mockRejectedValueOnce(new Error('Setting request failed.'))
      .mockRejectedValueOnce(new Error('Setting retry failed.'));
    try {
      f.start(); await f.playing();
      f.controller.setAdaptive(true);
      await vi.waitFor(() => {
        expect(f.controller.getSnapshot().phase).toBe('paused');
        expect(f.controller.getSnapshot().stopping).toBe(false);
      });
      f.controller.resume();
      await vi.waitFor(() => {
        expect(f.api.adaptive).toHaveBeenCalledTimes(2);
        expect(f.controller.getSnapshot().phase).toBe('paused');
        expect(f.controller.getSnapshot().stopping).toBe(false);
      });
      expect(f.controller.getSnapshot().error).toBe('Setting retry failed.');
      expect(f.api.resume).not.toHaveBeenCalled();
      expect(f.scene.perform).toHaveBeenCalledOnce();
      f.controller.resume(); await f.playing();
      expect(f.api.adaptive).toHaveBeenCalledTimes(3);
      expect(f.api.resume).toHaveBeenCalledOnce();
      expect(f.controller.getSnapshot().error).toBeNull();
    } finally { f.controller.pause(); }
  });
  it.each(['pause', 'reset'] as const)('does not resume after %s during a Loop setting retry', async operation => {
    const f = fixture(), saved = deferred<RunCursor>();
    f.api.adaptive.mockRejectedValueOnce(new Error('Setting request failed.'))
      .mockImplementationOnce(() => saved.promise);
    try {
      f.start(); await f.playing();
      f.controller.setAdaptive(true);
      await vi.waitFor(() => {
        expect(f.controller.getSnapshot().phase).toBe('paused');
        expect(f.controller.getSnapshot().stopping).toBe(false);
      });
      f.controller.resume();
      await vi.waitFor(() => expect(f.api.adaptive).toHaveBeenCalledTimes(2));
      f.controller[operation]();
      saved.resolve(f.cursor('paused'));
      await vi.waitFor(() => expect(f.api.pause).toHaveBeenCalledTimes(2));
      expect(f.api.resume).not.toHaveBeenCalled();
      expect(f.scene.perform).toHaveBeenCalledOnce();
      expect(f.controller.getSnapshot().running).toBe(false);
      expect(f.controller.getSnapshot().phase).toBe(operation === 'reset' ? 'idle' : 'paused');
    } finally { saved.resolve(f.cursor('paused')); f.controller.pause(); }
  });
  it('Pause/Resume restarts only the interrupted action with a fresh attempt, preserving completed actions', async () => {
    const f = fixture(); f.start(); await f.finish(); await f.playing();
    const interrupted = f.controller.getSnapshot().execution!;
    f.controller.pause(); await vi.waitFor(() => expect(f.controller.getSnapshot().stopping).toBe(false));
    expect(f.api.outcome).toHaveBeenCalledOnce();
    f.controller.resume(); await f.playing();
    expect(f.controller.getSnapshot().execution?.action_id).toBe(interrupted.action_id);
    expect(f.controller.getSnapshot().execution?.attempt_id).not.toBe(interrupted.attempt_id);
    expect(f.controller.getSnapshot().rankStates['a-0']).toBe('completed');
    expect(f.api.plan).toHaveBeenCalledOnce(); expect(f.api.search).toHaveBeenCalledOnce();
    f.controller.pause();
  });
  it('reconciles a lost outcome acknowledgement on Resume and ignores its late cursor', async () => {
    const f = fixture();
    const ack = deferred<RunCursor>();
    const original = f.api.outcome.getMockImplementation()!;
    f.api.outcome.mockImplementationOnce(async (id, outcome) => { await original(id, outcome); return ack.promise; });
    f.start(); await f.playing(); f.video.finish();
    await vi.waitFor(() => expect(f.api.outcome).toHaveBeenCalledOnce());
    f.controller.pause(); await vi.waitFor(() => expect(f.controller.getSnapshot().stopping).toBe(false));
    f.controller.resume(); await f.playing();
    const resumed = f.controller.getSnapshot().execution;
    expect(resumed?.action_id).toBe('a-1');
    expect(f.controller.getSnapshot().rankStates['a-0']).toBe('completed');
    ack.resolve(f.cursor()); await Promise.resolve(); await Promise.resolve();
    expect(f.controller.getSnapshot().execution).toEqual(resumed);
    expect(f.scene.perform).toHaveBeenCalledTimes(2);
    f.controller.pause();
  });
  it('does not gate query planning or search on navigation', async () => {
    const f = fixture(true), navigation = deferred<void>();
    f.start(); await f.finish(); await f.finish(); await f.finish();
    f.scene.ensureInteraction.mockImplementation(() => navigation.promise);
    await vi.waitFor(() => expect(f.api.search).toHaveBeenCalledTimes(2));
    f.controller.pause(); navigation.resolve();
    expect(f.api.plan).toHaveBeenCalledTimes(2);
  });
  it('ignores a late planned query after Pause and does not begin retrieval', async () => {
    const f = fixture(), pending = deferred<RunPlan>();
    f.api.plan.mockImplementation(() => pending.promise);
    f.start(); await vi.waitFor(() => expect(f.api.plan).toHaveBeenCalledOnce());
    f.controller.pause(); pending.resolve({ run_id: 'run', round_id: 'round-1', round: 1, plan_id: 'late', query: 'late', query_reason: 'late', scenario: scenarios[1] });
    await Promise.resolve(); await Promise.resolve();
    expect(f.api.search).not.toHaveBeenCalled(); expect(f.scene.perform).not.toHaveBeenCalled();
    expect(f.scene.updateEncounterBehavior).not.toHaveBeenCalled();
  });
  it('does not move until actual playback starts, and no blocked callback survives Pause', async () => {
    const f = fixture(); f.video.play.mockRejectedValue(new DOMException('blocked', 'NotAllowedError'));
    f.start(); await vi.waitFor(() => expect(f.controller.getSnapshot().playbackBlocked).toBe(true));
    expect(f.scene.perform).not.toHaveBeenCalled();
    f.controller.pause(); f.video.dispatchEvent(new Event('playing'));
    expect(f.scene.perform).not.toHaveBeenCalled(); expect(f.api.outcome).not.toHaveBeenCalled();
  });
  it('rejects passive or incorrectly ranked server queues before playback', async () => {
    const f = fixture(); f.api.search.mockImplementation(async () => { const round = f.round(); round.queue[0].candidate.action!.primitive = 'head_scan'; return round; });
    f.start(); await vi.waitFor(() => expect(f.controller.getSnapshot().phase).toBe('failed'));
    expect(f.video.play).not.toHaveBeenCalled(); expect(f.scene.perform).not.toHaveBeenCalled();
  });
  it('stops proactive navigation and media when a fast no-match ends the run', async () => {
    const f = fixture();
    let navigating = false;
    f.scene.stop.mockImplementation(() => { navigating = false; });
    f.api.search.mockImplementation(async () => {
      navigating = true; // The animal has appeared; its automatic approach is unfinished.
      return { ...f.round(), queue: [], execution: null, run_status: 'paused', status: 'no_supported_imitation' };
    });
    f.start();
    await vi.waitFor(() => expect(f.controller.getSnapshot().phase).toBe('empty'));
    expect(f.controller.getSnapshot().running).toBe(false);
    expect(navigating).toBe(false);
    expect(f.scene.stop.mock.invocationCallOrder.at(-1)).toBeGreaterThan(f.api.search.mock.invocationCallOrder[0]);
    expect(f.scene.stopCompanion).toHaveBeenCalled(); expect(f.video.pause).toHaveBeenCalled();
    expect(f.scene.perform).not.toHaveBeenCalled(); expect(f.api.outcome).not.toHaveBeenCalled();
  });
  it('replays through the same executor without new planning and labels its outcomes', async () => {
    const f = fixture(); f.start(); await f.finish(); f.controller.pause();
    await vi.waitFor(() => expect(f.controller.getSnapshot().stopping).toBe(false));
    f.controller.replay(); await f.finish();
    expect(f.api.replay).toHaveBeenCalledOnce(); expect(f.api.plan).toHaveBeenCalledOnce(); expect(f.api.search).toHaveBeenCalledOnce();
    expect(f.controller.getSnapshot().history[0].replay).toBe(true);
    f.controller.pause();
  });
  it('only automatically resumes a pause caused by visibility', async () => {
    const f = fixture(); f.start(); await f.playing();
    f.controller.visibility(true); f.controller.visibility(false);
    await vi.waitFor(() => expect(f.api.resume).toHaveBeenCalledOnce());
    f.controller.pause(); f.controller.visibility(true); f.controller.visibility(false);
    expect(f.api.resume).toHaveBeenCalledOnce();
  });
});

it('bounds shared planning deadlines for both toggle states', () => {
  expect(runDeadline(12000, 60000)).toBe(17000);
  for (const invalid of [undefined, NaN, -1, 60001, '1000']) expect(runDeadline(invalid, 60000)).toBe(65000);
  expect(runDeadline(undefined, 180000)).toBe(185000);
});
